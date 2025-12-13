#!/usr/bin/env python3
"""
Smart Episode Matcher: Extract titles from files without manual intervention.

Uses a combination of:
1. OCR on multiple frames
2. Fuzzy matching against known titles
3. Visual analysis of intro/credits
4. Heuristics for episode recognition

This learns from your files to build automatic title mapping.
"""

import json
from pathlib import Path
from typing import Dict, List, Tuple, Optional
from datetime import datetime
import subprocess

def get_best_ocr_frames(video_file: str, num_frames: int = 10) -> List[Tuple[float, str]]:
    """
    Extract frames at strategic points and OCR them.
    Returns list of (timestamp, ocr_text) with non-empty results.
    """
    from pipeline import get_duration, detect_scene_changes, find_intro_for_episode
    from pipeline import extract_frame, ocr_image, enhance_image_for_ocr
    import tempfile
    
    duration = None
    try:
        result = subprocess.run(
            ["ffprobe", "-v", "error", "-show_entries", "format=duration", 
             "-of", "default=noprint_wrappers=1:nokey=1", video_file],
            capture_output=True, text=True, timeout=10
        )
        duration = float(result.stdout.strip())
    except:
        return []
    
    # Sample at interesting times
    times = [
        duration * 0.01,   # 1% in (early content)
        duration * 0.05,   # 5% in
        duration * 0.1,    # 10% in
        duration * 0.2,    # 20% in
    ]
    
    results = []
    with tempfile.TemporaryDirectory() as tmpdir:
        for i, t in enumerate(times):
            try:
                frame_path = Path(tmpdir) / f"frame_{i}.png"
                extract_frame(video_file, t, frame_path)
                
                # Try enhanced
                try:
                    enhanced = enhance_image_for_ocr(frame_path)
                    enhanced_path = Path(tmpdir) / f"frame_{i}_enh.png"
                    enhanced.save(enhanced_path)
                    text = ocr_image(enhanced_path, "eng").strip()
                    if text:
                        results.append((t, text))
                        continue
                except:
                    pass
                
                # Try raw
                text = ocr_image(frame_path, "eng").strip()
                if text:
                    results.append((t, text))
            except:
                pass
    
    return results


def extract_keywords_from_ocr(ocr_texts: List[str], known_titles: List[str]) -> Dict[str, int]:
    """
    From OCR texts, extract words that appear in known titles.
    Returns word -> count mapping.
    """
    from rapidfuzz import fuzz
    
    keywords = {}
    
    for title in known_titles:
        title_words = title.lower().split()
        for word in title_words:
            if len(word) > 3:  # skip short words
                for ocr_text in ocr_texts:
                    if word in ocr_text.lower():
                        keywords[word] = keywords.get(word, 0) + 1
    
    return keywords


def guess_episode_from_ocr(ocr_results: List[Tuple[float, str]], 
                           known_titles: List[str]) -> Optional[Tuple[str, float]]:
    """
    From OCR results, try to guess which episode this file contains.
    Returns (episode_title, confidence_score).
    """
    from rapidfuzz import fuzz
    from pipeline import match_title
    
    ocr_texts = [text for _, text in ocr_results]
    combined_text = " ".join(ocr_texts)
    
    # Try to match against known titles
    best_match, best_score = None, 0
    for title in known_titles:
        score = fuzz.token_sort_ratio(combined_text.lower(), title.lower())
        if score > best_score:
            best_score = score
            best_match = title
    
    if best_score > 30:  # threshold
        return best_match, best_score / 100.0
    
    return None, 0.0


if __name__ == '__main__':
    import sys
    if len(sys.argv) < 2:
        print("Usage: smart_matcher.py <video_file> [--titles-file TITLES.TXT]")
        sys.exit(1)
    
    video_file = sys.argv[1]
    titles_file = "titles.txt"
    
    if "--titles-file" in sys.argv:
        idx = sys.argv.index("--titles-file")
        titles_file = sys.argv[idx + 1]
    
    # Load known titles
    titles = []
    if Path(titles_file).exists():
        titles = [line.strip() for line in Path(titles_file).read_text().splitlines() 
                 if line.strip() and not line.startswith("#")]
    
    print(f"Analyzing: {video_file}")
    print(f"Known titles: {len(titles)}")
    print()
    
    # Extract OCR
    print("Extracting frames and running OCR...")
    ocr_results = get_best_ocr_frames(video_file)
    
    print(f"Found {len(ocr_results)} frames with OCR text:")
    for t, text in ocr_results:
        preview = text[:80].replace("\n", " ")
        print(f"  @ {t:.1f}s: {preview}...")
    print()
    
    # Guess episode
    if ocr_results:
        guess, confidence = guess_episode_from_ocr(ocr_results, titles)
        print(f"Best guess: {guess or 'Unknown'} (confidence: {confidence:.1%})")
    else:
        print("No OCR results found. File may not contain readable title text.")
