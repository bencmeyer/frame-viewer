#!/usr/bin/env python3
"""
Find episode boundaries within a video file using scene detection.
This identifies where one episode ends and another begins.
"""

import subprocess
import sys
from pathlib import Path

def find_scenes(video_path: str, threshold: float = 27.0) -> list:
    """
    Detect scene changes in video using ffmpeg.
    
    Returns list of (timestamp_seconds, score) tuples.
    threshold: sensitivity (lower = more scenes detected, 27 is default)
    """
    try:
        # Use ffmpeg to detect scene changes
        cmd = [
            "ffmpeg", "-i", video_path,
            "-vf", f"select=gt(scene\\,{threshold/100}),showinfo",
            "-f", "null", "-"
        ]
        
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=120)
        
        scenes = []
        for line in result.stderr.split('\n'):
            if 'Parsed_showinfo' in line and 'pts_time:' in line:
                # Extract timestamp
                try:
                    import re
                    match = re.search(r'pts_time:(\d+\.?\d*)', line)
                    if match:
                        timestamp = float(match.group(1))
                        scenes.append(timestamp)
                except:
                    pass
        
        return scenes
    except Exception as e:
        print(f"Error detecting scenes: {e}", file=sys.stderr)
        return []

def extract_frame_at_time(video_path: str, time_seconds: float, output_path: str):
    """Extract a single frame at specified time."""
    try:
        cmd = [
            "ffmpeg", "-ss", str(time_seconds), "-i", video_path,
            "-vframes", "1", "-y", output_path
        ]
        subprocess.run(cmd, capture_output=True, timeout=10)
    except:
        pass

def main():
    if len(sys.argv) < 2:
        print("Usage: python scene_detector.py <video_file> [threshold]")
        print("  threshold: scene detection sensitivity (1-100, default 27)")
        sys.exit(1)
    
    video_path = sys.argv[1]
    threshold = float(sys.argv[2]) if len(sys.argv) > 2 else 27.0
    
    if not Path(video_path).exists():
        print(f"❌ File not found: {video_path}")
        sys.exit(1)
    
    print(f"Detecting scenes in: {Path(video_path).name}")
    print(f"Threshold: {threshold}")
    print("Analyzing video... (this may take a minute)")
    
    scenes = find_scenes(video_path, threshold)
    
    if not scenes:
        print("❌ No scene changes detected")
        return
    
    print(f"\n✓ Found {len(scenes)} scene changes")
    print("\nScene change timestamps (potential episode boundaries):")
    print("=" * 60)
    
    for i, timestamp in enumerate(scenes[:20], 1):  # Show first 20
        minutes = int(timestamp // 60)
        seconds = int(timestamp % 60)
        print(f"{i:2d}. {timestamp:7.2f}s ({minutes:2d}:{seconds:02d}) ← Extract frame here to check episodes")
    
    if len(scenes) > 20:
        print(f"... and {len(scenes) - 20} more")
    
    print("\nTo extract frames at these boundaries, run:")
    print("  ffmpeg -ss <timestamp> -i video.mkv -vframes 1 frame.png")

if __name__ == "__main__":
    main()
