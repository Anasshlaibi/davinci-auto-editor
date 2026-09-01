"""
DaVinci Auto-Editor: Two-step "Mark & Confirm" silence removal workflow.
Full multi-clip timeline support.

Step 1: Analyzes ALL clips on the timeline audio using FFmpeg and drops Red (Cut Start) and Blue (Cut End) markers.
Step 2: Human Editor reviews the markers inside DaVinci Resolve (deletes any marker they want to keep).
Step 3: Reads the remaining markers across all clips, calculates the keep ranges for each clip, and assembles the complete tightened timeline.
"""

from __future__ import annotations

import os
import re
import subprocess
import sys
from typing import Any, Dict, List, Optional, Tuple


def _get_resolve():
    """Import and get the connected DaVinci Resolve instance."""
    try:
        from src.server import get_resolve
        return get_resolve()
    except Exception:
        pass
    try:
        import DaVinciResolveScript as dvr
        return dvr.scriptapp("Resolve")
    except Exception:
        pass
    return None


def mark_silences_on_timeline(
    resolve: Optional[Any] = None,
    track_type: str = "video",
    track_index: int = 1,
    clip_index: Optional[int] = None,
    threshold_db: float = -32.0,
    min_duration: float = 0.3,
    start_marker_color: str = "Red",
    end_marker_color: str = "Blue",
    clear_existing: bool = True,
) -> Dict[str, Any]:
    """
    Step 1: Analyzes all clips (or a specified clip) on the timeline track using FFmpeg
    and drops Red (Cut Start) and Blue (Cut End) markers.
    """
    if resolve is None:
        resolve = _get_resolve()
    if not resolve:
        return {"success": False, "error": "Could not connect to DaVinci Resolve. Is Resolve open?"}

    pm = resolve.GetProjectManager()
    proj = pm.GetCurrentProject() if pm else None
    tl = proj.GetCurrentTimeline() if proj else None

    if not tl:
        return {"success": False, "error": "No active timeline found in DaVinci Resolve."}

    # 1. Timeline frame rate
    try:
        fps = float(tl.GetSetting("timelineFrameRate") or 30.0)
    except Exception:
        fps = 30.0

    # 2. Get clips on the track
    items = tl.GetItemListInTrack(track_type, track_index) or []
    if not items:
        # Fallback to audio track if video track is empty
        items = tl.GetItemListInTrack("audio", 1) or []
    if not items:
        return {"success": False, "error": f"No clips found on Track {track_index}."}

    # Filter to specific clip if requested
    if clip_index is not None:
        if 0 <= clip_index < len(items):
            items_to_process = [(clip_index, items[clip_index])]
        else:
            return {"success": False, "error": f"Clip index {clip_index} out of range (0-{len(items)-1})."}
    else:
        items_to_process = list(enumerate(items))

    # Clear existing Red/Blue markers if requested to avoid duplicates
    if clear_existing:
        try:
            tl.DeleteMarkersByColor(start_marker_color)
            tl.DeleteMarkersByColor(end_marker_color)
        except Exception:
            pass

    total_markers_added = 0
    total_silences_found = 0
    clips_processed = 0

    for idx, item in items_to_process:
        mpi = item.GetMediaPoolItem()
        if not mpi:
            continue
        audio_file_path = mpi.GetClipProperty("File Path")
        if not audio_file_path or not os.path.isfile(audio_file_path):
            continue

        tl_start = item.GetStart()
        tl_end   = item.GetEnd()
        src_start_frame = item.GetSourceStartFrame()
        dur_frames = tl_end - tl_start

        if dur_frames <= 0:
            continue

        start_sec = src_start_frame / fps
        dur_sec   = dur_frames / fps

        # Run FFmpeg silence detection on this clip's playback range
        command = [
            "ffmpeg",
            "-ss", f"{start_sec:.3f}",
            "-t", f"{dur_sec:.3f}",
            "-i", audio_file_path,
            "-af", f"silencedetect=noise={threshold_db}dB:d={min_duration}",
            "-f", "null", "-",
        ]

        try:
            result = subprocess.run(command, stderr=subprocess.PIPE, text=True, check=False)
        except FileNotFoundError:
            return {"success": False, "error": "FFmpeg is not installed or not in PATH."}

        starts = [float(x) for x in re.findall(r"silence_start:\s*([\d\.]+)", result.stderr)]
        ends   = [float(x) for x in re.findall(r"silence_end:\s*([\d\.]+)", result.stderr)]

        if not starts:
            clips_processed += 1
            continue

        # Pair starts and ends
        pairs: List[Tuple[float, float]] = []
        end_idx = 0
        for st in starts:
            while end_idx < len(ends) and ends[end_idx] <= st:
                end_idx += 1
            if end_idx < len(ends):
                pairs.append((st, ends[end_idx]))
                end_idx += 1

        # Drop markers for this clip
        for p_i, (st, en) in enumerate(pairs):
            marker_start_frame = tl_start + int(st * fps)
            marker_end_frame   = tl_start + int(en * fps)
            # Bound within clip
            marker_start_frame = max(tl_start, min(tl_end, marker_start_frame))
            marker_end_frame   = max(tl_start, min(tl_end, marker_end_frame))
            dur_gap = round(en - st, 2)

            tl.AddMarker(
                marker_start_frame,
                start_marker_color,
                f"Clip {idx+1} Cut #{p_i+1}",
                f"Silence: {dur_gap}s",
                1.0,
                f"silence_start_{idx+1}_{p_i+1}",
            )
            tl.AddMarker(
                marker_end_frame,
                end_marker_color,
                f"Clip {idx+1} End #{p_i+1}",
                "Resume vocal",
                1.0,
                f"silence_end_{idx+1}_{p_i+1}",
            )
            total_markers_added += 2

        total_silences_found += len(pairs)
        clips_processed += 1

    return {
        "success": True,
        "clips_analyzed": clips_processed,
        "silence_count": total_silences_found,
        "markers_added": total_markers_added,
        "timeline_name": tl.GetName(),
        "fps": fps,
    }


