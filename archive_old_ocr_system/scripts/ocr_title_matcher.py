#!/usr/bin/env python3
"""
OCR Title Matcher - Robust fuzzy matching for episode titles from OCR text.

This module handles:
- OCR error correction (common character substitutions)
- Credits text filtering
- Multi-fragment text combination
- Fuzzy matching against TVDB episode titles
- Confidence scoring
"""

import re
from typing import List, Dict, Optional, Tuple
from dataclasses import dataclass
from rapidfuzz import fuzz, process


@dataclass
class OCRFragment:
    """Represents a single OCR text detection."""
    text: str
    confidence: float
    bbox: Optional[List] = None


@dataclass
class TitleMatch:
    """Represents a matched episode title."""
    matched_title: str
    episode_number: int
    confidence: float
    raw_ocr: str
    season_number: Optional[int] = None
    
    def to_dict(self) -> Dict:
        """Convert to dictionary format."""
        return {
            "matched_title": self.matched_title,
            "episode_number": self.episode_number,
            "confidence": self.confidence,
            "raw_ocr": self.raw_ocr,
            "season_number": self.season_number
        }


class OCRTitleMatcher:
    """Matches OCR text fragments against episode titles using fuzzy matching."""
    
    # Common OCR character substitution errors
    OCR_CORRECTIONS = {
        # Letter substitutions
        'SAT': 'SAVE',
        'SATE': 'SAVE',
        'SAV': 'SAVE',
        'QEEQ': 'QUEEN',
        'QEEN': 'QUEEN',
        'OUEEN': 'QUEEN',
        '0': 'O',  # Number zero to letter O
        '1': 'I',  # Number one to letter I
        '5': 'S',  # Number five to letter S
        '8': 'B',  # Number eight to letter B
        
        # Common word-level errors
        'PIJPS': 'PUPS',
        'PLIPS': 'PUPS',
        'PLJPS': 'PUPS',
        'PIUPS': 'PUPS',
        
        # Character-level substitutions
        'IJ': 'U',
        'LI': 'U',
        'RN': 'M',
        'VV': 'W',
        '|': 'I',
        '!': 'I',
        
        # Common misreads
        'TOOIH': 'TOOTH',
        'T00TH': 'TOOTH',
        'FAIRY': 'FAIRY',
        'FAJRY': 'FAIRY',
        'FA1RY': 'FAIRY',
    }
    
    # Credits-related keywords to filter out
    CREDITS_KEYWORDS = [
        'WRITTEN BY',
        'DIRECTED BY',
        'STORY BY',
        'TELEPLAY BY',
        'PRODUCER',
        'EXECUTIVE PRODUCER',
        'CREATED BY',
        'BASED ON',
        'NICKELODEON',
        'SPIN MASTER',
        'COPYRIGHT',
        '©',
        '®',
        '™',
        'ALL RIGHTS RESERVED',
    ]
    
    # Minimum confidence threshold for OCR results
    MIN_OCR_CONFIDENCE = 0.3
    
    # Minimum fuzzy match score (0-100)
    MIN_MATCH_SCORE = 60
    
    def __init__(self, episode_titles: Dict[int, str], season_number: Optional[int] = None):
        """
        Initialize the matcher with episode titles.
        
        Args:
            episode_titles: Dictionary mapping episode numbers to titles
                           e.g., {1: "Pups Save the Day", 2: "Pups Find a Friend"}
            season_number: Optional season number for result metadata
        """
        self.episode_titles = episode_titles
        self.season_number = season_number
        
        # Pre-process titles for better matching
        self.normalized_titles = {
            ep_num: self._normalize_text(title)
            for ep_num, title in episode_titles.items()
        }
    
    def _normalize_text(self, text: str) -> str:
        """
        Normalize text for comparison.
        
        Args:
            text: Raw text string
            
        Returns:
            Normalized text (uppercase, alphanumeric + spaces only)
        """
        # Convert to uppercase
        text = text.upper()
        
        # Remove special characters but keep spaces
        text = re.sub(r'[^A-Z0-9\s]', '', text)
        
        # Normalize whitespace
        text = ' '.join(text.split())
        
        return text
    
    def _is_credits_text(self, text: str) -> bool:
        """
        Check if text appears to be credits/metadata rather than title.
        
        Args:
            text: Text fragment to check
            
        Returns:
            True if text appears to be credits
        """
        text_upper = text.upper()
        
        # Check against known credits keywords
        for keyword in self.CREDITS_KEYWORDS:
            if keyword in text_upper:
                return True
        
        # Check for patterns like "Name Surname" (likely a person's name in credits)
        # But be careful not to filter valid title words
        words = text.split()
        if len(words) == 2:
            # Common title words that should NOT be filtered
            title_words = {
                'PUPS', 'SAVE', 'STOP', 'FIND', 'GET', 'RESCUE', 
                'THE', 'A', 'AN', 'AND', 'OR', 'OF', 'TO', 'FROM',
                'GIANT', 'ROBOT', 'TOOTH', 'FAIRY', 'QUEEN', 'KING',
                'MINI', 'PATROL', 'ADVENTURE', 'MISSION', 'DAY',
                'NIGHT', 'ROYAL', 'CROWN', 'CHALK', 'ART', 'HOT',
                'POTATO', 'TREASURE', 'CRUISE', 'GREENHOUSE',
                'HIDING', 'ELEPHANTS', 'MOTORCYCLE', 'STUNT', 'SHOW',
                'SKYDIVERS', 'RETURN', 'HUMSQUATCH', 'FLOATING',
                'JUNGLE', 'PENGUINS', 'MASCOT', 'GLIDING', 'TURBOTS',
                'MAROONED', 'MAYORS',
            }
            
            # If both words are title-related, don't filter
            if all(w.upper() in title_words for w in words):
                return False
            
            # If it looks like "FirstName LastName" (both capitalized, not common title words)
            if (all(w and w[0].isupper() for w in words) and 
                not any(w.upper() in title_words for w in words)):
                return True
        
        return False
    
    def _apply_ocr_corrections(self, text: str) -> str:
        """
        Apply known OCR error corrections to text.
        
        Args:
            text: Raw OCR text
            
        Returns:
            Corrected text
        """
        corrected = text.upper()
        
        # First pass: Apply word-level corrections (whole words)
        for error, correction in self.OCR_CORRECTIONS.items():
            if len(error) > 1 and not error.isdigit():
                # Use word boundaries for multi-character word replacements
                corrected = re.sub(r'\b' + re.escape(error) + r'\b', correction, corrected)
        
        # Second pass: Apply character-level corrections
        # Replace 0 with O in letter contexts (e.g., T00TH -> TOOTH)
        corrected = re.sub(r'0+', lambda m: 'O' * len(m.group()), corrected)
        
        # Apply other character substitutions
        char_subs = {
            '1': 'I',
            '5': 'S',
            '8': 'B',
            '|': 'I',
            '!': 'I',
        }
        for error, correction in char_subs.items():
            corrected = corrected.replace(error, correction)
        
        # Apply multi-character patterns
        pattern_subs = [
            ('IJ', 'U'),
            ('LI', 'U'),
            ('RN', 'M'),
            ('VV', 'W'),
        ]
        for error, correction in pattern_subs:
            corrected = corrected.replace(error, correction)
        
        return corrected
    
    def _combine_fragments(self, fragments: List[OCRFragment]) -> str:
        """
        Combine OCR fragments into a single title string.
        
        Args:
            fragments: List of OCR fragments
            
        Returns:
            Combined text string
        """
        # Filter by confidence threshold
        valid_fragments = [
            f for f in fragments 
            if f.confidence >= self.MIN_OCR_CONFIDENCE
        ]
        
        if not valid_fragments:
            return ""
        
        # Filter out credits text
        title_fragments = [
            f for f in valid_fragments
            if not self._is_credits_text(f.text)
        ]
        
        if not title_fragments:
            return ""
        
        # Don't sort - preserve original order which is usually top-to-bottom
        # This maintains natural reading order of title cards
        
        # Join text with spaces
        combined = ' '.join(f.text for f in title_fragments)
        
        # Apply OCR corrections
        corrected = self._apply_ocr_corrections(combined)
        
        # Normalize
        normalized = self._normalize_text(corrected)
        
        return normalized
    
    def match_title(
        self, 
        ocr_fragments: List[OCRFragment],
        min_score: Optional[int] = None
    ) -> Optional[TitleMatch]:
        """
        Match OCR fragments against episode titles.
        
        Args:
            ocr_fragments: List of OCR text fragments with confidence scores
            min_score: Minimum fuzzy match score (default: MIN_MATCH_SCORE)
            
        Returns:
            TitleMatch object if match found, None otherwise
        """
        if min_score is None:
            min_score = self.MIN_MATCH_SCORE
        
        # Combine and clean OCR fragments
        combined_text = self._combine_fragments(ocr_fragments)
        
        if not combined_text:
            return None
        
        # Try fuzzy matching against all episode titles
        # Use token_sort_ratio to handle word order differences
        matches = process.extract(
            combined_text,
            self.normalized_titles,
            scorer=fuzz.token_sort_ratio,
            limit=3  # Get top 3 matches for debugging
        )
        
        if not matches:
            return None
        
        # Get best match
        best_match = matches[0]
        episode_number = best_match[2]  # The key from the dictionary
        match_score = best_match[1]     # The score
        
        # Check if score meets threshold
        if match_score < min_score:
            return None
        
        # Return match result
        return TitleMatch(
            matched_title=self.episode_titles[episode_number],
            episode_number=episode_number,
            confidence=match_score / 100.0,  # Convert to 0-1 scale
            raw_ocr=combined_text,
            season_number=self.season_number
        )
    
    def match_title_simple(
        self,
        ocr_texts: List[str],
        ocr_confidences: Optional[List[float]] = None,
        min_score: Optional[int] = None
    ) -> Optional[TitleMatch]:
        """
        Simplified interface that takes lists of strings and confidences.
        
        Args:
            ocr_texts: List of OCR text strings
            ocr_confidences: Optional list of confidence scores (defaults to 1.0)
            min_score: Minimum fuzzy match score
            
        Returns:
            TitleMatch object if match found, None otherwise
        """
        # Convert to OCRFragment objects
        if ocr_confidences is None:
            ocr_confidences = [1.0] * len(ocr_texts)
        
        fragments = [
            OCRFragment(text=text, confidence=conf)
            for text, conf in zip(ocr_texts, ocr_confidences)
        ]
        
        return self.match_title(fragments, min_score)


