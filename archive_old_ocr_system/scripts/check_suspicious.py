#!/usr/bin/env python3
"""
Test specific files that are likely mislabeled.
Based on filename analysis, check if single-episode files actually contain 2 episodes.
"""

import os
import re
import sys
import subprocess
import tempfile
from pathlib import Path

def get_video_duration(video_path: str) -> float:
    """Get video duration in seconds using ffprobe."""
    try:
        cmd = [
            "ffprobe", "-v", "error", "-show_entries", "format=duration",
            "-of", "default=noprint_wrappers=1:nokey=1:noprint_wrappers=1",
            video_path
        ]
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=10)
        return float(result.stdout.strip())
    except:
        return 0.0

def extract_episode_nums(filename: str):
    """Extract season and episode numbers from filename."""
    match = re.search(r'S(\d+)E(\d+)(?:-E(\d+))?', filename)
    if match:
        season = int(match.group(1))
        start = int(match.group(2))
        end = int(match.group(3)) if match.group(3) else start
        return season, start, end
    return None, None, None

def main():
    # Known suspicious files: labeled as single but likely multi-episode
    suspicious_files = [
        # S09 - Single episode files where next episode is missing
        ("Paw Patrol/Season 09/Paw Patrol (2013) - S09E20 - Pups Stop the Return of Humsquatch [WEBDL-1080p][AAC 2.0][x264]-playWEB.mkv", 20, 21),
        ("Paw Patrol/Season 09/Paw Patrol (2013) - S09E22 - Mighty Pups Stop a Mighty Eel [WEBDL-1080p][AAC 2.0][x264]-playWEB.mkv", 22, 23),
        ("Paw Patrol/Season 09/Paw Patrol (2013) - S09E24 - Aqua Pups Pups Save a Floating Castle [WEBDL-1080p][AAC 2.0][x264]-playWEB.mkv", 24, 25),
        
        # S10 - Single episode file where next episode is missing  
        ("Paw Patrol/Season 10/Paw Patrol (2013) - S10E42 - Rescue Wheels Pups Save Adventure Bay [WEBDL-1080p][AC3 5.1][h264]-AtotIK.mkv", 42, 43),
    ]
    
    print(f"{'='*80}")
    print("TESTING SUSPICIOUS FILES FOR MULTI-EPISODE CONTENT")
    print(f"{'='*80}\n")
    
    for filepath, labeled_ep, suspected_next_ep in suspicious_files:
        if not os.path.exists(filepath):
            print(f"❌ File not found: {filepath}\n")
            continue
        
        filename = os.path.basename(filepath)
        duration = get_video_duration(filepath)
        
        print(f"📁 {filename[:70]}")
        print(f"   Labeled as: E{labeled_ep}")
        print(f"   Suspected: E{labeled_ep}-E{suspected_next_ep}")
        print(f"   Duration: {duration:.0f}s ({duration/60:.1f} min)")
        
        # Typical Paw Patrol episode: ~21 minutes = 1260 seconds
        # 2-episode file: ~42 minutes = 2520 seconds
        if duration > 2000:  # More than 33 minutes
            print(f"   ⚠️  Duration suggests MULTI-EPISODE file (>2000s)")
        elif duration > 1500:  # More than 25 minutes
            print(f"   ⚠️  Duration suggests POSSIBLE multi-episode file (>1500s)")
        else:
            print(f"   ✓ Duration suggests single episode")
        
        print()

if __name__ == "__main__":
    main()
