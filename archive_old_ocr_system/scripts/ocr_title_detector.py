#!/usr/bin/env python3
"""
Improved OCR title card detection and text extraction.

Handles:
- Case normalization (UPPERCASE → proper case)
- OCR character errors (P→D, S→5, l→1, etc.)
- Credits vs. title separation
- Multi-line title cards
- High-confidence text filtering
"""

import re
from typing import List, Tuple, Optional
from PIL import Image
import numpy as np
import easyocr
import pytesseract
from dataclasses import dataclass


@dataclass
class OCRRegion:
    """A single detected text region from OCR."""
    text: str
    confidence: float
    bbox: Optional[list] = None
    is_title: bool = False  # Detected as title (not credits)
    cleaned_text: str = ""  # Corrected version


# Common OCR character substitutions (for Paw Patrol title cards specifically)
OCR_CORRECTIONS = {
    'P': ['D', 'R'],  # PUPPS → Pups (P misread as D rare)
    'U': ['V', '∪'],
    'S': ['5', '$', 'Z'],  # SPLASH → SPLASH
    'l': ['1', '|', 'I'],  # lowercase l
    'O': ['0', 'Q'],
    'B': ['8', '3'],
    'Z': ['2', 'S'],
}

TITLE_INDICATORS = [
    'title', 'episode', 'presents',
]

CREDIT_KEYWORDS = [
    'written by',
    'produced by',
    'directed by',
    'executive producer',
    'animation',
    'storyboard',
    'character design',
    'music by',
    'voice',
    'guest star',
    'special thanks',
    'based on',
    '©',
    '®',
    'all rights',
]

FILLER_WORDS = [
    'and', 'a', 'the', 'an', 'or', 'in', 'to', 'for', 'of', 'by',
]


def normalize_case(text: str) -> str:
    """Convert all-caps or mixed case to proper title case.
    
    Examples:
        "PUPS MAKE A SPLASH" → "Pups Make A Splash"
        "pUPS mAKE a sPLASH" → "Pups Make A Splash"
    """
    # If text is ALL CAPS, convert to Title Case
    if text.isupper() and len(text) > 2:
        return ' '.join(word.capitalize() for word in text.split())
    
    # If text is all lowercase, convert to Title Case
    if text.islower() and len(text) > 2:
        return ' '.join(word.capitalize() for word in text.split())
    
    # Mixed case: leave as-is (probably already correct)
    return text


def correct_ocr_errors(text: str) -> str:
    """Correct common OCR character substitutions.
    
    This is a heuristic approach - tries to identify if characters were
    misread based on visual similarity and context.
    """
    # Split into words for analysis
    words = text.split()
    corrected_words = []
    
    for word in words:
        corrected_word = word
        
        # Common substitutions for Paw Patrol
        if 'UPP' in word.upper():  # PUPPS or similar
            corrected_word = word.replace('D', 'P').replace('R', 'P')
        
        # Numeric character confusion
        if '5' in word or '$' in word:
            corrected_word = corrected_word.replace('5', 'S').replace('$', 'S')
        
        if '0' in word or 'Q' in word.upper():
            # Only replace if surrounded by obvious letters
            if len(word) > 1:
                corrected_word = corrected_word.replace('0', 'O')
        
        if '1' in word:
            corrected_word = corrected_word.replace('1', 'l').replace('1', 'I')
        
        corrected_words.append(corrected_word)
    
    return ' '.join(corrected_words)


def is_credits_line(text: str) -> bool:
    """Determine if a line is credits text vs. title text."""
    text_lower = text.lower()
    
    # Check for credit keywords
    if any(kw in text_lower for kw in CREDIT_KEYWORDS):
        return True
    
    # "by" is a strong signal for credits
    if ' by ' in text_lower:
        return True
    
    # Very short text is likely a label, not a full credit line
    if len(text.strip()) < 3:
        return False
    
    return False


def extract_title_words(regions: List[OCRRegion]) -> List[str]:
    """Extract non-credit words from OCR regions, ordered top-to-bottom."""
    title_words = []
    
    # Filter to non-credit regions and extract words
    for region in regions:
        if is_credits_line(region.text):
            region.is_title = False
            continue
        
        region.is_title = True
        # Split into words and add
        words = region.text.split()
        title_words.extend(words)
    
    # Filter out common filler words (and, the, etc.)
    # BUT keep short titles like "A Day at the Beach"
    filtered = [w for w in title_words if w.lower() not in FILLER_WORDS or len(title_words) < 3]
    
    return filtered if filtered else title_words


def clean_ocr_text(text: str) -> str:
    """Clean OCR output: normalize case and fix character errors."""
    # Remove leading/trailing whitespace
    text = text.strip()
    
    # Replace multiple spaces with single space
    text = re.sub(r'\s+', ' ', text)
    
    # Normalize case
    text = normalize_case(text)
    
    # Fix OCR errors
    text = correct_ocr_errors(text)
    
    return text