def example_usage():
    """Example usage of the OCR title matcher."""
    
    # Example: Season 9 episode titles (subset)
    season_9_titles = {
        1: "Pups Save the Tooth Fairy",
        2: "Pups Stop a Giant Robot",
        3: "Pups Save a Floating Royal Crown",
        4: "Pups Save the Jungle Penguins",
        5: "Pups Save the Mini Patrol",
        # ... more episodes
        11: "Pups Save the Queen of the Pups",
        20: "Pups Stop the Return of Humsquatch",
    }
    
    # Create matcher
    matcher = OCRTitleMatcher(season_9_titles, season_number=9)
    
    # Example 1: Clean OCR with minor errors
    print("=" * 60)
    print("Example 1: OCR with minor errors")
    print("=" * 60)
    
    ocr_fragments_1 = [
        OCRFragment("PUPS SAT THE", 0.85),
        OCRFragment("QEEQ", 0.72),
    ]
    
    match_1 = matcher.match_title(ocr_fragments_1)
    if match_1:
        print(f"✓ Matched: {match_1.matched_title}")
        print(f"  Episode: S{match_1.season_number:02d}E{match_1.episode_number:02d}")
        print(f"  Confidence: {match_1.confidence:.2%}")
        print(f"  Raw OCR: '{match_1.raw_ocr}'")
    else:
        print("✗ No match found")
    
    # Example 2: Multiple fragments with credits
    print("\n" + "=" * 60)
    print("Example 2: Multiple fragments with credits")
    print("=" * 60)
    
    ocr_fragments_2 = [
        OCRFragment("PUPS STOP THE", 0.90),
        OCRFragment("RETURN OF HUMSQUATCH", 0.88),
        OCRFragment("WRITTEN BY", 0.65),  # Should be filtered
        OCRFragment("JOHN SMITH", 0.70),   # Should be filtered
    ]
    
    match_2 = matcher.match_title(ocr_fragments_2)
    if match_2:
        print(f"✓ Matched: {match_2.matched_title}")
        print(f"  Episode: S{match_2.season_number:02d}E{match_2.episode_number:02d}")
        print(f"  Confidence: {match_2.confidence:.2%}")
        print(f"  Raw OCR: '{match_2.raw_ocr}'")
    else:
        print("✗ No match found")
    
    # Example 3: Using simplified interface
    print("\n" + "=" * 60)
    print("Example 3: Simplified interface")
    print("=" * 60)
    
    ocr_texts = ["PUPS SAV THE", "T00TH FAIRY"]
    ocr_confidences = [0.82, 0.75]
    
    match_3 = matcher.match_title_simple(ocr_texts, ocr_confidences)
    if match_3:
        print(f"✓ Matched: {match_3.matched_title}")
        print(f"  Episode: S{match_3.season_number:02d}E{match_3.episode_number:02d}")
        print(f"  Confidence: {match_3.confidence:.2%}")
        print(f"  Raw OCR: '{match_3.raw_ocr}'")
        print(f"\n  Dictionary format:")
        print(f"  {match_3.to_dict()}")
    else:
        print("✗ No match found")
    
    # Example 4: Low quality OCR that should fail
    print("\n" + "=" * 60)
    print("Example 4: Low quality OCR (should fail)")
    print("=" * 60)
    
    ocr_fragments_4 = [
        OCRFragment("RANDOM TEXT", 0.25),  # Too low confidence
        OCRFragment("GARBAGE", 0.20),      # Too low confidence
    ]
    
    match_4 = matcher.match_title(ocr_fragments_4)
    if match_4:
        print(f"✓ Matched: {match_4.matched_title}")
    else:
        print("✗ No match found (as expected - low confidence OCR)")


if __name__ == "__main__":
    example_usage()
