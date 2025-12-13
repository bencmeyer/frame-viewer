#!/usr/bin/env python3
"""
OCR Title Matching System for Paw Patrol Episodes
Handles OCR errors, credits filtering, and fuzzy matching against TVDB titles.
"""

from dataclasses import dataclass
from typing import List, Optional, Dict, Tuple
from rapidfuzz import fuzz, process

@dataclass
class OCRFragment:
    """A single text fragment detected by OCR."""
    text: str
    confidence: float
    bbox: Optional[list] = None

@dataclass
class TitleMatch:
    """Result of matching OCR text to an episode title."""
    matched_title: str
    episode_number: int
    season_number: int
    confidence: float  # 0.0 to 1.0
    raw_ocr: str

# Common OCR character substitution errors
OCR_CORRECTIONS = {
    'SAT': 'SAVE',
    'SATE': 'SAVE',
    'SAV': 'SAVE',
    'SAUE': 'SAVE',
    'ST0P': 'STOP',
    'STDP': 'STOP',
    'T00TH': 'TOOTH',
    'TQQTH': 'TOOTH',
    'TQOTH': 'TOOTH',
    'QEEQ': 'FAIRY',  # Common misread in title cards
    'QUEEO': 'QUEEN',
    'PUPP5': 'PUPS',
    'PUPPS': 'PUPS',
    'PUP5': 'PUPS',
    'FLQAT': 'FLOAT',
    'HUMDINQER': 'HUMDINGER',
    'MAYQR': 'MAYOR',
    'RESCQE': 'RESCUE',
    'PQTROL': 'PATROL',
    'MISSINQ': 'MISSING',
    'ART': 'ART',
}

# Credits keywords to filter out
CREDITS_KEYWORDS = [
    'written by',
    'directed by',
    'produced by',
    'story by',
    'executive producer',
    'animation',
    'storyboard',
    'voice',
    'guest star',
    'music by',
    'special thanks',
    '©',
    '®',
]

def is_credits_text(text: str) -> bool:
    """Check if text is credits/metadata rather than episode title."""
    text_lower = text.lower()
    
    # Check for credit keywords
    if any(kw in text_lower for kw in CREDITS_KEYWORDS):
        return True
    
    # Check for typical credit patterns
    if ' by ' in text_lower and len(text) < 30:
        return True
    
    # Very short fragments likely not titles
    if len(text.strip()) < 3:
        return True
    
    return False

def correct_ocr_errors(text: str) -> str:
    """Apply common OCR error corrections."""
    text_upper = text.upper()
    corrected = text_upper
    
    # Apply known corrections
    for error, correction in OCR_CORRECTIONS.items():
        corrected = corrected.replace(error, correction)
    
    # Common character substitutions
    corrected = corrected.replace('0', 'O')
    corrected = corrected.replace('5', 'S')
    corrected = corrected.replace('1', 'I')
    corrected = corrected.replace('8', 'B')
    corrected = corrected.replace('$', 'S')
    corrected = corrected.replace('|', 'I')
    
    # Fix double letters from corrections
    corrected = corrected.replace('SAVEE', 'SAVE')
    corrected = corrected.replace('SAVVES', 'SAVES')
    
    return corrected

def combine_ocr_fragments(fragments: List[OCRFragment], min_confidence: float = 0.3) -> str:
    """
    Combine OCR fragments into episode title, filtering out credits.
    
    Args:
        fragments: List of OCR text fragments
        min_confidence: Minimum confidence to include (0.0-1.0)
    
    Returns:
        Combined title text
    """
    title_fragments = []
    
    for fragment in fragments:
        # Skip low confidence
        if fragment.confidence < min_confidence:
            continue
        
        # Skip credits
        if is_credits_text(fragment.text):
            continue
        
        # Add to title
        title_fragments.append(fragment.text)
    
    # Combine and clean
    combined = ' '.join(title_fragments)
    combined = ' '.join(combined.split())  # Normalize whitespace
    
    return combined


def is_valid_title_card(ocr_text: str, min_words: int = 2) -> bool:
    """
    Validate that OCR text looks like an actual episode title card.
    
    Args:
        ocr_text: Combined OCR text
        min_words: Minimum number of words required
    
    Returns:
        True if looks like a valid title card
    """
    if not ocr_text or len(ocr_text) < 5:
        return False
    
    # Must have minimum words
    words = ocr_text.split()
    if len(words) < min_words:
        return False
    
    # Should have "PUPS" or "PUP" somewhere
    text_upper = ocr_text.upper()
    if 'PUP' not in text_upper:
        # Exception: some titles might not have PUPS (rare)
        # But then needs action words
        action_words = ['SAVE', 'STOP', 'MEET', 'SOLVE', 'RESCUE']
        if not any(word in text_upper for word in action_words):
            return False
    
    # Should not be just logos/network names
    invalid_only = ['NICKELODEON', 'PARAMOUNT', 'SPINMASTER', 'TVOkids']
    if all(invalid in text_upper for invalid in invalid_only):
        return False
    
    return True

