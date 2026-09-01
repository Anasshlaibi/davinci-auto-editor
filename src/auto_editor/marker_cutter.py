"""
DaVinci Auto-Editor: Two-step "Mark & Confirm" silence removal workflow.

Step 1: Analyzes timeline audio using FFmpeg and drops Red (Cut Start) and Blue (Cut End) markers.
Step 2: Human Editor reviews the markers inside DaVinci Resolve (deletes any marker they want to keep).
Step 3: Reads the remaining markers, calculates the keep ranges, and assembles the tightened timeline.
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
    audio_file_path: Optional[str] = None,
    threshold_db: float = -32.0,
    min_duration: float = 0.3,
    start_marker_color: str = "Red",
    end_marker_color: str = "Blue",
) -> Dict[str, Any]:
    """
    Step 1: Analyzes audio using FFmpeg and drops Red (Cut Start) and Blue (Cut End)
    markers onto the active timeline.
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

    # 1. Resolve timeline frame rate
    try:
        fps = float(tl.GetSetting("timelineFrameRate") or 30.0)
    except Exception:
        fps = 30.0

    # 2. If no audio_file_path is provided, inspect the timeline to find the source media
    clip_offset = 0
    if not audio_file_path:
        items = tl.GetItemListInTrack("video", 1) or []
        if not items:
            items = tl.GetItemListInTrack("audio", 1) or []
        if not items:
            return {"success": False, "error": "Timeline is empty. Please add media to Track 1."}
        
        # Use the first video/audio clip's source media
        first_item = items[0]
        mpi = first_item.GetMediaPoolItem()
        if not mpi:
            return {"success": False, "error": f"Clip '{first_item.GetName()}' has no MediaPoolItem."}
        
        audio_file_path = mpi.GetClipProperty("File Path")
        if not audio_file_path or not os.path.isfile(audio_file_path):
            return {"success": False, "error": f"Source file not accessible: {audio_file_path}"}
        
        # Timeline start frame offset
        clip_offset = first_item.GetStart()

    # 3. Run FFmpeg silence detection
    command = [
        "ffmpeg", "-i", audio_file_path,
        "-af", f"silencedetect=noise={threshold_db}dB:d={min_duration}",
        "-f", "null", "-"
    ]

    print(f"Analyzing audio: {audio_file_path} (threshold: {threshold_db}dB, min: {min_duration}s)...")
    try:
        result = subprocess.run(command, stderr=subprocess.PIPE, text=True, check=False)
    except FileNotFoundError:
        return {"success": False, "error": "FFmpeg is not installed or not in PATH."}

    # 4. Parse FFmpeg output
    silence_starts = [float(x) for x in re.findall(r"silence_start:\s*([\d\.]+)", result.stderr)]
    silence_ends   = [float(x) for x in re.findall(r"silence_end:\s*([\d\.]+)", result.stderr)]

    if not silence_starts:
        return {"success": True, "marked_count": 0, "message": "No silence pauses detected."}

    # Pair starts and ends
    pairs: List[Tuple[float, float]] = []
    end_idx = 0
    for st in silence_starts:
        while end_idx < len(silence_ends) and silence_ends[end_idx] <= st:
            end_idx += 1
        if end_idx < len(silence_ends):
            pairs.append((st, silence_ends[end_idx]))
            end_idx += 1

    # 5. Drop markers onto the timeline
    added = 0
    for i, (st, en) in enumerate(pairs):
        start_frame = clip_offset + int(st * fps)
        end_frame   = clip_offset + int(en * fps)
        dur_sec     = round(en - st, 2)

        # Drop Cut Start marker
        tl.AddMarker(
            start_frame,
            start_marker_color,
            f"Cut Start #{i+1}",
            f"Silence duration: {dur_sec}s",
            1.0,
            "auto_silence_start",
        )
        # Drop Cut End marker
        tl.AddMarker(
            end_frame,
            end_marker_color,
            f"Cut End #{i+1}",
            "Resume vocal",
            1.0,
            "auto_silence_end",
        )
        added += 2

    print(f"Dropped {added} markers across {len(pairs)} silent regions.")
    return {
        "success": True,
        "silence_count": len(pairs),
        "markers_added": added,
        "timeline_name": tl.GetName(),
        "fps": fps,
    }


