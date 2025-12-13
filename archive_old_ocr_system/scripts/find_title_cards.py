#!/usr/bin/env python3
"""
Systematic title card finder - scans many frames to find where title cards appear.
Helps us learn the timing patterns for Paw Patrol episodes.
"""

import os
import subprocess
import tempfile
import sys
from PIL import Image
import easyocr
import numpy as np

def extract_frame(video_path: str, time_seconds: float) -> str:
    """Extract frame and return path."""
    try:
        tmp_path = tempfile.mktemp(suffix=".png")
        cmd = [
            "ffmpeg", "-ss", str(time_seconds), "-i", video_path,
            "-vframes", "1", "-y", tmp_path
        ]
        subprocess.run(cmd, capture_output=True, timeout=10, stderr=subprocess.DEVNULL, stdout=subprocess.DEVNULL)
        if os.path.exists(tmp_path):
            return tmp_path
    except:
        pass
    return None

def analyze_frame_for_title(image_path: str, reader) -> dict:
    """Analyze a frame and return OCR results."""
    try:
        img = Image.open(image_path)
        img_array = np.array(img)
        
        results = reader.readtext(img_array, paragraph=False)
        
        # Collect all text with good confidence
        good_text = []
        for bbox, text, conf in results:
            if conf > 0.5:  # Only high-confidence text
                text_clean = text.strip()
                if len(text_clean) > 3:  # Skip tiny fragments
                    good_text.append({
                        'text': text_clean,
                        'confidence': conf
                    })
        
        return {
            'has_text': len(good_text) > 0,
            'text_regions': good_text,
            'full_text': ' '.join([t['text'] for t in good_text])
        }
    except Exception as e:
        return {'has_text': False, 'text_regions': [], 'full_text': '', 'error': str(e)}

def main():
    if len(sys.argv) < 2:
        print("Usage: find_title_cards.py <video_file>")
        sys.exit(1)
    
    video_path = sys.argv[1]
    if not os.path.exists(video_path):
        print(f"❌ File not found: {video_path}")
        sys.exit(1)
    
    print("Loading OCR model (with GPU)...")
    reader = easyocr.Reader(['en'], gpu=True, verbose=False)
    
    filename = os.path.basename(video_path)
    print(f"\n📹 {filename[:70]}")
    print("\nScanning frames every 5 seconds to find title cards...")
    print("=" * 80)
    
    # Get video duration
    duration_cmd = [
        "ffprobe", "-v", "error", "-show_entries", "format=duration",
        "-of", "default=noprint_wrappers=1:nokey=1", video_path
    ]
    result = subprocess.run(duration_cmd, capture_output=True, text=True, timeout=10)
    duration = float(result.stdout.strip())
    
    print(f"Duration: {duration:.0f}s ({duration/60:.1f} min)\n")
    
    # Scan every 5 seconds, focusing on first 2 minutes and midpoint
    scan_times = []
    # First episode title card (typically 10-60 seconds in)
    scan_times.extend(range(10, 90, 5))
    # Second episode title card (typically around 11-13 minutes in)
    mid_point = int(duration / 2)
    scan_times.extend(range(mid_point - 60, mid_point + 60, 5))
    
    found_titles = []
    
    for time_sec in scan_times:
        if time_sec > duration:
            break
        
        frame_path = extract_frame(video_path, time_sec)
        if not frame_path:
            continue
        
        result = analyze_frame_for_title(frame_path, reader)
        
        if result['has_text']:
            text = result['full_text']
            
            # Look for episode title indicators
            has_pups = 'pup' in text.lower()
            has_save = 'save' in text.lower() or 'stop' in text.lower()
            likely_title = has_pups and (has_save or len(text) > 15)
            
            if likely_title:
                print(f"\n⭐ t={time_sec:3d}s: LIKELY TITLE CARD")
                print(f"   Full text: {text[:70]}")
                for region in result['text_regions']:
                    print(f"   - {region['text']} (conf: {region['confidence']:.2f})")
                found_titles.append({
                    'time': time_sec,
                    'text': text
                })
            else:
                # Just show we scanned it
                print(f"t={time_sec:3d}s: {text[:50] if text else '(no text)'}", end='\r')
        else:
            print(f"t={time_sec:3d}s: (no text)", end='\r')
        
        # Clean up
        try:
            os.remove(frame_path)
        except:
            pass
    
    print("\n\n" + "=" * 80)
    print("SUMMARY - LIKELY TITLE CARDS FOUND:")
    print("=" * 80)
    
    if found_titles:
        for i, title_info in enumerate(found_titles, 1):
            print(f"{i}. t={title_info['time']}s: {title_info['text'][:65]}")
    else:
        print("❌ No title cards detected")
        print("\nTry:")
        print("1. Checking frames manually at different timestamps")
        print("2. Adjusting scan times based on episode structure")

if __name__ == "__main__":
    main()