def extract_keywords(text: str) -> str:
    """
    Extract keywords from episode title, removing common Paw Patrol filler words.
    
    Args:
        text: Episode title or OCR text
    
    Returns:
        Cleaned text with only key words
    """
    text = text.upper()
    
    # Common filler words in Paw Patrol titles
    stopwords = {'PUPS', 'PUP', 'SAVE', 'SAVES', 'SAVEE', 'THE', 'A', 'AN', 'AND', 'OF', 
                 'PATROL', 'PAW', 'TO', 'STOP', 'STOPS', 'MEET', 'MEETS', 'SOLVE', 'SOLVES'}
    
    # Common people names that appear in credits
    credits_names = {'CLARK', 'STUBBS', 'WRITTEN', 'BY', 'DIRECTED', 'PRODUCED'}
    
    words = text.split()
    keywords = [w for w in words 
                if w not in stopwords 
                and w not in credits_names
                and len(w) > 2]
    
    return ' '.join(keywords)


def match_title_to_episodes(
    ocr_text: str,
    episode_database: Dict[Tuple[int, int], Dict],
    season: int,
    min_score: float = 0.50  # Lowered from 0.60
) -> Optional[TitleMatch]:
    """
    Match OCR text to episode titles using fuzzy matching.
    
    Args:
        ocr_text: Combined OCR text from frame
        episode_database: Dict mapping (season, episode) -> {"title": str, ...}
        season: Season number to search in
        min_score: Minimum fuzzy match score (0.0-1.0)
    
    Returns:
        TitleMatch if found, None otherwise
    """
    if not ocr_text or len(ocr_text) < 4:
        return None
    
    # Apply OCR corrections
    corrected_text = correct_ocr_errors(ocr_text)
    
    # Extract keywords from OCR
    ocr_keywords = extract_keywords(corrected_text)
    
    # Build list of episode titles for this season
    season_episodes = []
    for (s, e), data in episode_database.items():
        if s == season:
            season_episodes.append({
                'episode': e,
                'title': data.get('title', ''),
                'keywords': extract_keywords(data.get('title', ''))
            })
    
    if not season_episodes:
        return None
    
    # Try matching keywords first (more accurate)
    if ocr_keywords:
        keywords_list = [ep['keywords'] for ep in season_episodes]
        
        result = process.extractOne(
            ocr_keywords,
            keywords_list,
            scorer=fuzz.ratio,  # Use simple ratio for keyword matching
            score_cutoff=min_score * 100  # rapidfuzz uses 0-100 scale
        )
        
        if result:
            matched_keywords, score, index = result
            matched_episode = season_episodes[index]['episode']
            matched_title = season_episodes[index]['title']
            
            return TitleMatch(
                matched_title=matched_title,
                episode_number=matched_episode,
                season_number=season,
                confidence=score / 100.0,  # Convert to 0-1 scale
                raw_ocr=ocr_text
            )
    
    # Fallback: match full text
    titles = [ep['title'] for ep in season_episodes]
    
    result = process.extractOne(
        corrected_text,
        titles,
        scorer=fuzz.token_sort_ratio,
        score_cutoff=min_score * 100
    )
    
    if not result:
        return None
    
    matched_title, score, index = result
    matched_episode = season_episodes[index]['episode']
    
    return TitleMatch(
        matched_title=matched_title,
        episode_number=matched_episode,
        season_number=season,
        confidence=score / 100.0,  # Convert to 0-1 scale
        raw_ocr=ocr_text
    )

def detect_episode_from_ocr(
    fragments: List[OCRFragment],
    episode_database: Dict[Tuple[int, int], Dict],
    season: int,
    min_confidence: float = 0.3,
    min_match_score: float = 0.60
) -> Optional[TitleMatch]:
    """
    Complete pipeline: OCR fragments -> episode match.
    
    Args:
        fragments: OCR text fragments from frame
        episode_database: Episode title database
        season: Season number
        min_confidence: Minimum OCR confidence to use
        min_match_score: Minimum fuzzy match score
    
    Returns:
        TitleMatch if successful, None otherwise
    """
    # Combine fragments
    combined_text = combine_ocr_fragments(fragments, min_confidence)
    
    if not combined_text:
        return None
    
    # Validate it looks like a title card
    if not is_valid_title_card(combined_text):
        return None
    
    # Match to episode
    match = match_title_to_episodes(
        combined_text,
        episode_database,
        season,
        min_match_score
    )
    
    return match