def execute_cuts_from_markers(
    resolve: Optional[Any] = None,
    track_type: str = "video",
    track_index: int = 1,
    start_marker_color: str = "Red",
    end_marker_color: str = "Blue",
    new_timeline_suffix: str = "Auto Cut",
) -> Dict[str, Any]:
    """
    Step 3: Reads remaining Red/Blue markers across ALL clips on the timeline,
    calculates the 'keep ranges' for each clip, and assembles the complete tightened timeline.
    """
    if resolve is None:
        resolve = _get_resolve()
    if not resolve:
        return {"success": False, "error": "Could not connect to DaVinci Resolve."}

    pm = resolve.GetProjectManager()
    proj = pm.GetCurrentProject() if pm else None
    tl = proj.GetCurrentTimeline() if proj else None
    mp = proj.GetMediaPool() if proj else None

    if not tl or not mp:
        return {"success": False, "error": "No active timeline or MediaPool found."}

    markers = tl.GetMarkers() or {}
    items = tl.GetItemListInTrack(track_type, track_index) or []
    if not items:
        return {"success": False, "error": f"No clips found on Track {track_index}."}

    # Sort cut markers by frame
    sorted_frames = sorted(markers.keys())
    cut_markers = [(int(f), markers[f]) for f in sorted_frames if markers[f].get("color") in (start_marker_color, end_marker_color)]

    all_subclips = []
    total_cuts_made = 0

    # Iterate through ALL clips in sequence
    for clip_idx, item in enumerate(items):
        mpi = item.GetMediaPoolItem()
        if not mpi:
            continue

        clip_start = item.GetStart()
        clip_end   = item.GetEnd()
        src_start  = item.GetSourceStartFrame()

        # Find markers that fall strictly within this clip
        clip_markers = [(f, m) for f, m in cut_markers if clip_start <= f <= clip_end]

        if not clip_markers:
            # If no cut markers on this clip, keep the entire clip intact!
            dur = clip_end - clip_start
            all_subclips.append({
                "mediaPoolItem": mpi,
                "startFrame": int(src_start),
                "endFrame": int(src_start + dur),
            })
            continue

        # Calculate KEEP ranges for this clip
        keep_ranges: List[Tuple[int, int]] = []
        cur_pos = clip_start

        for frame, marker in clip_markers:
            col = marker.get("color")
            if col == start_marker_color:
                # End of current keep section
                if frame > cur_pos:
                    keep_ranges.append((cur_pos, frame))
            elif col == end_marker_color:
                # Start of next keep section
                cur_pos = frame
                total_cuts_made += 1

        # Add remaining tail of the clip
        if cur_pos < clip_end:
            keep_ranges.append((cur_pos, clip_end))

        # Convert keep ranges to source media frames
        for k_start, k_end in keep_ranges:
            media_start = src_start + (k_start - clip_start)
            media_end   = src_start + (k_end - clip_start)
            if media_end > media_start:
                all_subclips.append({
                    "mediaPoolItem": mpi,
                    "startFrame": int(media_start),
                    "endFrame": int(media_end),
                })

    if not all_subclips:
        return {"success": False, "error": "No valid subclips could be built."}

    # Create new timeline with unique name and append all subclips
    orig_name = tl.GetName()
    base_name = f"{orig_name} - {new_timeline_suffix}"
    new_timeline_name = base_name

    existing_names = {proj.GetTimelineByIndex(i).GetName() for i in range(1, proj.GetTimelineCount() + 1)}
    v = 1
    while new_timeline_name in existing_names:
        v += 1
        new_timeline_name = f"{base_name} v{v}"

    new_timeline = mp.CreateEmptyTimeline(new_timeline_name)
    if not new_timeline:
        return {"success": False, "error": f"Failed to create new timeline '{new_timeline_name}'."}

    proj.SetCurrentTimeline(new_timeline)
    appended = mp.AppendToTimeline(all_subclips)

    return {
        "success": bool(appended),
        "new_timeline_name": new_timeline_name,
        "clips_processed": len(items),
        "kept_segments_count": len(all_subclips),
        "cuts_executed": total_cuts_made,
    }


if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser(description="DaVinci Auto-Editor Multi-Clip Silence Cutter")
    parser.add_argument("--mark", action="store_true", help="Step 1: Analyze all clips and place cut markers")
    parser.add_argument("--cut", action="store_true", help="Step 3: Execute cuts from remaining markers across all clips")
    parser.add_argument("--clip", type=int, default=None, help="Optional: 0-based clip index (default: all clips)")
    parser.add_argument("--threshold", type=float, default=-32.0, help="Silence threshold in dB (default -32.0)")
    parser.add_argument("--min-duration", type=float, default=0.3, help="Minimum silence duration in seconds (default 0.3)")
    args = parser.parse_args()

    r = _get_resolve()
    if not r:
        print("Error: Could not connect to DaVinci Resolve. Make sure Resolve is open.")
        sys.exit(1)

    if args.mark:
        res = mark_silences_on_timeline(r, clip_index=args.clip, threshold_db=args.threshold, min_duration=args.min_duration)
        print("Mark Result:", res)
    elif args.cut:
        res = execute_cuts_from_markers(r)
        print("Cut Result:", res)
    else:
        parser.print_help()