def extract_regions_from_image(
    image_path,
    use_easyocr: bool = True,
) -> List[OCRRegion]:
    """Extract all text regions from an image using EasyOCR and/or Tesseract.
    
    Returns list of OCRRegion objects with position and confidence data.
    """
    img = Image.open(image_path)
    img_array = np.array(img)
    
    regions = []
    
    # Primary: EasyOCR (better for stylized text)
    if use_easyocr:
        try:
            if not hasattr(extract_regions_from_image, '_reader'):
                extract_regions_from_image._reader = easyocr.Reader(['en'], gpu=False, verbose=False)
            reader = extract_regions_from_image._reader
            
            ocr_results = reader.readtext(img_array)
            
            for bbox, text, confidence in ocr_results:
                if confidence > 0.25:  # Lower threshold to catch more text
                    region = OCRRegion(
                        text=text,
                        confidence=confidence,
                        bbox=bbox,
                        cleaned_text=clean_ocr_text(text),
                    )
                    regions.append(region)
        except Exception as e:
            # Fall back to Tesseract if EasyOCR fails
            pass
    
    # Fallback: Tesseract (more reliable for some fonts)
    if not regions:
        try:
            text = pytesseract.image_to_string(img, lang='eng', config='--psm 6')
            if text.strip():
                region = OCRRegion(
                    text=text,
                    confidence=0.7,  # Assume good confidence for Tesseract
                    cleaned_text=clean_ocr_text(text),
                )
                regions.append(region)
        except Exception as e:
            pass
    
    return regions


def find_title_region(
    regions: List[OCRRegion],
    known_titles: Optional[List[str]] = None,
) -> Tuple[Optional[str], float]:
    """
    Find the most likely title from detected regions.
    
    Returns (title_text, confidence_score 0-100).
    If known_titles provided, returns fuzzy match confidence.
    Otherwise returns OCR confidence.
    """
    if not regions:
        return None, 0.0
    
    # Separate title vs. credit regions
    title_regions = []
    credit_regions = []
    
    for r in regions:
        if is_credits_line(r.text):
            credit_regions.append(r)
        else:
            title_regions.append(r)
    
    if not title_regions:
        # No clear title regions, return None
        return None, 0.0
    
    # Sort by position (top-to-bottom, then left-to-right)
    if title_regions and title_regions[0].bbox:
        title_regions.sort(key=lambda r: (r.bbox[0][1] if r.bbox else 0, r.bbox[0][0] if r.bbox else 0))
    
    # Combine consecutive title regions that are likely part of the same title
    # Strategy: All title regions (non-credit) should be combined
    # This handles multi-box title cards where each word is a separate text region
    if title_regions:
        combined_regions = [title_regions]
    else:
        combined_regions = []
    
    best_title = None
    best_score = 0.0
    
    # Try each group of regions
    for group in combined_regions:
        # Combine text from all regions in the group
        combined_text = ' '.join([r.cleaned_text for r in group if r.cleaned_text])
        combined_confidence = sum(r.confidence for r in group) / len(group)
        
        if not combined_text or len(combined_text) < 3:
            continue
        
        # If we have known titles, score against them using fuzzy match
        if known_titles:
            from rapidfuzz import fuzz, process
            
            result = process.extractOne(
                combined_text,
                known_titles,
                scorer=fuzz.token_sort_ratio,
                score_cutoff=35,
            )
            
            if result:
                matched_title, fuzzy_score, _ = result
                # Use fuzzy score (0-100)
                if fuzzy_score > best_score:
                    best_score = fuzzy_score
                    best_title = matched_title
        else:
            # No known titles, use OCR confidence scaled to 0-100
            if combined_confidence * 100 > best_score:
                best_score = combined_confidence * 100
                best_title = combined_text
    
    return best_title, best_score


def extract_title_from_frame(
    image_path,
    known_titles: Optional[List[str]] = None,
    verbose: bool = False,
) -> Tuple[Optional[str], float, List[OCRRegion]]:
    """
    Extract episode title from a frame image.
    
    Returns (title, confidence, all_regions).
    """
    regions = extract_regions_from_image(image_path, use_easyocr=True)
    
    if verbose:
        print(f"Found {len(regions)} text regions:")
        for i, region in enumerate(regions):
            is_credit = "CREDIT" if is_credits_line(region.text) else "TITLE"
            print(f"  {i+1}. [{is_credit}] '{region.cleaned_text}' (conf: {region.confidence:.2f})")
    
    title, confidence = find_title_region(regions, known_titles)
    
    return title, confidence, regions
