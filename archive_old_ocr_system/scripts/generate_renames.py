#!/usr/bin/env python3
"""
Generate rename commands based on verified episodes.
"""

import json
from pathlib import Path
from episode_detector import parse_filename_episodes, format_episode_range
import sys

def load_verifications(season: int) -> dict:
    """Load verification data."""
    verification_file = Path(f"verified_s{season:02d}.json")
    
    if not verification_file.exists():
        print(f"Error: No verification file found: {verification_file}")
        print(f"Run interactive_verify.py first to create verifications.")
        return {}
    
    with open(verification_file) as f:
        return json.load(f)

def generate_rename_commands(season: int, season_dir: Path) -> list:
    """
    Generate rename commands for mislabeled files.
    
    Returns:
        List of (old_path, new_path, reason) tuples
    """
    verifications = load_verifications(season)
    
    if not verifications:
        return []
    
    rename_commands = []
    
    for filename, verified_data in verifications.items():
        # Find the actual file
        file_path = season_dir / filename
        
        if not file_path.exists():
            print(f"Warning: Verified file not found: {filename}")
            continue
        
        # Parse filename episodes
        _, filename_episodes = parse_filename_episodes(filename)
        
        # Get verified episodes
        verified_episodes = verified_data['episodes']
        
        # Check if mismatch
        if sorted(filename_episodes) == sorted(verified_episodes):
            # Correctly labeled, skip
            continue
        
        # Build new filename
        import re
        
        # Extract parts of filename
        # Pattern: "Paw Patrol (2013) - S09E20 - Title [quality].mkv"
        match = re.match(r'(.+?)\s+-\s+S(\d+)E[\d-E]+\s+-\s+(.+?)(\[.+\]\..+)$', filename)
        
        if not match:
            print(f"Warning: Could not parse filename: {filename}")
            continue
        
        prefix = match.group(1)
        season_num = match.group(2)
        old_title = match.group(3)
        suffix = match.group(4)
        
        # Format new episode string
        new_episode_str = format_episode_range(verified_episodes)
        
        # Build new title from verified data or keep old
        new_title = verified_data.get('title', old_title)
        
        # Build new filename
        new_filename = f"{prefix} - S{season_num}{new_episode_str} - {new_title} {suffix}"
        new_path = season_dir / new_filename
        
        reason = f"Verified as E{'-E'.join(str(e) for e in verified_episodes)}"
        if verified_data.get('notes'):
            reason += f" ({verified_data['notes']})"
        
        rename_commands.append((file_path, new_path, reason))
    
    return rename_commands

def main():
    season = 9
    if len(sys.argv) > 1:
        season = int(sys.argv[1])
    
    season_dir = Path(f"Paw Patrol/Season {season:02d}")
    
    if not season_dir.exists():
        print(f"Error: Directory not found: {season_dir}")
        sys.exit(1)
    
    print(f"\n{'='*80}")
    print(f"Generate Rename Commands - Season {season}")
    print(f"{'='*80}\n")
    
    # Generate commands
    rename_commands = generate_rename_commands(season, season_dir)
    
    if not rename_commands:
        print("No mislabeled files found!")
        print("All verified files match their current labels.\n")
        return
    
    # Display commands
    print(f"Found {len(rename_commands)} files to rename:\n")
    
    for old_path, new_path, reason in rename_commands:
        print(f"{'='*80}")
        print(f"Old: {old_path.name}")
        print(f"New: {new_path.name}")
        print(f"Reason: {reason}")
        print()
    
    # Generate shell script
    script_path = Path(f"rename_verified_s{season:02d}.sh")
    
    with open(script_path, 'w') as f:
        f.write("#!/bin/bash\n")
        f.write(f"# Auto-generated rename commands for verified Season {season} episodes\n")
        f.write(f"# Generated from verified_s{season:02d}.json\n\n")
        
        for old_path, new_path, reason in rename_commands:
            f.write(f"# {reason}\n")
            f.write(f"mv '{old_path}' '{new_path}'\n\n")
    
    script_path.chmod(0o755)
    
    print(f"{'='*80}")
    print(f"✓ Rename script saved to: {script_path}")
    print(f"\nTo apply renames:")
    print(f"  ./{script_path}")
    print(f"\nTo review first:")
    print(f"  cat {script_path}")

if __name__ == '__main__':
    main()
