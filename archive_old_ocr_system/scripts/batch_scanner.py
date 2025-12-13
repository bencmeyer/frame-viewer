#!/usr/bin/env python3
"""
Batch Episode Scanner
Scans all Season 9 and 10 files to detect mislabeled episodes.
"""

import json
from pathlib import Path
from typing import Dict, Tuple, List
from collections import defaultdict

from episode_detector import EpisodeDetector, parse_filename_episodes, format_episode_range
from title_matcher import TitleMatch
from tvdb_loader import load_episode_database


def scan_directory(
    directory: Path,
    season: int,
    detector: EpisodeDetector
) -> List[Dict]:
    """
    Scan all video files in directory.
    
    Args:
        directory: Path to season directory
        season: Season number
        detector: EpisodeDetector instance
    
    Returns:
        List of scan results
    """
    results = []
    
    # Find all video files
    video_files = sorted(directory.glob('*.mkv'))
    video_files.extend(sorted(directory.glob('*.mp4')))
    video_files.extend(sorted(directory.glob('*.avi')))
    
    print(f"\nScanning {len(video_files)} files in {directory.name}...")
    
    for video_file in video_files:
        print(f"\n📹 {video_file.name}")
        
        # Parse filename
        filename_season, filename_episodes = parse_filename_episodes(video_file.name)
        
        if filename_season != season:
            print(f"  ⚠️  Filename season mismatch: {filename_season} != {season}")
            continue
        
        # Detect actual content
        detected = detector.detect_episodes_in_file(video_file, season)
        
        # Build result
        result = {
            'filename': video_file.name,
            'filepath': str(video_file),
            'filename_season': filename_season,
            'filename_episodes': filename_episodes,
            'detected_episodes': [],
            'matches': []
        }
        
        # First episode
        if detected['first_episode']:
            match = detected['first_episode']
            result['detected_episodes'].append(match.episode_number)
            result['matches'].append({
                'position': 'first',
                'episode': match.episode_number,
                'title': match.matched_title,
                'confidence': match.confidence,
                'raw_ocr': match.raw_ocr
            })
            print(f"  ✓ First episode: E{match.episode_number:02d} - {match.matched_title}")
            print(f"    Confidence: {match.confidence:.1%}, OCR: '{match.raw_ocr}'")
        else:
            print(f"  ✗ First episode: Not detected")
        
        # Second episode
        if detected['second_episode']:
            match = detected['second_episode']
            result['detected_episodes'].append(match.episode_number)
            result['matches'].append({
                'position': 'second',
                'episode': match.episode_number,
                'title': match.matched_title,
                'confidence': match.confidence,
                'raw_ocr': match.raw_ocr
            })
            print(f"  ✓ Second episode: E{match.episode_number:02d} - {match.matched_title}")
            print(f"    Confidence: {match.confidence:.1%}, OCR: '{match.raw_ocr}'")
        
        # Check for mismatch
        is_mismatch = (
            sorted(result['detected_episodes']) != sorted(filename_episodes)
            if result['detected_episodes'] else False
        )
        
        result['is_mismatch'] = is_mismatch
        
        if is_mismatch:
            print(f"  🚨 MISMATCH: Filename says {format_episode_range(filename_episodes)}, "
                  f"detected {format_episode_range(result['detected_episodes'])}")
        else:
            print(f"  ✅ Match: Filename matches detected content")
        
        results.append(result)
    
    return results


