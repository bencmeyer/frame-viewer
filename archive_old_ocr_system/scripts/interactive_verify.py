#!/usr/bin/env python3
"""
Interactive Episode Verification Tool
Shows title card candidates and lets you confirm/correct episode information.
"""

import json
from pathlib import Path
from typing import List, Dict, Optional
from visual_title_finder import TitleCardFinder
from tvdb_loader import load_episode_database
from episode_detector import parse_filename_episodes

class VerificationSession:
    """Manages interactive verification of episodes."""
    
    def __init__(self, season: int):
        self.season = season
        self.episode_db = None
        self.finder = TitleCardFinder()
        self.verified_episodes = {}
        self.verification_file = Path(f"verified_s{season:02d}.json")
        
        # Load existing verifications
        if self.verification_file.exists():
            with open(self.verification_file) as f:
                self.verified_episodes = json.load(f)
    
    def load_episode_database(self):
        """Load TVDB episode database."""
        print("Loading TVDB episode database...")
        self.episode_db = load_episode_database([self.season])
        print(f"✓ Loaded {len(self.episode_db)} episodes\n")
    
    def save_verification(self, filename: str, episodes: List[int], timestamp: float, notes: str = ""):
        """Save verified episode information."""
        self.verified_episodes[filename] = {
            'episodes': episodes,
            'title_card_timestamp': timestamp,
            'notes': notes,
            'verified_date': str(Path.ctime(Path(__file__)))
        }
        
        with open(self.verification_file, 'w') as f:
            json.dump(self.verified_episodes, f, indent=2)
    
    def is_verified(self, filename: str) -> bool:
        """Check if file has been verified."""
        return filename in self.verified_episodes
    
    def verify_file(self, video_path: Path) -> Optional[Dict]:
        """
        Interactive verification of a single file.
        
        Returns:
            Verification result dict or None if skipped
        """
        print(f"\n{'='*80}")
        print(f"File: {video_path.name}")
        print('='*80)
        
        # Check if already verified
        if self.is_verified(video_path.name):
            verified = self.verified_episodes[video_path.name]
            print(f"✓ Already verified as E{'-E'.join(str(e) for e in verified['episodes'])}")
            print(f"  Title card at: {verified['title_card_timestamp']:.1f}s")
            if verified.get('notes'):
                print(f"  Notes: {verified['notes']}")
            
            response = input("\nRe-verify? (y/N): ").strip().lower()
            if response != 'y':
                return verified
        
        # Parse filename
        _, filename_episodes = parse_filename_episodes(video_path.name)
        print(f"\n📝 Filename says: E{'-E'.join(str(e) for e in filename_episodes)}")
        
        if filename_episodes and self.episode_db:
            print("\n   Expected titles:")
            for ep in filename_episodes:
                key = (self.season, ep)
                if key in self.episode_db:
                    print(f"   E{ep:02d}: {self.episode_db[key]['title']}")
        
        # Find title card candidates
        print("\n🔍 Finding title card candidates...")
        output_dir = Path("title_card_candidates") / video_path.stem
        candidates = self.finder.find_title_card_candidates(video_path, output_dir, max_candidates=8)
        
        if not candidates:
            print("\n⚠️  No title card candidates found")
            print("This episode may have graphical titles only.")
            
            response = input("\nManually specify episodes? (y/N): ").strip().lower()
            if response != 'y':
                return None
            
            # Manual entry
            episodes_str = input("Enter episode number(s) (e.g., '20' or '11-12'): ").strip()
            timestamp_str = input("Enter title card timestamp in seconds (or 0 if none): ").strip()
            notes = input("Notes (optional): ").strip()
            
            try:
                if '-' in episodes_str:
                    episodes = [int(x) for x in episodes_str.split('-')]
                else:
                    episodes = [int(episodes_str)]
                timestamp = float(timestamp_str) if timestamp_str else 0.0
                
                self.save_verification(video_path.name, episodes, timestamp, notes)
                return {'episodes': episodes, 'timestamp': timestamp}
            except ValueError:
                print("Invalid input, skipping.")
                return None
        
        # Show candidates
        print(f"\n📸 Found {len(candidates)} candidates (saved to {output_dir}):")
        print()
        
        for i, c in enumerate(candidates, 1):
            print(f"{i}. {c['timestamp']:6.1f}s  Score:{c['score']:.2f}  OCR: '{c['ocr_text'][:50]}'")
        
        print(f"\n💡 Open the images in: {output_dir}")
        print(f"   Command: xdg-open '{output_dir}' &")
        
        # Get user input
        print("\nOptions:")
        print("  1-8: Select candidate number as title card")
        print("  m: Manually enter episode info")
        print("  s: Skip this file")
        print("  q: Quit")
        
        while True:
            response = input("\nChoice: ").strip().lower()
            
            if response == 'q':
                return None
            
            if response == 's':
                print("Skipped.")
                return None
            
            if response == 'm':
                # Manual entry
                episodes_str = input("Enter episode number(s) (e.g., '20' or '11-12'): ").strip()
                timestamp_str = input("Enter title card timestamp in seconds: ").strip()
                notes = input("Notes (optional): ").strip()
                
                try:
                    if '-' in episodes_str:
                        episodes = [int(x) for x in episodes_str.split('-')]
                    else:
                        episodes = [int(episodes_str)]
                    timestamp = float(timestamp_str)
                    
                    self.save_verification(video_path.name, episodes, timestamp, notes)
                    print(f"✓ Verified as E{'-E'.join(str(e) for e in episodes)}")
                    return {'episodes': episodes, 'timestamp': timestamp}
                except ValueError:
                    print("Invalid input, try again.")
                    continue
            
            # Try to parse as candidate number
            try:
                choice = int(response)
                if 1 <= choice <= len(candidates):
                    candidate = candidates[choice - 1]
                    
                    print(f"\nSelected: {candidate['timestamp']:.1f}s")
                    print(f"OCR text: '{candidate['ocr_text']}'")
                    
                    # Confirm episodes
                    episodes_str = input(f"Enter episode(s) [default: {'-'.join(str(e) for e in filename_episodes)}]: ").strip()
                    
                    if episodes_str:
                        if '-' in episodes_str:
                            episodes = [int(x) for x in episodes_str.split('-')]
                        else:
                            episodes = [int(episodes_str)]
                    else:
                        episodes = filename_episodes
                    
                    notes = input("Notes (optional): ").strip()
                    
                    self.save_verification(video_path.name, episodes, candidate['timestamp'], notes)
                    print(f"✓ Verified as E{'-E'.join(str(e) for e in episodes)}")
                    return {'episodes': episodes, 'timestamp': candidate['timestamp']}
                else:
                    print(f"Invalid choice. Enter 1-{len(candidates)}, m, s, or q")
            except ValueError:
                print(f"Invalid choice. Enter 1-{len(candidates)}, m, s, or q")


