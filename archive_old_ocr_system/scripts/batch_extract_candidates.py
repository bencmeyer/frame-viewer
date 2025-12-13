#!/usr/bin/env python3
"""
Batch generate title card candidates for all files in a season.
"""

from pathlib import Path
from visual_title_finder import TitleCardFinder
import sys

def main():
    season = 9
    if len(sys.argv) > 1:
        season = int(sys.argv[1])
    
    season_dir = Path(f"Paw Patrol/Season {season:02d}")
    
    if not season_dir.exists():
        print(f"Error: Directory not found: {season_dir}")
        sys.exit(1)
    
    video_files = sorted(season_dir.glob("*.mkv"))
    video_files.extend(sorted(season_dir.glob("*.mp4")))
    
    print(f"\n{'='*80}")
    print(f"Batch Title Card Extraction - Season {season}")
    print(f"{'='*80}\n")
    print(f"Found {len(video_files)} files\n")
    
    finder = TitleCardFinder()
    
    for i, video_path in enumerate(video_files, 1):
        print(f"\n[{i}/{len(video_files)}] {video_path.name[:60]}...")
        
        output_dir = Path("title_card_candidates") / video_path.stem
        
        # Skip if already processed
        if output_dir.exists() and list(output_dir.glob("*.png")):
            print(f"  ⏭️  Skipping (already processed)")
            continue
        
        try:
            candidates = finder.find_title_card_candidates(video_path, output_dir, max_candidates=10)
            print(f"  ✓ Found {len(candidates)} candidates")
            
            # Show top 3
            for c in candidates[:3]:
                print(f"     {c['timestamp']:5.1f}s  score:{c['score']:.2f}  {c['ocr_text'][:40]}")
        
        except Exception as e:
            print(f"  ✗ Error: {e}")
    
    print(f"\n{'='*80}")
    print("COMPLETE")
    print(f"{'='*80}")
    print(f"\n✓ Candidate frames saved to: title_card_candidates/")
    print(f"\nNext: Run interactive_verify.py to review and confirm episodes")

if __name__ == '__main__':
    main()
