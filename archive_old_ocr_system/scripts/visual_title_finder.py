#!/usr/bin/env python3
"""
Visual Title Card Finder
Extracts candidate title card frames for manual verification.
"""

import subprocess
import json
from pathlib import Path
from typing import List, Tuple, Optional
import tempfile
from PIL import Image
import easyocr
import numpy as np

# Global OCR reader cache (avoid re-initializing during rescan)
_ocr_reader = None

def get_ocr_reader():
    """Get or create the global OCR reader."""
    global _ocr_reader
    if _ocr_reader is None:
        print("  Initializing OCR reader (GPU)...")
        _ocr_reader = easyocr.Reader(['en'], gpu=True, verbose=False)
    return _ocr_reader

class TitleCardFinder:
    """Finds potential title card frames using scene detection and OCR hints."""
    
    def __init__(self):
        self.reader = get_ocr_reader()
    
    def get_video_duration(self, video_path: Path) -> float:
        """Get video duration in seconds."""
        cmd = ['ffprobe', '-v', 'quiet', '-print_format', 'json', '-show_format', str(video_path)]
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=10)
        data = json.loads(result.stdout)
        return float(data['format']['duration'])
    
    def find_scene_changes(self, video_path: Path, threshold: float = 0.3, max_time: int = 180) -> List[float]:
        """
        Find major scene changes in video (potential title card locations).
        
        Args:
            video_path: Path to video
            threshold: Scene detection threshold (0.3 = major changes)
            max_time: Only analyze first N seconds
        
        Returns:
            List of timestamps (seconds) where scenes change
        """
        print(f"  Analyzing scene changes (first {max_time}s)...")
        
        cmd = [
            'ffmpeg',
            '-i', str(video_path),
            '-t', str(max_time),
            '-vf', f'select=gt(scene\\,{threshold}),showinfo',
            '-f', 'null',
            '-'
        ]
        
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=60)
        
        # Parse timestamps from ffmpeg output
        import re
        timestamps = []
        for line in result.stderr.split('\n'):
            if 'pts_time:' in line:
                match = re.search(r'pts_time:(\d+\.?\d*)', line)
                if match:
                    timestamps.append(float(match.group(1)))
        
        return sorted(set(timestamps))
    
    def extract_frame(self, video_path: Path, timestamp: float, output_path: Path) -> bool:
        """Extract frame at timestamp to file."""
        cmd = [
            'ffmpeg',
            '-ss', str(timestamp),
            '-i', str(video_path),
            '-vframes', '1',
            '-y',
            str(output_path)
        ]
        
        result = subprocess.run(cmd, capture_output=True, timeout=10)
        return result.returncode == 0 and output_path.exists()
    
    def score_frame_as_title_card(self, frame_path: Path) -> Tuple[float, str]:
        """
        Score how likely a frame is to be a title card.
        
        Returns:
            (score, ocr_text) - score 0-1, higher = more likely to be title
        """
        try:
            img = Image.open(frame_path)
            img_array = np.array(img)
            
            # Run OCR
            results = self.reader.readtext(img_array, paragraph=False)
            
            # Combine text
            all_text = ' '.join([text for bbox, text, conf in results if conf > 0.2])
            
            score = 0.0
            
            # Positive indicators
            if 'pup' in all_text.lower():
                score += 0.3
            if any(word in all_text.lower() for word in ['save', 'stop', 'meet', 'rescue', 'solve']):
                score += 0.2
            if len(results) >= 2 and len(results) <= 8:  # Title cards usually have 2-8 text regions
                score += 0.2
            
            # Negative indicators
            if 'nickelodeon' in all_text.lower():
                score -= 0.2
            if any(word in all_text.lower() for word in ['written', 'produced', 'directed', 'executive']):
                score -= 0.3
            if len(results) > 10:  # Too much text, probably credits
                score -= 0.2
            
            return max(0.0, min(1.0, score)), all_text
            
        except Exception:
            return 0.0, ""
    
    def find_title_card_candidates(
        self,
        video_path: Path,
        output_dir: Path,
        max_candidates: int = 10,
        is_multi_episode: bool = False,
        quick_scan: bool = True,
        rescan_offset: float = 0.0
    ) -> List[dict]:
        """
        Find and extract likely title card frames.
        
        Args:
            video_path: Path to video file
            output_dir: Directory to save frame images
            max_candidates: Maximum number of candidates to return
            is_multi_episode: If True, search for multiple episodes
            quick_scan: If True, skip OCR scoring and just extract frames (much faster)
        
        Returns:
            List of candidate dicts with {timestamp, score, ocr_text, frame_path}
        """
        output_dir.mkdir(parents=True, exist_ok=True)
        
        duration = self.get_video_duration(video_path)
        
        if is_multi_episode:
            return self.find_title_card_candidates_multi_episode(video_path, output_dir, max_candidates, quick_scan, rescan_offset)
        
        # Single episode: use fast fixed time extraction
        print(f"  Extracting frames from first 52 seconds..." + (" (quick scan - no OCR)" if quick_scan else ""))
        
        # Get fixed times
        candidate_times = self._get_candidate_times(0, 52, duration, rescan_offset)
        
        if quick_scan:
            # Fast mode: extract frames without OCR scoring
            candidates = self._extract_frames_fast(video_path, candidate_times, output_dir, max_candidates)
        else:
            # Thorough mode: extract and score frames with OCR
            candidates = self._extract_and_score_frames(video_path, candidate_times, output_dir)
            # Sort by score
            candidates.sort(key=lambda x: x['score'], reverse=True)
            # Keep top candidates
            candidates = candidates[:max_candidates]
            # Delete non-top candidate frames to save space
            kept_paths = {c['frame_path'] for c in candidates}
            for c in candidates:
                if c['frame_path'] not in kept_paths and c['frame_path'].exists():
                    c['frame_path'].unlink()
        
        return candidates

    def find_title_card_candidates_multi_episode(
        self,
        video_path: Path,
        output_dir: Path,
        max_candidates: int = 10,
        quick_scan: bool = True,
        rescan_offset: float = 0.0
    ) -> List[dict]:
        """
        Find title card frames for multi-episode files (typically 2 episodes).
        Checks both episode windows independently.
        
        Args:
            video_path: Path to video file
            output_dir: Directory to save frame images
            max_candidates: Maximum number of candidates to return
            quick_scan: If True, skip OCR scoring (much faster)
            rescan_offset: Offset in seconds to shift timestamps for rescans
        
        Returns:
            List of candidate dicts with {timestamp, score, ocr_text, frame_path}
        """
        output_dir.mkdir(parents=True, exist_ok=True)
        
        duration = self.get_video_duration(video_path)
        all_candidates = []
        
        if quick_scan:
            # Fast mode: just extract key frames without OCR
            print("  Scanning Episode 1 (0-52s, quick scan)...")
            ep1_times = self._get_candidate_times(0, 52, duration, rescan_offset)
            all_candidates.extend(self._extract_frames_fast(video_path, ep1_times, output_dir, max_candidates))
            
            # Episode 2: Check around 42-50 minute mark
            if duration > 2400:  # At least 40 minutes
                print("  Scanning Episode 2 (42-52 min mark, quick scan)...")
                ep2_start = int(duration / 2 - 60)  # Estimate start of second episode
                ep2_end = min(int(ep2_start + 52), int(duration))
                ep2_times = self._get_candidate_times(ep2_start, ep2_end, duration, rescan_offset)
                all_candidates.extend(self._extract_frames_fast(video_path, ep2_times, output_dir, max_candidates))
        else:
            # Thorough mode: extract and score with OCR
            print("  Scanning Episode 1 (0-52s)...")
            ep1_times = self._get_candidate_times(0, 52, duration, rescan_offset)
            all_candidates.extend(self._extract_and_score_frames(video_path, ep1_times, output_dir))
            
            # Episode 2: Check around 42-50 minute mark
            if duration > 2400:  # At least 40 minutes
                print("  Scanning Episode 2 (42-52 min mark)...")
                ep2_start = int(duration / 2 - 60)  # Estimate start of second episode
                ep2_end = min(int(ep2_start + 52), int(duration))
                ep2_times = self._get_candidate_times(ep2_start, ep2_end, duration, rescan_offset)
                all_candidates.extend(self._extract_and_score_frames(video_path, ep2_times, output_dir))
            
            # Sort by score
            all_candidates.sort(key=lambda x: x['score'], reverse=True)
        
        # Keep top candidates
        top_candidates = all_candidates[:max_candidates]
        
        # Delete non-top candidate frames to save space
        kept_paths = {c['frame_path'] for c in top_candidates}
        for c in all_candidates:
            if c['frame_path'] not in kept_paths and c['frame_path'].exists():
                c['frame_path'].unlink()
        
        return top_candidates

    def _get_candidate_times(self, start_sec: int, end_sec: int, max_duration: float, offset: float = 0.0) -> List[float]:
        """Get candidate timestamps in a time window with optional offset for rescans."""
        # Common title card times
        common_times = [10, 12, 15, 18, 20, 25, 28, 30, 35, 38, 40, 42, 44, 46, 48, 50]
        
        # Apply offset to common times
        common_times = [t + offset for t in common_times]
        
        # Adjust common times to the window
        times = [t for t in common_times if start_sec <= t <= end_sec]
        
        # If window is outside the common range, use relative offsets
        if not times or end_sec > 200:
            times = [start_sec + offset + i for i in range(0, min(end_sec - start_sec, int(max_duration) - start_sec), 2)]
        
        # Add +0.5 second offset for each time (half-second variants)
        times_with_offset = []
        for t in times:
            times_with_offset.append(t)
            if t + 0.5 <= end_sec:
                times_with_offset.append(t + 0.5)
        
        return sorted(set(times_with_offset))

    def _extract_frames_fast(self, video_path: Path, timestamps: List[float], output_dir: Path, max_count: int = 6) -> List[dict]:
        """Extract frames quickly without OCR scoring (for rescan - much faster)."""
        candidates = []
        count = 0
        
        for ts in timestamps:
            if count >= max_count:
                break
            
            # Extract frame
            frame_path = output_dir / f"frame_{ts:06.1f}s.png"
            
            if not self.extract_frame(video_path, ts, frame_path):
                continue
            
            # Add without OCR scoring (huge speedup)
            candidates.append({
                'timestamp': ts,
                'score': 0.5,  # Default middle score - user will pick best one
                'ocr_text': '',
                'frame_path': frame_path
            })
            count += 1
        
        return candidates

    def _extract_and_score_frames(self, video_path: Path, timestamps: List[float], output_dir: Path) -> List[dict]:
        """Extract and score frames at given timestamps."""
        candidates = []
        
        for ts in timestamps:
            # Extract frame
            frame_path = output_dir / f"frame_{ts:06.1f}s.png"
            
            if not self.extract_frame(video_path, ts, frame_path):
                continue
            
            # Score it
            score, ocr_text = self.score_frame_as_title_card(frame_path)
            
            candidates.append({
                'timestamp': ts,
                'score': score,
                'ocr_text': ocr_text,
                'frame_path': frame_path
            })
        
        return candidates