def execute_cuts_from_markers(
    resolve: Optional[Any] = None,
    start_marker_color: str = "Red",
    end_marker_color: str = "Blue",
    new_timeline_suffix: str = "Auto Cut",
) -> Dict[str, Any]:
    """
    Step 3: Reads remaining Red/Blue markers (after human review in Resolve),
    calculates the 'keep ranges', and assembles a tightened timeline.
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
    if not markers:
        return {"success": False, "error": "No markers found on timeline. Run Step 1 first."}

    # Filter markers matching our cut colors
    sorted_frames = sorted(markers.keys())
    cut_markers = [(f, markers[f]) for f in sorted_frames if markers[f].get("color") in (start_marker_color, end_marker_color)]

    if not cut_markers:
        return {
            "success": False,
            "error": f"No {start_marker_color} or {end_marker_color} markers found on the timeline."
        }

    # Get source clips on track 1
    items = tl.GetItemListInTrack("video", 1) or []
    if not items:
        return {"success": False, "error": "No video clips found on Track 1."}

    primary_item = items[0]
    mpi = primary_item.GetMediaPoolItem()
    if not mpi:
        return {"success": False, "error": f"Clip '{primary_item.GetName()}' has no MediaPoolItem."}

    clip_start_tl = primary_item.GetStart()
    clip_end_tl   = primary_item.GetEnd()
    src_start     = primary_item.GetSourceStartFrame()

    # Calculate KEEP ranges (timeline frames)
    keep_ranges: List[Dict[str, int]] = []
    current_start = clip_start_tl

    for frame, marker in cut_markers:
        color = marker.get("color")
        if color == start_marker_color:
            # End of a keep range (start of silence)
            if frame > current_start:
                keep_ranges.append({"start": current_start, "end": int(frame)})
        elif color == end_marker_color:
            # Start of next keep range (end of silence)
            current_start = int(frame)

    # Final tail of the clip
    if current_start < clip_end_tl:
        keep_ranges.append({"start": current_start, "end": clip_end_tl})

    if not keep_ranges:
        return {"success": False, "error": "No valid keep ranges computed from markers."}

    # Convert timeline frames to source media frames for AppendToTimeline
    subclips = []
    for rng in keep_ranges:
        # Source offset calculation
        media_start = (rng["start"] - clip_start_tl) + src_start
        media_end   = (rng["end"]   - clip_start_tl) + src_start
        if media_end > media_start:
            subclips.append({
                "mediaPoolItem": mpi,
                "startFrame": int(media_start),
                "endFrame": int(media_end),
            })

    if not subclips:
        return {"success": False, "error": "Calculated subclips are empty."}

    # Create new timeline and append the tightened subclips
    orig_name = tl.GetName()
    new_timeline_name = f"{orig_name} - {new_timeline_suffix}"
    new_timeline = mp.CreateEmptyTimeline(new_timeline_name)
    if not new_timeline:
        return {"success": False, "error": f"Failed to create new timeline '{new_timeline_name}'."}

    # Set as current timeline and append the kept segments
    proj.SetCurrentTimeline(new_timeline)
    appended = mp.AppendToTimeline(subclips)

    return {
        "success": bool(appended),
        "new_timeline_name": new_timeline_name,
        "kept_segments_count": len(subclips),
        "removed_cuts_count": len(cut_markers) // 2,
    }


if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser(description="DaVinci Auto-Editor Silence Cutter")
    parser.add_argument("--mark", action="store_true", help="Step 1: Analyze audio and place cut markers")
    parser.add_argument("--cut", action="store_true", help="Step 3: Execute cuts from remaining markers")
    parser.add_argument("--threshold", type=float, default=-32.0, help="Silence threshold in dB (default -32.0)")
    parser.add_argument("--min-duration", type=float, default=0.3, help="Minimum silence duration in seconds (default 0.3)")
    parser.add_argument("--audio-file", type=str, default=None, help="Path to audio file (optional, auto-detected from timeline)")
    args = parser.parse_args()

    r = _get_resolve()
    if not r:
        print("Error: Could not connect to DaVinci Resolve. Make sure Resolve is open.")
        sys.exit(1)

    if args.mark:
        res = mark_silences_on_timeline(r, audio_file_path=args.audio_file, threshold_db=args.threshold, min_duration=args.min_duration)
        print("Mark Result:", res)
    elif args.cut:
        res = execute_cuts_from_markers(r)
        print("Cut Result:", res)
    else:
        parser.print_help()