def main():
    """Interactive verification workflow."""
    import sys
    
    season = 9  # Default to season 9
    
    if len(sys.argv) > 1:
        season = int(sys.argv[1])
    
    print(f"\n{'='*80}")
    print(f"Interactive Episode Verification - Season {season}")
    print('='*80 + "\n")
    
    session = VerificationSession(season)
    session.load_episode_database()
    
    # Get all video files
    season_dir = Path(f"Paw Patrol/Season {season:02d}")
    
    if not season_dir.exists():
        print(f"Error: Directory not found: {season_dir}")
        sys.exit(1)
    
    video_files = sorted(season_dir.glob("*.mkv"))
    video_files.extend(sorted(season_dir.glob("*.mp4")))
    
    print(f"Found {len(video_files)} video files\n")
    
    # Process each file
    verified_count = 0
    skipped_count = 0
    
    for video_path in video_files:
        result = session.verify_file(video_path)
        
        if result:
            verified_count += 1
        else:
            if input("\nContinue to next file? (Y/n): ").strip().lower() == 'n':
                break
            skipped_count += 1
    
    # Summary
    print(f"\n{'='*80}")
    print("VERIFICATION SUMMARY")
    print('='*80)
    print(f"Verified: {verified_count}")
    print(f"Skipped: {skipped_count}")
    print(f"\n✓ Verification data saved to: {session.verification_file}")


if __name__ == '__main__':
    main()
