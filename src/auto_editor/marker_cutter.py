"""
DaVinci Auto-Editor: Frame-Accurate "Mark & Confirm" Engine.
Solves Audio Math Drift with absolute timebases, fractional rounding, and attack/release safety buffers.

Step 1: Analyzes source audio with FFmpeg (absolute container timestamps), applies vocal padding,
        and places Red/Blue checkpoint markers.
Step 2: Human Editor reviews/deletes markers in DaVinci Resolve.
Step 3: Reads remaining markers, calculates frame-accurate keep ranges, and assembles via AppendToTimeline.
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
    threshold_db: float = -30.0,
    min_duration: float = 0.35,
    lead_out_seconds: float = 0.08,   # 4 frames @ 50fps: room for natural word decay
    lead_in_seconds: float = 0.12,    # 6 frames @ 50fps: catches initial consonant/breath
    start_marker_color: str = "Red",
    end_marker_color: str = "Blue",
    clear_existing: bool = True,
) -> Dict[str, Any]:
    """
    Step 1: Analyzes audio with FFmpeg using absolute file timebases and applies
    attack/release safety buffers to prevent vocal clipping and timecode drift.
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

    # 1. Exact timeline frame rate (handles 23.976, 29.97, 50.0, 59.94, etc.)
    try:
        fps = float(tl.GetSetting("timelineFrameRate") or 30.0)
    except Exception:
        fps = 30.0

    # 2. Get clips on the track
    items = tl.GetItemListInTrack(track_type, track_index) or []
    if not items:
        items = tl.GetItemListInTrack("audio", 1) or []
    if not items:
        return {"success": False, "error": f"No clips found on Track {track_index}."}

    if clip_index is not None:
        if 0 <= clip_index < len(items):
            items_to_process = [(clip_index, items[clip_index])]
        else:
            return {"success": False, "error": f"Clip index {clip_index} out of range (0-{len(items)-1})."}
    else:
        items_to_process = list(enumerate(items))

    # Clear existing Red/Blue markers if requested
    if clear_existing:
        try:
            tl.DeleteMarkersByColor(start_marker_color)
            tl.DeleteMarkersByColor(end_marker_color)
        except Exception:
            pass

    total_markers_added = 0
    total_silences_found = 0
    clips_processed = 0

    # Cache analyzed audio files to avoid redundant FFmpeg passes if clips share media
    file_silences_cache: Dict[str, List[Tuple[float, float]]] = {}

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
        src_end_frame   = src_start_frame + (tl_end - tl_start)

        # Analyze whole file once (zero seeking offset drift)
        if audio_file_path not in file_silences_cache:
            command = [
                "ffmpeg",
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

            pairs: List[Tuple[float, float]] = []
            end_idx = 0
            for st in starts:
                while end_idx < len(ends) and ends[end_idx] <= st:
                    end_idx += 1
                if end_idx < len(ends):
                    pairs.append((st, ends[end_idx]))
                    end_idx += 1

            file_silences_cache[audio_file_path] = pairs

        all_file_pairs = file_silences_cache[audio_file_path]

        # Map file silences strictly into this clip's source window
        clip_pairs: List[Tuple[int, int, float]] = []
        for raw_st_sec, raw_en_sec in all_file_pairs:
            # Apply attack/release safety buffers:
            # Padded start moves forward (after words decay)
            # Padded end moves backward (before next word begins)
            padded_st_sec = raw_st_sec + lead_out_seconds
            padded_en_sec = raw_en_sec - lead_in_seconds

            # If padding closed the gap, skip it (preserves natural breath/micro-pause)
            if padded_en_sec <= padded_st_sec:
                continue

            # Convert to absolute source frames using exact rounding
            src_silence_st = round(padded_st_sec * fps)
            src_silence_en = round(padded_en_sec * fps)

            # Check overlap with this clip's source window [src_start_frame, src_end_frame]
            overlap_st = max(src_start_frame, src_silence_st)
            overlap_en = min(src_end_frame, src_silence_en)

            if overlap_en > overlap_st:
                # Convert source frame to timeline frame
                tl_marker_st = tl_start + (overlap_st - src_start_frame)
                tl_marker_en = tl_start + (overlap_en - src_start_frame)
                dur_s = round((overlap_en - overlap_st) / fps, 2)
                clip_pairs.append((tl_marker_st, tl_marker_en, dur_s))

        # Drop markers for this clip
        for p_i, (mst, men, dur_s) in enumerate(clip_pairs):
            tl.AddMarker(
                mst,
                start_marker_color,
                f"Clip {idx+1} Cut #{p_i+1}",
                f"Silence: {dur_s}s (Padded)",
                1.0,
                f"silence_start_{idx+1}_{p_i+1}",
            )
            tl.AddMarker(
                men,
                end_marker_color,
                f"Clip {idx+1} End #{p_i+1}",
                "Resume vocal (Padded)",
                1.0,
                f"silence_end_{idx+1}_{p_i+1}",
            )
            total_markers_added += 2

        total_silences_found += len(clip_pairs)
        clips_processed += 1

    return {
        "success": True,
        "clips_analyzed": clips_processed,
        "silence_count": total_silences_found,
        "markers_added": total_markers_added,
        "timeline_name": tl.GetName(),
        "fps": fps,
        "lead_out_seconds": lead_out_seconds,
        "lead_in_seconds": lead_in_seconds,
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
    Step 3: Reads surviving Red/Blue markers across ALL clips on the timeline,
    assembles the tightened timeline via AppendToTimeline with zero drift.
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

    sorted_frames = sorted(markers.keys())
    cut_markers = [(int(f), markers[f]) for f in sorted_frames if markers[f].get("color") in (start_marker_color, end_marker_color)]

    all_subclips = []
    total_cuts_made = 0

    for item in items:
        mpi = item.GetMediaPoolItem()
        if not mpi:
            continue

        clip_start = item.GetStart()
        clip_end   = item.GetEnd()
        src_start  = item.GetSourceStartFrame()

        # Find markers that fall strictly within this clip
        clip_markers = [(f, m) for f, m in cut_markers if clip_start <= f <= clip_end]

        if not clip_markers:
            dur = clip_end - clip_start
            all_subclips.append({
                "mediaPoolItem": mpi,
                "startFrame": int(src_start),
                "endFrame": int(src_start + dur),
            })
            continue

        keep_ranges: List[Tuple[int, int]] = []
        cur_pos = clip_start

        for frame, marker in clip_markers:
            col = marker.get("color")
            if col == start_marker_color:
                if frame > cur_pos:
                    keep_ranges.append((cur_pos, frame))
            elif col == end_marker_color:
                cur_pos = frame
                total_cuts_made += 1

        if cur_pos < clip_end:
            keep_ranges.append((cur_pos, clip_end))

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

    # Auto-version timeline name
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
    parser = argparse.ArgumentParser(description="DaVinci Auto-Editor Zero-Drift Silence Cutter")
    parser.add_argument("--mark", action="store_true", help="Step 1: Analyze all clips and place cut markers")
    parser.add_argument("--cut", action="store_true", help="Step 3: Execute cuts from remaining markers across all clips")
    parser.add_argument("--clip", type=int, default=None, help="Optional: 0-based clip index (default: all clips)")
    parser.add_argument("--threshold", type=float, default=-30.0, help="Silence threshold in dB (default -30.0)")
    parser.add_argument("--min-duration", type=float, default=0.35, help="Minimum silence duration in seconds (default 0.35)")
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