def generate_rename_commands(results: List[Dict], season: int) -> List[str]:
    """
    Generate shell commands to rename mislabeled files.
    
    Args:
        results: Scan results
        season: Season number
    
    Returns:
        List of mv commands
    """
    commands = []
    
    for result in results:
        if not result['is_mismatch']:
            continue
        
        if not result['detected_episodes']:
            continue
        
        # Build new filename
        old_path = Path(result['filepath'])
        
        # Keep everything before S##E##
        parts = old_path.name.split('S' + str(season).zfill(2))
        if len(parts) < 2:
            continue
        
        prefix = parts[0]
        
        # Keep everything after episode numbers
        import re
        suffix_match = re.search(r'(E\d+(?:-E\d+)?)(.+)$', parts[1], re.IGNORECASE)
        if not suffix_match:
            continue
        
        suffix = suffix_match.group(2)
        
        # Build new filename
        new_episode_str = format_episode_range(result['detected_episodes'])
        new_name = f"{prefix}S{season:02d}{new_episode_str}{suffix}"
        new_path = old_path.parent / new_name
        
        # Generate command
        cmd = f"mv '{old_path}' '{new_path}'"
        commands.append(cmd)
    
    return commands


def main():
    """Main batch scanning function."""
    import sys
    
    # Configuration
    BASE_DIR = Path("Paw Patrol")
    SEASONS = [9, 10]
    
    # Check if base directory exists
    if not BASE_DIR.exists():
        print(f"Error: Directory not found: {BASE_DIR}")
        sys.exit(1)
    
    # Load episode database from TVDB
    print("Loading episode database from TVDB...")
    episode_database = load_episode_database(SEASONS)
    
    if not episode_database:
        print("Error: Failed to load episode database from TVDB")
        sys.exit(1)
    
    print(f"✓ Loaded {len(episode_database)} episodes from TVDB")
    
    # Initialize detector
    print("Initializing EasyOCR (this may take a moment)...")
    detector = EpisodeDetector(episode_database, use_gpu=True)
    
    # Scan each season
    all_results = {}
    
    for season in SEASONS:
        season_dir = BASE_DIR / f"Season {season:02d}"
        
        if not season_dir.exists():
            print(f"⚠️  Season directory not found: {season_dir}")
            continue
        
        results = scan_directory(season_dir, season, detector)
        all_results[season] = results
    
    # Generate summary
    print("\n" + "="*80)
    print("SCAN SUMMARY")
    print("="*80)
    
    total_files = 0
    total_mismatches = 0
    
    for season, results in all_results.items():
        mismatches = [r for r in results if r['is_mismatch']]
        total_files += len(results)
        total_mismatches += len(mismatches)
        
        print(f"\nSeason {season}:")
        print(f"  Total files: {len(results)}")
        print(f"  Mismatches: {len(mismatches)}")
        
        if mismatches:
            print(f"  Mislabeled files:")
            for m in mismatches:
                print(f"    - {m['filename']}")
                print(f"      Should be: {format_episode_range(m['detected_episodes'])}")
    
    print(f"\nOverall: {total_mismatches}/{total_files} files mislabeled ({total_mismatches/total_files*100:.1f}%)")
    
    # Generate rename commands
    print("\n" + "="*80)
    print("RENAME COMMANDS")
    print("="*80)
    
    all_commands = []
    for season, results in all_results.items():
        commands = generate_rename_commands(results, season)
        all_commands.extend(commands)
    
    if all_commands:
        print(f"\nGenerated {len(all_commands)} rename commands:\n")
        for cmd in all_commands:
            print(cmd)
        
        # Save to file
        script_path = Path("rename_mislabeled.sh")
        with open(script_path, 'w') as f:
            f.write("#!/bin/bash\n")
            f.write("# Auto-generated rename commands for mislabeled episodes\n\n")
            for cmd in all_commands:
                f.write(cmd + "\n")
        
        script_path.chmod(0o755)
        print(f"\n✓ Saved rename script to: {script_path}")
        print(f"  Review and run with: ./{script_path}")
    else:
        print("\nNo mislabeled files found!")
    
    # Save detailed results
    results_path = Path("scan_results.json")
    with open(results_path, 'w') as f:
        json.dump(all_results, f, indent=2)
    
    print(f"\n✓ Saved detailed results to: {results_path}")


if __name__ == '__main__':
    main()
