#!/usr/bin/env python3
"""
Analyze video files to extract episode numbers from filenames.
This provides a quick overview of what we have without needing OCR.
"""

import os
import re
import glob
from pathlib import Path
from typing import List, Tuple, Dict

def parse_episode_from_filename(filename: str) -> Tuple[int, List[int]]:
    """
    Extract season and episodes from filename.
    Returns: (season_num, [episode_numbers])
    """
    # Pattern: S09E20-E21 or S09E20 or S09E03-E07
    match = re.search(r'S(\d+)E(\d+)(?:-E(\d+))?', filename)
    if match:
        season = int(match.group(1))
        start_ep = int(match.group(2))
        end_ep = int(match.group(3)) if match.group(3) else start_ep
        episodes = list(range(start_ep, end_ep + 1))
        return season, episodes
    return None, []

def analyze_season_files(season_dir: str) -> Dict:
    """Analyze all files in a season directory."""
    season_num = int(os.path.basename(season_dir).split()[-1])
    files = sorted(glob.glob(os.path.join(season_dir, "*.mkv")))
    
    analysis = {
        "season": season_num,
        "total_files": len(files),
        "files": [],
        "episodes_covered": set(),
        "gaps": [],
        "overlaps": [],
    }
    
    for filepath in files:
        filename = os.path.basename(filepath)
        season, episodes = parse_episode_from_filename(filename)
        
        if season == season_num:
            file_info = {
                "filename": filename,
                "episodes": episodes,
                "count": len(episodes),
            }
            analysis["files"].append(file_info)
            
            for ep in episodes:
                if ep in analysis["episodes_covered"]:
                    # Overlap detected
                    analysis["overlaps"].append(ep)
                analysis["episodes_covered"].add(ep)
    
    # Find gaps
    if analysis["episodes_covered"]:
        all_eps = sorted(analysis["episodes_covered"])
        for i in range(all_eps[0], all_eps[-1] + 1):
            if i not in analysis["episodes_covered"]:
                analysis["gaps"].append(i)
    
    return analysis

def main():
    base_dir = "Paw Patrol"
    
    if not os.path.isdir(base_dir):
        print(f"❌ Directory not found: {base_dir}")
        return
    
    for season_dir in ["Season 09", "Season 10"]:
        season_path = os.path.join(base_dir, season_dir)
        if not os.path.isdir(season_path):
            continue
        
        analysis = analyze_season_files(season_path)
        
        print(f"\n{'='*80}")
        print(f"SEASON {analysis['season']:02d} ANALYSIS")
        print(f"{'='*80}")
        print(f"Total files: {analysis['total_files']}")
        print(f"Episodes covered: {len(analysis['episodes_covered'])}")
        
        if analysis['gaps']:
            print(f"⚠️  MISSING EPISODES ({len(analysis['gaps'])}): {sorted(analysis['gaps'])}")
        else:
            print(f"✓ No gaps detected")
        
        if analysis['overlaps']:
            print(f"⚠️  OVERLAPPING EPISODES ({len(analysis['overlaps'])}): {sorted(set(analysis['overlaps']))}")
        
        # Show file breakdown
        print(f"\n{'File':<50} {'Episodes':<20}")
        print("-" * 75)
        
        for file_info in analysis["files"]:
            if len(file_info["episodes"]) == 1:
                ep_str = f"E{file_info['episodes'][0]:02d}"
            else:
                ep_str = f"E{file_info['episodes'][0]:02d}-E{file_info['episodes'][-1]:02d}"
            
            filename = file_info["filename"][:48]
            print(f"{filename:<50} {ep_str:<20}")
        
        # Summary of what we have
        print(f"\n{'Episode Range':<20} {'Count':<10} {'Type':<30}")
        print("-" * 60)
        
        single_ep_files = [f for f in analysis["files"] if len(f["episodes"]) == 1]
        multi_ep_files = [f for f in analysis["files"] if len(f["episodes"]) > 1]
        
        print(f"{'Single episodes':<20} {len(single_ep_files):<10} {sum(len(f['episodes']) for f in single_ep_files)} total")
        print(f"{'Multi-episode files':<20} {len(multi_ep_files):<10} {sum(len(f['episodes']) for f in multi_ep_files)} total")
        print(f"{'TOTAL':<20} {analysis['total_files']:<10} {len(analysis['episodes_covered'])} total")

if __name__ == "__main__":
    main()