def main():
    """Test the title card finder."""
    import sys
    
    if len(sys.argv) < 2:
        print("Usage: python visual_title_finder.py <video_file>")
        sys.exit(1)
    
    video_path = Path(sys.argv[1])
    
    if not video_path.exists():
        print(f"Error: Video file not found: {video_path}")
        sys.exit(1)
    
    print(f"\n{'='*80}")
    print(f"Finding title card candidates in: {video_path.name}")
    print('='*80 + "\n")
    
    finder = TitleCardFinder()
    
    # Create output directory
    output_dir = Path("title_card_candidates") / video_path.stem
    
    # Find candidates
    candidates = finder.find_title_card_candidates(video_path, output_dir, max_candidates=10)
    
    print(f"\n{'='*80}")
    print(f"Found {len(candidates)} title card candidates")
    print('='*80 + "\n")
    
    for i, candidate in enumerate(candidates, 1):
        print(f"{i}. Timestamp: {candidate['timestamp']:.1f}s")
        print(f"   Score: {candidate['score']:.2f}")
        print(f"   OCR: '{candidate['ocr_text'][:60]}'")
        print(f"   Frame: {candidate['frame_path']}")
        print()
    
    print(f"\n✓ Candidate frames saved to: {output_dir}")
    print(f"\nNext steps:")
    print(f"1. Open the frames in an image viewer")
    print(f"2. Identify which frame shows the episode title card")
    print(f"3. Note the timestamp of the correct frame")


if __name__ == '__main__':
    main()
