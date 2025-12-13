#!/usr/bin/env python3
"""
Enhanced episode detector that tries multiple timestamps and picks best match.
"""

from pathlib import Path
from typing import List, Dict, Optional, Tuple
import subprocess
import tempfile
from PIL import Image
import numpy as np
import easyocr

from title_matcher import OCRFragment, detect_episode_from_ocr, TitleMatch

class SmartEpisodeDetector:
    """Detects episodes by trying multiple timestamps and validating results."""
    
    # Timestamps to check (seconds)
    TITLE_CARD_SEARCH_TIMES = [
        # Early intro/title
        10, 12, 15, 18, 20, 25, 28, 30, 32, 35, 38, 40, 42, 44, 46, 48, 50,
        # Mid-episode (for second episode in dual files)
        680, 690, 700, 710, 720, 730, 740
    ]
    
    def __init__(self, episode_database: Dict[Tuple[int, int], Dict], use_gpu: bool = True):
        self.episode_database = episode_database
        self.reader = easyocr.Reader(['en'], gpu=use_gpu, verbose=False)
    
    def extract_frame(self, video_path: Path, timestamp: int) -> Optional[Path]:
        """Extract frame at timestamp."""
        try:
            temp_file = tempfile.NamedTemporaryFile(suffix='.png', delete=False)
            temp_path = Path(temp_file.name)
            temp_file.close()
            
            cmd = [
                'ffmpeg', '-ss', str(timestamp), '-i', str(video_path),
                '-vframes', '1', '-y', str(temp_path)
            ]
            
            result = subprocess.run(cmd, capture_output=True, timeout=10)
            
            if result.returncode != 0 or not temp_path.exists():
                return None
            
            return temp_path
        except Exception:
            return None
    
    def ocr_frame(self, frame_path: Path) -> List[OCRFragment]:
        """Run OCR on frame."""
        try:
            img = Image.open(frame_path)
            img_array = np.array(img)
            results = self.reader.readtext(img_array, paragraph=False)
            
            fragments = []
            for bbox, text, conf in results:
                fragments.append(OCRFragment(text=text, confidence=conf, bbox=bbox))
            
            return fragments
        except Exception:
            return []
    
    def detect_best_episode(
        self,
        video_path: Path,
        season: int,
        expected_episodes: Optional[List[int]] = None
    ) -> Optional[TitleMatch]:
        """
        Try multiple timestamps and return best match.
        
        Args:
            video_path: Path to video
            season: Season number
            expected_episodes: Expected episode numbers from filename (for validation)
        
        Returns:
            Best TitleMatch found, or None
        """
        candidates = []
        
        # Try first episode timestamps
        for ts in self.TITLE_CARD_SEARCH_TIMES[:17]:  # First 17 are for episode 1
            frame_path = self.extract_frame(video_path, ts)
            if not frame_path:
                continue
            
            try:
                fragments = self.ocr_frame(frame_path)
                
                if fragments:
                    match = detect_episode_from_ocr(
                        fragments,
                        self.episode_database,
                        season,
                        min_confidence=0.25,  # Lower threshold to catch more
                        min_match_score=0.45   # Lower threshold
                    )
                    
                    if match:
                        # Score bonus if matches expected episode
                        bonus = 0.0
                        if expected_episodes and match.episode_number in expected_episodes:
                            bonus = 0.2
                        
                        candidates.append({
                            'match': match,
                            'timestamp': ts,
                            'score': match.confidence + bonus
                        })
            finally:
                if frame_path.exists():
                    frame_path.unlink()
        
        if not candidates:
            return None
        
        # Return highest scoring match
        best = max(candidates, key=lambda x: x['score'])
        
        # If we have expected episodes, prefer matches that agree
        if expected_episodes:
            matching_candidates = [c for c in candidates 
                                  if c['match'].episode_number in expected_episodes]
            if matching_candidates:
                best = max(matching_candidates, key=lambda x: x['score'])
        
        return best['match']
    
    def detect_episodes_in_file(
        self,
        video_path: Path,
        season: int,
        expected_episodes: Optional[List[int]] = None
    ) -> Dict[str, Optional[TitleMatch]]:
        """Detect all episodes in file."""
        result = {
            'first_episode': None,
            'second_episode': None
        }
        
        # Detect first episode
        print(f"  Searching for first episode title card...")
        result['first_episode'] = self.detect_best_episode(
            video_path,
            season,
            expected_episodes[:1] if expected_episodes else None
        )
        
        # TODO: Detect second episode for multi-ep files
        # Would use timestamps 680-740
        
        return result
