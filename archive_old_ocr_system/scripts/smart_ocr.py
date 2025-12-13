#!/usr/bin/env python3
"""
Smart episode detection using title card analysis.
Attempts to find and OCR the actual episode title cards.
"""

import os
import subprocess
import tempfile
import sys
from pathlib import Path
from PIL import Image
import easyocr

def extract_frame(video_path: str, time_seconds: float) -> str:
    """Extract frame and return path."""
    try:
        tmp_path = tempfile.mktemp(suffix=".png")
        cmd = [
            "ffmpeg", "-ss", str(time_seconds), "-i", video_path,
            "-vframes", "1", "-y", tmp_path
        ]
        subprocess.run(cmd, capture_output=True, timeout=10)
        if os.path.exists(tmp_path):
            return tmp_path
    except:
        pass
    return None

def simple_ocr(image_path: str, reader) -> str:
    """Simple OCR - just get raw text."""
    try:
        img = Image.open(image_path)
        img_array = __import__('numpy').array(img)
        
        results = reader.readtext(img_array)
        text_parts = [text for _, text, _ in results]
        return ' '.join(text_parts)
    except:
        return ""

def main():
    if len(sys.argv) < 2:
        print("Usage: smart_ocr.py <video_file>")
        sys.exit(1)
    
    video_path = sys.argv[1]
    if not os.path.exists(video_path):
        print(f"❌ File not found: {video_path}")
        sys.exit(1)
    
    print(f"Loading OCR model...")
    reader = easyocr.Reader(['en'], gpu=True, verbose=False)
    
    filename = os.path.basename(video_path)
    print(f"\n📹 Analyzing: {filename[:60]}")
    
    # Paw Patrol episodes are typically:
    # - 0-5s: Logos/intro
    # - 5-15s: Opening theme
    # - 15-20s: First title card appears
    # - ~12 min into file: Second episode title card
    
    scan_times = [
        (15, "Early title card (Episode 1)"),
        (20, "Title card region"),
        (30, "Title card region"),
        (700, "Mid-file (Episode 2 title)"),
        (710, "Title card region"),
        (720, "Title card region"),
    ]
    
    print("\nScanning for episode titles:")
    print("=" * 70)
    
    detections = {}
    for time_sec, description in scan_times:
        frame_path = extract_frame(video_path, time_sec)
        if not frame_path:
            continue
        
        raw_text = simple_ocr(frame_path, reader)
        
        # Filter to lines that look like episode titles
        lines = [l.strip() for l in raw_text.split('\n') if l.strip() and len(l.strip()) > 5]
        
        # Look for "Pups" keyword (most Paw Patrol episodes start with "Pups")
        pups_lines = [l for l in lines if 'Pup' in l or 'pup' in l]
        
        if pups_lines:
            print(f"\nt={time_sec:3d}s ({description}):")
            for line in pups_lines[:2]:
                print(f"  → {line[:65]}")
                if line not in detections:
                    detections[line] = []
                detections[line].append(time_sec)
    
    # Summary
    print("\n" + "=" * 70)
    print("DETECTED EPISODE TITLES:")
    print("=" * 70)
    
    if detections:
        for title, times in sorted(detections.items(), key=lambda x: len(x[1]), reverse=True):
            print(f"'{title[:60]}' (found at {len(times)} frame(s): {times})")
    else:
        print("❌ No episode titles detected")

if __name__ == "__main__":
    main()
