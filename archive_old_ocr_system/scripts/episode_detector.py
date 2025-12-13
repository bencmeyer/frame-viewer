#!/usr/bin/env python3
"""
Complete Episode Detection System
Scans video files using OCR to detect actual episode content.
"""

import subprocess
import tempfile
from pathlib import Path
from typing import List, Dict, Tuple, Optional
import numpy as np
from PIL import Image
import easyocr

from title_matcher import OCRFragment, TitleMatch, detect_episode_from_ocr

# Title card timestamps (seconds into video)
FIRST_EPISODE_TIMESTAMP = 44
SECOND_EPISODE_TIMESTAMP = 700  # ~11:40 for second episode in multi-ep files

class EpisodeDetector:
    """Detects actual episode content from video files using OCR."""
    
    def __init__(self, episode_database: Dict[Tuple[int, int], Dict], use_gpu: bool = True):
        """
        Initialize detector.
        
        Args:
            episode_database: Dict mapping (season, episode) -> {"title": str, ...}
            use_gpu: Whether to use GPU acceleration for OCR
        """
        self.episode_database = episode_database
        self.reader = easyocr.Reader(['en'], gpu=use_gpu, verbose=False)
    
    def extract_frame(self, video_path: Path, timestamp: int) -> Optional[Path]:
        """
        Extract a single frame from video at specified timestamp.
        
        Args:
            video_path: Path to video file
            timestamp: Time in seconds
        
        Returns:
            Path to extracted frame PNG, or None if failed
        """
        try:
            # Create temp file for frame
            temp_file = tempfile.NamedTemporaryFile(suffix='.png', delete=False)
            temp_path = Path(temp_file.name)
            temp_file.close()
            
            # Extract frame using ffmpeg
            cmd = [
                'ffmpeg',
                '-ss', str(timestamp),
                '-i', str(video_path),
                '-vframes', '1',
                '-y',
                str(temp_path)
            ]
            
            result = subprocess.run(
                cmd,
                capture_output=True,
                timeout=10,
                text=True
            )
            
            if result.returncode != 0:
                print(f"Warning: ffmpeg failed for {video_path} at {timestamp}s")
                return None
            
            if not temp_path.exists():
                return None
            
            return temp_path
            
        except Exception as e:
            print(f"Error extracting frame from {video_path}: {e}")
            return None
    
    def ocr_frame(self, frame_path: Path) -> List[OCRFragment]:
        """
        Run OCR on a frame image.
        
        Args:
            frame_path: Path to frame PNG
        
        Returns:
            List of detected text fragments
        """
        try:
            # Load image
            img = Image.open(frame_path)
            img_array = np.array(img)
            
            # Run OCR
            results = self.reader.readtext(img_array, paragraph=False)
            
            # Convert to OCRFragment objects
            fragments = []
            for bbox, text, conf in results:
                fragments.append(OCRFragment(
                    text=text,
                    confidence=conf,
                    bbox=bbox
                ))
            
            return fragments
            
        except Exception as e:
            print(f"Error running OCR on {frame_path}: {e}")
            return []
    
    def detect_episode_at_timestamp(
        self,
        video_path: Path,
        season: int,
        timestamp: int
    ) -> Optional[TitleMatch]:
        """
        Detect episode from video at specific timestamp.
        
        Args:
            video_path: Path to video file
            season: Season number
            timestamp: Time in seconds to extract frame
        
        Returns:
            TitleMatch if episode detected, None otherwise
        """
        # Extract frame
        frame_path = self.extract_frame(video_path, timestamp)
        if not frame_path:
            return None
        
        try:
            # Run OCR
            fragments = self.ocr_frame(frame_path)
            
            if not fragments:
                return None
            
            # Match to episode
            match = detect_episode_from_ocr(
                fragments,
                self.episode_database,
                season
            )
            
            return match
            
        finally:
            # Cleanup temp frame
            if frame_path and frame_path.exists():
                frame_path.unlink()
    
    def detect_episodes_in_file(
        self,
        video_path: Path,
        season: int
    ) -> Dict[str, Optional[TitleMatch]]:
        """
        Detect all episodes in a video file (handles multi-episode files).
        
        Args:
            video_path: Path to video file
            season: Season number
        
        Returns:
            Dict with 'first_episode' and 'second_episode' keys
        """
        result = {
            'first_episode': None,
            'second_episode': None
        }
        
        # Detect first episode (always present)
        print(f"  Checking first episode at {FIRST_EPISODE_TIMESTAMP}s...")
        result['first_episode'] = self.detect_episode_at_timestamp(
            video_path,
            season,
            FIRST_EPISODE_TIMESTAMP
        )
        
        # Detect second episode (if multi-episode file)
        print(f"  Checking second episode at {SECOND_EPISODE_TIMESTAMP}s...")
        result['second_episode'] = self.detect_episode_at_timestamp(
            video_path,
            season,
            SECOND_EPISODE_TIMESTAMP
        )
        
        return result


def parse_filename_episodes(filename: str) -> Tuple[Optional[int], List[int]]:
    """
    Parse season and episode numbers from filename.
    
    Args:
        filename: Video filename
    
    Returns:
        (season, [episode_numbers])
    """
    import re
    
    # Match S##E##-E## or S##E##
    pattern = r'S(\d+)E(\d+)(?:-E(\d+))?'
    match = re.search(pattern, filename, re.IGNORECASE)
    
    if not match:
        return None, []
    
    season = int(match.group(1))
    first_ep = int(match.group(2))
    
    if match.group(3):
        second_ep = int(match.group(3))
        return season, [first_ep, second_ep]
    else:
        return season, [first_ep]


def format_episode_range(episodes: List[int]) -> str:
    """Format episode numbers as S##E##-E## string."""
    if not episodes:
        return ""
    if len(episodes) == 1:
        return f"E{episodes[0]:02d}"
    else:
        return f"E{episodes[0]:02d}-E{episodes[1]:02d}"
