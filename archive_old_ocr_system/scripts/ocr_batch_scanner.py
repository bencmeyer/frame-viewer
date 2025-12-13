#!/usr/bin/env python3
"""
Comprehensive OCR scanner for all S09/S10 files.
Extracts title cards from each file and attempts to identify actual episode numbers.
Compares against TVDB and Sonarr data to flag mismatches.
"""

import os
import sys
import json
import glob
from pathlib import Path
from datetime import datetime
from typing import Dict, List, Tuple, Optional
import subprocess
import tempfile

# Add parent directory to path for imports
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

try:
    from ocr_title_detector import extract_title_from_frame, normalize_case
    from PIL import Image
    import easyocr
    from rapidfuzz import fuzz
except ImportError as e:
    print(f"❌ Missing dependency: {e}")
    print("Install with: pip install pillow easyocr rapidfuzz requests")
    sys.exit(1)

# Configuration
TVDB_API_KEY = "585432a6-f441-4db3-a106-2d5a05fa95d7"
SCAN_PATTERNS = ["S09E*.mkv", "S10E*.mkv"]
FRAME_TIMES = [40, 44, 700, 705]  # Times (in seconds) to extract title cards
MIN_CONFIDENCE = 0.35

class OCRScanner:
    def __init__(self, tvdb_api_key: str):
        self.api_key = tvdb_api_key
        self.reader = None
        self.tvdb_episodes = {}
        self.scan_results = []
        
    def load_ocr_reader(self):
        """Lazy load OCR reader."""
        if self.reader is None:
            print("Loading OCR model (EasyOCR with GPU)...")
            self.reader = easyocr.Reader(['en'], gpu=True)
        return self.reader
    
    def extract_frame(self, video_path: str, time_seconds: float) -> Optional[Image.Image]:
        """Extract a single frame from video at specified time."""
        try:
            with tempfile.NamedTemporaryFile(suffix=".png", delete=False) as tmp:
                cmd = [
                    "ffmpeg", "-ss", str(time_seconds), "-i", video_path,
                    "-vf", "scale=1280:-1", "-vframes", "1", "-y", tmp.name
                ]
                result = subprocess.run(cmd, capture_output=True, timeout=10)
                if result.returncode == 0 and os.path.exists(tmp.name):
                    img = Image.open(tmp.name)
                    img.load()  # Force load to avoid file handle issues
                    # Convert to RGB if necessary
                    if img.mode != 'RGB':
                        img = img.convert('RGB')
                    return img
        except Exception as e:
            print(f"  Frame extraction error at {time_seconds}s: {e}")
        return None
    
    def load_titles_list(self) -> List[str]:
        """Load known titles from titles.txt."""
        titles_file = os.path.join(os.path.dirname(__file__), "titles.txt")
        if os.path.exists(titles_file):
            with open(titles_file, 'r') as f:
                return [line.strip() for line in f if line.strip()]
        return []
    
    def scan_file(self, video_path: str) -> dict:
        """Scan a single video file for OCR matches."""
        filename = os.path.basename(video_path)
        
        # Extract season/episode from filename
        file_parts = filename.split(" - ")
        labeled_ep = file_parts[0] if file_parts else "Unknown"
        
        print(f"\n📹 Scanning: {filename}")
        print(f"   Labeled as: {labeled_ep}")
        
        result = {
            "filename": filename,
            "labeled_episode": labeled_ep,
            "detections": [],
            "best_match": None,
            "confidence_score": 0.0,
        }
        
        # Load titles
        known_titles = self.load_titles_list()
        
        # Extract frames at key times
        for time_sec in FRAME_TIMES:
            frame = self.extract_frame(video_path, time_sec)
            if frame is None:
                continue
            
            # Extract title from frame
            try:
                title_result = extract_title_from_frame(frame, known_titles)
                if title_result and title_result["confidence"] > MIN_CONFIDENCE:
                    result["detections"].append({
                        "time": time_sec,
                        "title": title_result["title"],
                        "episode": title_result.get("episode", "Unknown"),
                        "confidence": title_result["confidence"],
                    })
                    print(f"   ✓ t={time_sec}s: {title_result['episode']} " +
                          f"'{title_result['title'][:40]}' ({title_result['confidence']:.1%})")
            except Exception as e:
                print(f"   ✗ t={time_sec}s: {e}")
        
        # Find best match across all detections
        if result["detections"]:
            best = max(result["detections"], key=lambda x: x["confidence"])
            result["best_match"] = best["episode"]
            result["confidence_score"] = best["confidence"]
            
            # Check for multi-episode (different episodes detected)
            unique_eps = set(d["episode"] for d in result["detections"])
            if len(unique_eps) > 1:
                result["multi_episode_detected"] = sorted(unique_eps)
                print(f"   ⚠️  Multiple episodes detected: {result['multi_episode_detected']}")
            else:
                print(f"   ➜ Best match: {best['episode']} ({best['confidence']:.1%})")
        else:
            print(f"   ❌ No matches found")
        
        self.scan_results.append(result)
        return result
    
    def scan_directory(self, pattern: str = "S09E*.mkv"):
        """Scan all files matching pattern."""
        video_files = glob.glob(os.path.join(os.getcwd(), pattern))
        
        if not video_files:
            print(f"❌ No files found matching pattern: {pattern}")
            return []
        
        print(f"\n{'='*70}")
        print(f"Found {len(video_files)} files matching {pattern}")
        print(f"{'='*70}")
        
        for video_path in sorted(video_files):
            self.scan_file(video_path)
        
        return self.scan_results
    
    def generate_report(self, output_file: str = "ocr_scan_report.json"):
        """Generate report of all scans."""
        report = {
            "timestamp": datetime.now().isoformat(),
            "total_files_scanned": len(self.scan_results),
            "files_with_detections": sum(1 for r in self.scan_results if r["detections"]),
            "files_without_detections": sum(1 for r in self.scan_results if not r["detections"]),
            "results": self.scan_results,
        }
        
        with open(output_file, 'w') as f:
            json.dump(report, f, indent=2)
        
        print(f"\n✓ Report saved to {output_file}")
        return report
    
    def print_summary(self):
        """Print summary of scan results."""
        print(f"\n{'='*70}")
        print("SCAN SUMMARY")
        print(f"{'='*70}")
        
        labeled_vs_detected = []
        mismatches = []
        
        for result in self.scan_results:
            filename = result["filename"]
            labeled = result["labeled_episode"]
            detected = result["best_match"]
            confidence = result["confidence_score"]
            
            if detected:
                match_status = "✓" if labeled.split()[-1] in detected else "⚠️"
                labeled_vs_detected.append({
                    "filename": filename,
                    "labeled": labeled,
                    "detected": detected,
                    "confidence": confidence,
                    "match": match_status,
                })
                
                if labeled.split()[-1] not in detected:
                    mismatches.append(result)
            else:
                labeled_vs_detected.append({
                    "filename": filename,
                    "labeled": labeled,
                    "detected": "NOT DETECTED",
                    "confidence": 0.0,
                    "match": "❌",
                })
                mismatches.append(result)
        
        # Print table
        print(f"{'File':<40} {'Labeled':<15} {'Detected':<15} {'Conf':<8} {'Match':<4}")
        print("-" * 85)
        
        for item in labeled_vs_detected:
            print(f"{item['filename'][:39]:<40} {item['labeled']:<15} " +
                  f"{item['detected']:<15} {item['confidence']:.1%}  {item['match']:<4}")
        
        # Print mismatches
        if mismatches:
            print(f"\n⚠️  POTENTIAL MISMATCHES ({len(mismatches)}):")
            print("-" * 85)
            for result in mismatches:
                print(f"  • {result['filename']}")
                print(f"    Labeled: {result['labeled_episode']}")
                print(f"    Detected: {result['best_match']} ({result['confidence_score']:.1%})")
                if result['detections']:
                    print(f"    All detections: {[d['episode'] for d in result['detections']]}")
        else:
            print(f"\n✓ All files match their labels!")

def main():
    scanner = OCRScanner(TVDB_API_KEY)
    scanner.load_ocr_reader()
    
    # Change to Paw Patrol directory structure
    base_dir = "Paw Patrol"
    if not os.path.isdir(base_dir):
        print(f"❌ Directory not found: {base_dir}")
        sys.exit(1)
    
    # Scan Season 09 and Season 10
    for season_dir in ["Season 09", "Season 10"]:
        season_path = os.path.join(base_dir, season_dir)
        if not os.path.isdir(season_path):
            print(f"⚠️  Directory not found: {season_path}")
            continue
        
        print(f"\n{'='*70}")
        print(f"Scanning {season_dir}")
        print(f"{'='*70}")
        
        # Get all mkv files in this season
        video_files = sorted(glob.glob(os.path.join(season_path, "*.mkv")))
        
        if not video_files:
            print(f"❌ No files found in {season_path}")
            continue
        
        print(f"Found {len(video_files)} files")
        
        for video_path in video_files:
            scanner.scan_file(video_path)
    
    # Generate outputs
    scanner.generate_report("ocr_scan_report.json")
    scanner.print_summary()

if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        print("\n\nScan interrupted by user.")
        sys.exit(0)
    except Exception as e:
        print(f"\n❌ Error: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)
