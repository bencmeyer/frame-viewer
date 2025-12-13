#!/usr/bin/env python3
"""Automation pipeline: detect scenes/intro, optional OCR on title cards, then split with ffmpeg."""
import argparse
import csv
import json
import os
import re
import tempfile
from dataclasses import asdict
from pathlib import Path
from typing import Dict, List, Optional, Tuple

import pytesseract
import requests
from PIL import Image
from rapidfuzz import fuzz, process
from rich import print
from rich.table import Table

from ocr_title_detector import (
    extract_title_from_frame,
    extract_regions_from_image,
    find_title_region,
    clean_ocr_text,
)
from episode_splitter import (
    EpisodeSegment,
    cut_segment,
    detect_scene_changes,
    find_intro_for_episode,
    get_duration,
    guess_episode_segments,
    run_cmd,
)


def load_episodes_database(episodes_file: Path) -> Dict[Tuple[int, int], Dict[str, str]]:
    """Load episode database (season, episode, air_date, title).
    
    Returns dict: (season, episode) -> {'air_date': 'YYYY-MM-DD', 'title': '...'}
    """
    episodes: Dict[Tuple[int, int], Dict[str, str]] = {}
    if not episodes_file.exists():
        return episodes
    
    try:
        with open(episodes_file) as f:
            reader = csv.DictReader(f)
            for row in reader:
                if not row.get('season') or not row.get('episode'):
                    continue
                season = int(row['season'])
                episode = int(row['episode'])
                episodes[(season, episode)] = {
                    'air_date': row.get('air_date', ''),
                    'title': row.get('title', ''),
                }
    except Exception as e:
        print(f"[yellow]Warning: Failed to load episodes database: {e}[/yellow]")
    
    return episodes


def detect_episodes_from_air_dates(
    season: int, episode: int, episodes_db: Dict[Tuple[int, int], Dict[str, str]]
) -> int:
    """Detect if episode file contains 1 or 2 episodes based on airing dates.
    
    If season:episode and season:(episode+1) share the same air_date, it's a 2-episode file.
    Returns 1 or 2.
    """
    ep_info = episodes_db.get((season, episode))
    next_ep_info = episodes_db.get((season, episode + 1))
    
    if ep_info and next_ep_info:
        # If they air on the same date, they're likely a 2-episode file
        if ep_info.get('air_date') == next_ep_info.get('air_date'):
            return 2
    
    return 1


def extract_frame(input_file: str, timestamp: float, out_path: Path) -> None:
    cmd = [
        "ffmpeg",
        "-y",
        "-ss",
        f"{timestamp:.3f}",
        "-i",
        input_file,
        "-frames:v",
        "1",
        "-q:v",
        "2",
        str(out_path),
    ]
    run_cmd(cmd)


def ocr_image(image_path: Path, lang: str, psm: int = 6) -> str:
    """Legacy OCR function - now delegates to improved ocr_title_detector module.
    
    Returns raw concatenated text from all detected regions (for backward compatibility).
    """
    try:
        regions = extract_regions_from_image(image_path, use_easyocr=True)
        
        # Concatenate all non-garbage text with newlines
        text_parts = []
        for region in regions:
            if len(region.cleaned_text.strip()) > 3:
                text_parts.append(region.cleaned_text)
        
        if text_parts:
            return '\n'.join(text_parts)
    except Exception:
        pass
    
    # Fallback: use raw Tesseract if everything else fails
    try:
        img = Image.open(image_path)
        return pytesseract.image_to_string(img, lang=lang, config=f'--psm {psm}')
    except Exception:
        return ""


def extract_title_from_ocr(text: str, known_titles: Optional[List[str]] = None) -> Optional[str]:
    """Legacy function - now superseded by ocr_title_detector.find_title_region().
    
    Kept for backward compatibility only.
    """
    from ocr_title_detector import clean_ocr_text
    return clean_ocr_text(text) if text else None


def match_title(text: str, candidates: List[str], cutoff: int = 50) -> Tuple[Optional[str], Optional[float]]:
    """Fuzzy-match OCR text against list of known titles. Lower cutoff for noisy OCR."""
    if not text.strip() or not candidates:
        return None, None
    # try token-sort ratio (better for title cards with credits mixed in)
    result = process.extractOne(text, candidates, scorer=fuzz.token_sort_ratio, score_cutoff=cutoff)
    if result:
        return result[0], float(result[1])
    
    # fallback: check if any candidate word appears in the OCR text
    text_lower = text.lower()
    for cand in candidates:
        cand_words = cand.lower().split()
        # if multiple words from title appear, consider it a match
        matching_words = sum(1 for w in cand_words if len(w) > 3 and w in text_lower)
        if matching_words >= 1:
            return cand, float(matching_words * 30)  # lower score but valid match
    
    return None, None


def extract_episode_info(filename: str) -> Tuple[Optional[int], Optional[int]]:
    """Extract season and episode from filename patterns like 's10e05', 'S01E01', etc."""
    # patterns: s10e05, S01E01, 10x05, etc.
    patterns = [
        r"[Ss](\d+)[Ee](\d+)",  # s10e05 or S10E05
        r"(\d+)[Xx](\d+)",       # 10x05
        r"season[ _]?(\d+).*episode[ _]?(\d+)",  # season 10 episode 05
    ]
    filename_lower = filename.lower()
    for pattern in patterns:
        match = re.search(pattern, filename_lower)
        if match:
            season, episode = int(match.group(1)), int(match.group(2))
            return season, episode
    return None, None


def extract_titles_from_filename(filename: str) -> Tuple[Optional[str], Optional[str]]:
    """Extract episode titles from filename pattern like 'S01E01-E02 - Title1 and Title2'."""
    # Pattern: after episode marker, extract titles separated by 'and'
    # e.g., "S01E01-E02 - Pups Make a Splash and Pups Fall Festival" → ["Pups Make a Splash", "Pups Fall Festival"]
    
    # Look for text after episode marker (skip any "E##" that might appear after dash)
    match = re.search(r"[Ss]\d+[Ee]\d+[Ee]?\d*\s*-\s*(?:[Ee]?\d+\s*-\s*)?(.+)", filename)
    if not match:
        return None, None
    
    text_after = match.group(1)
    # Remove quality indicators and brackets
    text_after = re.sub(r"\s*\[.*?\].*$", "", text_after)
    text_after = text_after.strip()
    
    # Split by common separators: " and ", " & ", " / "
    parts = re.split(r"\s+(?:and|&|\/)\s+", text_after, maxsplit=2)
    
    if len(parts) >= 2:
        # clean up each title
        title1 = parts[0].strip()
        title2 = parts[1].strip()
        return title1, title2
    elif len(parts) == 1:
        # Single episode, use it for ep1
        return parts[0].strip(), None
    
    return None, None
    if not csv:
        return []
    out: List[float] = []
    for part in csv.split(","):
        part = part.strip()
        if not part:
            continue
        try:
            out.append(float(part))
        except ValueError:
            continue
    return out


def parse_time_to_seconds(text: str) -> Optional[float]:
    """Parse hh:mm:ss, mm:ss, or seconds (float) into seconds."""
    text = text.strip()
    if not text:
        return None
    if ":" in text:
        parts = text.split(":")
        try:
            parts = [float(p) for p in parts]
        except ValueError:
            return None
        if len(parts) == 3:
            h, m, s = parts
        elif len(parts) == 2:
            h = 0.0
            m, s = parts
        else:
            return None
        return h * 3600 + m * 60 + s
    try:
        return float(text)
    except ValueError:
        return None


def parse_float_list(spec: str) -> List[float]:
    """Parse comma-separated floats from string like '1,3,8,15'."""
    try:
        return [float(x.strip()) for x in spec.split(",") if x.strip()]
    except ValueError:
        return []


def parse_manual_titles(spec: Optional[str]) -> Dict[int, str]:
    """Parse manual title overrides like '1=Title1,2=Title2'."""
    result: Dict[int, str] = {}
    if not spec:
        return result
    for item in spec.split(","):
        item = item.strip()
        if "=" not in item:
            continue
        ep_str, title = item.split("=", 1)
        try:
            ep_idx = int(ep_str.strip())
            result[ep_idx] = title.strip()
        except ValueError:
            continue
    return result


def parse_sample_times_map(spec: Optional[str]) -> Dict[int, List[float]]:
    """Parse mapping like '1=45,2=11:45' into {1:[45],2:[705]}"""
    if not spec:
        return {}
    out: Dict[int, List[float]] = {}
    for token in spec.split(','):
        token = token.strip()
        if not token or '=' not in token:
            continue
        left, right = token.split('=', 1)
        try:
            ep_idx = int(left.strip())
        except ValueError:
            continue
        timestr = right.strip()
        t = parse_time_to_seconds(timestr)
        if t is None:
            continue
        out.setdefault(ep_idx, []).append(t)
    return out


def slugify_title(text: str) -> str:
    """Make a filename-friendly slug from OCR/matched title."""
    cleaned = re.sub(r"[^A-Za-z0-9]+", " ", text).strip()
    cleaned = re.sub(r"\s+", " ", cleaned)
    return cleaned.replace(" ", "_") or "untitled"


def search_tmdb_series(series_name: str, api_key: Optional[str] = None) -> Optional[int]:
    """Search TMDB for series ID by name. Requires TMDB_API_KEY env var or api_key param."""
    if not api_key:
        api_key = os.getenv("TMDB_API_KEY")
    if not api_key:
        return None
    try:
        resp = requests.get(
            "https://api.themoviedb.org/3/search/tv",
            params={"api_key": api_key, "query": series_name},
            timeout=5,
        )
        resp.raise_for_status()
        data = resp.json()
        if data.get("results"):
            return data["results"][0]["id"]
    except Exception:
        pass
    return None


def fetch_tmdb_episode_title(series_id: int, season: int, episode: int, api_key: Optional[str] = None) -> Optional[str]:
    """Fetch episode title from TMDB by series ID, season, and episode number."""
    if not api_key:
        api_key = os.getenv("TMDB_API_KEY")
    if not api_key:
        return None
    try:
        resp = requests.get(
            f"https://api.themoviedb.org/3/tv/{series_id}/season/{season}/episode/{episode}",
            params={"api_key": api_key},
            timeout=5,
        )
        resp.raise_for_status()
        return resp.json().get("name")
    except Exception:
        pass
    return None


def get_tvdb_token(api_key: str) -> Optional[str]:
    """Login to TVDB v4 and get bearer token.
    
    TVDB v4 requires a 2-step process:
    1. POST to /login with apikey to get bearer token
    2. Use bearer token for all subsequent requests
    """
    try:
        resp = requests.post(
            "https://api4.thetvdb.com/v4/login",
            json={"apikey": api_key},
            timeout=5,
        )
        resp.raise_for_status()
        data = resp.json()
        return data.get("data", {}).get("token")
    except Exception:
        return None


def search_tvdb_series(series_name: str, api_key: Optional[str] = None) -> Optional[int]:
    """Search TVDB (v4) for series ID by name. Requires TVDB_API_KEY env var or api_key param."""
    if not api_key:
        api_key = os.getenv("TVDB_API_KEY")
    if not api_key:
        return None
    
    # Get bearer token
    token = get_tvdb_token(api_key)
    if not token:
        return None
    
    try:
        headers = {"Authorization": f"Bearer {token}"}
        resp = requests.get(
            "https://api4.thetvdb.com/v4/search",
            params={"query": series_name, "type": "series"},
            headers=headers,
            timeout=5,
        )
        resp.raise_for_status()
        data = resp.json()
        if data.get("data"):
            return data["data"][0]["tvdb_id"]
    except Exception:
        pass
    return None


def fetch_tvdb_episode_title(series_id: int, season: int, episode: int, api_key: Optional[str] = None) -> Optional[str]:
    """Fetch episode title from TVDB v4 by series ID, season, and episode number."""
    if not api_key:
        api_key = os.getenv("TVDB_API_KEY")
    if not api_key:
        return None
    
    # Get bearer token
    token = get_tvdb_token(api_key)
    if not token:
        return None
    
    try:
        headers = {"Authorization": f"Bearer {token}"}
        resp = requests.get(
            f"https://api4.thetvdb.com/v4/series/{series_id}/episodes/default",
            headers=headers,
            timeout=5,
        )
        resp.raise_for_status()
        eps = resp.json().get("data", {}).get("episodes", [])
        for ep in eps:
            if ep.get("seasonNumber") == season and ep.get("number") == episode:
                return ep.get("name")
    except Exception as e:
        pass
    return None


def fetch_tvdb_season_episodes(series_id: int, season: int, api_key: Optional[str] = None) -> Dict[Tuple[int, int], Dict[str, str]]:
    """Fetch all episodes for a season from TVDB.
    
    Returns dict mapping (season, episode) -> {title, air_date}
    This allows correlating 2-episode files by air date.
    """
    if not api_key:
        api_key = os.getenv("TVDB_API_KEY")
    if not api_key:
        return {}
    
    # Get bearer token
    token = get_tvdb_token(api_key)
    if not token:
        return {}
    
    try:
        headers = {"Authorization": f"Bearer {token}"}
        resp = requests.get(
            f"https://api4.thetvdb.com/v4/series/{series_id}/episodes/default",
            headers=headers,
            timeout=5,
        )
        resp.raise_for_status()
        eps = resp.json().get("data", {}).get("episodes", [])
        
        result = {}
        for ep in eps:
            s = ep.get("seasonNumber")
            e = ep.get("number")
            if s == season and e is not None:
                result[(s, e)] = {
                    "title": ep.get("name", ""),
                    "air_date": ep.get("aired", ""),
                }
        
        return result
    except Exception as e:
        if os.getenv("DEBUG"):
            print(f"[yellow]TVDB season fetch failed: {e}[/yellow]")
        return {}


def detect_episodes_from_air_dates(season: int, episode: int, episodes_db: Dict[Tuple[int, int], Dict[str, str]]) -> int:
    """Determine if this should be a 2-episode file based on air dates.
    
    Returns 1 or 2 (number of episodes expected in file).
    If episode N and N+1 aired on the same date, it's likely a 2-episode file.
    """
    ep_info = episodes_db.get((season, episode))
    next_ep_info = episodes_db.get((season, episode + 1))
    
    if not ep_info or not next_ep_info:
        return 1  # Can't determine, assume single episode
    
    ep_date = ep_info.get("air_date")
    next_ep_date = next_ep_info.get("air_date")
    
    if ep_date and next_ep_date and ep_date == next_ep_date:
        return 2  # Same air date = 2-episode file
    
    return 1


def fetch_tvdb_episode_info(series_id: int, season: int, episode: int, api_key: Optional[str] = None) -> Dict[str, any]:
    """Fetch full episode info from TVDB: title, air date, and next episode air date.
    
    Returns dict with keys: title, air_date, next_ep_title, next_ep_air_date
    """
    if not api_key:
        api_key = os.getenv("TVDB_API_KEY")
    if not api_key:
        return {}
    
    try:
        headers = {"Authorization": f"Bearer {api_key}"}
        resp = requests.get(
            f"https://api4.thetvdb.com/v4/series/{series_id}/episodes/default",
            headers=headers,
            timeout=5,
        )
        resp.raise_for_status()
        eps = resp.json().get("data", {}).get("episodes", [])
        
        result = {}
        for i, ep in enumerate(eps):
            if ep.get("seasonNumber") == season and ep.get("number") == episode:
                result["title"] = ep.get("name")
                result["air_date"] = ep.get("aired")
                
                # Check if next episode airs same day (= 2-episode file)
                if i + 1 < len(eps):
                    next_ep = eps[i + 1]
                    if next_ep.get("seasonNumber") == season and next_ep.get("number") == episode + 1:
                        result["next_ep_title"] = next_ep.get("name")
                        result["next_ep_air_date"] = next_ep.get("aired")
                        # If same air date, mark as double episode
                        if result["air_date"] == result["next_ep_air_date"]:
                            result["same_day_double"] = True
                break
        
        return result
    except Exception as e:
        if os.getenv("DEBUG"):
            print(f"[yellow]TVDB fetch failed: {e}[/yellow]")
        return {}


def rename_file(src: Path, dst_filename: str) -> None:
    """Rename a file to dst_filename in the same directory."""
    dst = src.parent / dst_filename
    src.rename(dst)
    print(f"[green]Renamed[/green] {src.name} → {dst.name}")


def pick_sample_times(
    seg: EpisodeSegment,
    post_intro_offsets: List[float],
    episode_offsets: List[float],
) -> List[float]:
    """Return candidate frame times (absolute seconds) inside an episode.
    
    Strategy: Title cards appear in predictable windows:
    - EP1: BEFORE intro starts (opening title card at 6-10s) OR right after intro (30-40s)
    - EP2: Same pattern - before its intro or right after
    
    We sample aggressively in these windows to find readable OCR text.
    """
    times: List[float] = []

    if seg.has_intro and seg.intro_start is not None and seg.intro_end is not None:
        if seg.index == 1:
            # EP1: title card often appears BEFORE intro starts (6-10s from episode start)
            # Also try right after intro ends (30-55s range)
            for offset in [6, 7, 8, 9, 10]:
                times.append(seg.start + offset)
            for offset in [1, 3, 5, 8, 10, 12, 14, 16, 18, 20, 22, 25]:
                times.append(seg.intro_end + offset)
        elif seg.index == 2:
            # EP2: title card appears before its intro (early in ep2)
            # Sample early in episode 2
            for offset in [6, 7, 8, 9, 10, 12, 15]:
                times.append(seg.start + offset)
            # Also try before intro
            if seg.intro_start > seg.start + 20:
                for offset in [20, 15, 10]:
                    times.append(seg.intro_start - offset)
    
    # Fallback: generic episode-relative samples from start
    for offset in post_intro_offsets:
        times.append(seg.start + offset)
    for offset in episode_offsets:
        times.append(seg.start + offset)

    # Final fallback: early in episode (where title cards usually are)
    span = seg.end - seg.start
    times.append(seg.start + 8)  # Very early, typical title card time
    times.append(seg.start + min(90.0, span * 0.20))
    times.append(seg.start + span * 0.5)

    # dedupe while preserving order and keep within episode bounds
    seen = set()
    ordered: List[float] = []
    for t in times:
        if t < seg.start or t > seg.end:
            continue
        if t in seen:
            continue
        seen.add(t)
        ordered.append(t)
    return ordered


def detect_segments(input_file: str, scene_threshold: float, assume_two: bool, num_episodes: Optional[int] = None) -> Tuple[List[EpisodeSegment], List[float], float]:
    duration = get_duration(input_file)
    scenes = detect_scene_changes(input_file, threshold=scene_threshold)
    
    # If num_episodes override provided, use it directly
    if num_episodes is not None:
        assume_two = (num_episodes == 2)
    
    episode_ranges = guess_episode_segments(duration, scenes, assume_two=assume_two)

    segments: List[EpisodeSegment] = []
    for idx, (ep_start, ep_end) in enumerate(episode_ranges, start=1):
        intro_start, intro_end = find_intro_for_episode(scenes, ep_start, ep_end)
        has_intro = intro_start is not None and intro_end is not None
        segments.append(
            EpisodeSegment(
                index=idx,
                start=ep_start,
                end=ep_end,
                has_intro=has_intro,
                intro_start=intro_start,
                intro_end=intro_end,
            )
        )
    return segments, scenes, duration


def run_pipeline(
    input_file: str,
    scene_threshold: float,
    assume_two: bool,
    ocr_lang: str,
    titles_path: Optional[Path],
    skip_split: bool,
    verbose: bool,
    json_out: Optional[Path],
    save_frames_dir: Optional[Path],
    post_intro_offsets: List[float],
    episode_offsets: List[float],
    explicit_samples: Dict[int, List[float]],
    series_name: Optional[str],
    tvdb_api_key: Optional[str],
    num_episodes: Optional[int] = None,
    manual_titles: Optional[Dict[int, str]] = None,
    episodes_db: Optional[Dict[Tuple[int, int], Dict[str, str]]] = None,
) -> None:
    input_path = Path(input_file)
    titles: List[str] = []
    if titles_path and titles_path.exists():
        titles = [line.strip() for line in titles_path.read_text().splitlines() if line.strip()]
    
    # Extract episode info from filename
    season, episode = extract_episode_info(input_path.name)
    if verbose and (season is not None and episode is not None):
        print(f"[blue]Extracted from filename: Season {season}, Episode {episode}[/blue]")
    
    # Fetch all episodes for the season from TVDB if available
    tvdb_series_id = None
    season_episodes_db = episodes_db or {}
    
    if tvdb_api_key and series_name and season is not None:
        if verbose:
            print(f"[cyan]Fetching season {season} episodes from TVDB for '{series_name}'...[/cyan]")
        try:
            tvdb_series_id = search_tvdb_series(series_name, tvdb_api_key)
            if tvdb_series_id:
                # Fetch all episodes for this season
                season_episodes_db = fetch_tvdb_season_episodes(tvdb_series_id, season, tvdb_api_key)
                if verbose and season_episodes_db:
                    print(f"[green]Loaded {len(season_episodes_db)} episodes from TVDB season {season}[/green]")
                
                # Build titles list from the season data
                if not titles:  # Only if no titles file was provided
                    titles = [ep_data["title"] for ep_data in season_episodes_db.values() if ep_data.get("title")]
                    if verbose and titles:
                        print(f"[green]Using {len(titles)} episode titles from TVDB for OCR matching[/green]")
        except Exception as e:
            if verbose:
                print(f"[yellow]TVDB fetch failed: {e}[/yellow]")
    
    # Check if this file should be 2 episodes based on air dates (if no override provided)
    if not assume_two and num_episodes is None and season_episodes_db and season is not None and episode is not None:
        detected_ep_count = detect_episodes_from_air_dates(season, episode, season_episodes_db)
        if detected_ep_count == 2:
            if verbose:
                ep_info = season_episodes_db.get((season, episode), {})
                next_ep_info = season_episodes_db.get((season, episode + 1), {})
                print(f"[cyan]Air date detection:[/cyan] S{season}E{episode:02d} and S{season}E{episode+1:02d} both aired on {ep_info.get('air_date', '?')} → treating as 2-episode file")
            assume_two = True
    
    # Extract episode titles from filename (if it contains title info)
    filename_title1, filename_title2 = extract_titles_from_filename(input_path.name)
    if verbose:
        if filename_title1:
            print(f"[blue]Filename has title for ep1: '{filename_title1}'[/blue]")
        if filename_title2:
            print(f"[blue]Filename has title for ep2: '{filename_title2}'[/blue]")

    print(f"[cyan]Analyzing[/cyan] {input_path} (assume_two={assume_two}, scene_threshold={scene_threshold})")
    segments, scenes, duration = detect_segments(input_file, scene_threshold, assume_two, num_episodes=num_episodes)
    
    if verbose:
        preview = ", ".join(f"{t:.1f}" for t in scenes[:50])
        print(f"[blue]Scene times (first 50):[/blue] {preview}")
    
    # Show auto-detection result if assume_two was used
    if assume_two and num_episodes is None:
        num_detected = len(segments)
        print(f"[cyan]Auto-detected: {num_detected} episode{'s' if num_detected != 1 else ''} in file[/cyan]")

    results: List[Dict] = []
    table = Table(title="Pipeline plan")
    table.add_column("#", justify="right")
    table.add_column("Episode range (s)")
    table.add_column("Intro range (s)")
    table.add_column("Sample t (s)")
    table.add_column("OCR excerpt")
    table.add_column("Filename title")
    table.add_column("OCR match")

    with tempfile.TemporaryDirectory() as tmpdir:
        tmpdir_path = Path(tmpdir)
        for seg in segments:
            ocr_text = ""
            match = None
            score = None
            sample_t_display = "-"
            best_match = None
            best_score = 0.0
            
            # Get filename title for this episode (as reference only, not definitive)
            filename_title = None
            if seg.index == 1 and filename_title1:
                filename_title = filename_title1
            elif seg.index == 2 and filename_title2:
                filename_title = filename_title2

            candidate_times = explicit_samples.get(seg.index) or pick_sample_times(seg, post_intro_offsets, episode_offsets)
            
            # Build list of titles to match against for this specific episode
            episode_titles = []
            tvdb_ep_title = None
            
            # Try to get TVDB title for this specific episode from season database
            if season_episodes_db and season is not None and episode is not None:
                actual_ep_num = episode + seg.index - 1
                ep_data = season_episodes_db.get((season, actual_ep_num))
                if ep_data:
                    tvdb_ep_title = ep_data.get("title")
                    if tvdb_ep_title:
                        episode_titles.append(tvdb_ep_title)
                        if verbose:
                            print(f"[cyan]  Episode {seg.index} (S{season}E{actual_ep_num:02d}): Using TVDB title: {tvdb_ep_title}[/cyan]")
            
            # Add filename title as reference
            if filename_title:
                if filename_title not in episode_titles:  # Avoid duplicates
                    episode_titles.append(filename_title)
            
            # Add all other known titles for fallback matching
            if titles:
                for t in titles:
                    if t not in episode_titles:
                        episode_titles.append(t)
            
            for sample_t in candidate_times:
                frame_path = tmpdir_path / f"ep{seg.index}_sample_{sample_t:.2f}.png"
                try:
                    extract_frame(input_file, sample_t, frame_path)
                    
                    # Save a copy for debugging
                    debug_path = Path(f"frames_debug/ep{seg.index}_sample_{sample_t:.2f}.png")
                    debug_path.parent.mkdir(exist_ok=True)
                    debug_path.write_bytes(frame_path.read_bytes())
                    
                    if verbose:
                        print(f"[dim]  Saved debug frame: {debug_path}[/dim]")
                    
                    # Use improved OCR detector
                    detected_title, confidence, regions = extract_title_from_frame(
                        frame_path,
                        known_titles=episode_titles if episode_titles else None,
                        verbose=False,
                    )
                    
                    # Get raw OCR text for display
                    raw_ocr_parts = []
                    for region in regions:
                        if len(region.cleaned_text.strip()) > 3:
                            raw_ocr_parts.append(region.cleaned_text)
                    candidate_text = ' '.join(raw_ocr_parts)
                    
                    if verbose:
                        print(f"[blue]OCR attempt ep{seg.index} @ {sample_t:.2f}s:")
                        print(f"  Raw text: '{candidate_text[:60].replace(chr(10), ' ')}'")
                        print(f"  Matched title: '{detected_title}' (confidence: {confidence:.2f})")
                    
                    # Check if we have meaningful results
                    if not candidate_text or len(candidate_text.strip()) < 3:
                        if verbose:
                            print(f"[dim]  Skipping - no meaningful text[/dim]")
                        continue
                    
                    ocr_text = candidate_text
                    sample_t_display = f"{sample_t:.1f}"
                    
                    # Use the title from the detector, or try fuzzy matching if not found
                    current_match = None
                    current_score = 0.0
                    
                    if detected_title:
                        current_match = detected_title
                        current_score = confidence  # Already 0-100 from detector
                    elif episode_titles:
                        # Fallback: fuzzy match raw text
                        current_match, current_score = match_title(candidate_text, episode_titles, cutoff=35)
                        if current_match:
                            current_score = current_score or 0.0
                    
                    # Track the best match found so far
                    if current_match and current_score > best_score:
                        best_match = current_match
                        best_score = current_score
                        match = current_match
                        score = current_score
                    
                    # Decide if this is a good enough match to break
                    if filename_title:
                        # Require strong match against the expected title (>= 50%)
                        if current_match and current_score >= 50:
                            if save_frames_dir:
                                save_frames_dir.mkdir(parents=True, exist_ok=True)
                                frame_dest = save_frames_dir / frame_path.name
                                frame_dest.write_bytes(frame_path.read_bytes())
                            if verbose:
                                print(f"[green]✓ Found good match (score: {current_score:.0f}%)[/green]")
                            break
                    else:
                        # No filename title to compare against, use any reasonable match
                        if current_match and current_score >= 35:
                            if save_frames_dir:
                                save_frames_dir.mkdir(parents=True, exist_ok=True)
                                frame_dest = save_frames_dir / frame_path.name
                                frame_dest.write_bytes(frame_path.read_bytes())
                            if verbose:
                                print(f"[green]✓ Found reasonable match (score: {current_score:.0f}%)[/green]")
                            break
                        elif candidate_text and len(candidate_text.strip()) > 10:
                            # No title list to match against, use raw OCR if it looks good
                            if verbose:
                                print(f"[green]✓ Using raw OCR (no titles to match)[/green]")
                            break
                except Exception as exc:  # noqa: BLE001
                    if verbose:
                        print(f"[yellow]OCR failed for episode {seg.index} at {sample_t:.2f}s: {exc}[/yellow]")


            intro_info = "-"
            if seg.has_intro and seg.intro_start is not None and seg.intro_end is not None:
                intro_info = f"{seg.intro_start:.1f} → {seg.intro_end:.1f}"

            # Try TVDB lookup if series_name provided and we have season/episode from filename
            tvdb_title = None
            if series_name and season is not None and episode is not None and tvdb_api_key:
                try:
                    series_id = search_tvdb_series(series_name, tvdb_api_key)
                    if series_id:
                        tvdb_title = fetch_tvdb_episode_title(series_id, season, episode + seg.index - 1, tvdb_api_key)
                        if tvdb_title and not match:
                            match = tvdb_title
                except Exception as e:
                    if verbose:
                        print(f"[yellow]TVDB lookup failed: {e}[/yellow]")
            
            # Priority for final title: Manual > OCR match > TVDB > extracted text > filename
            # Don't use filename by default - it's often wrong (e.g., S09E22 is actually E37-E38)
            manual_title = manual_titles.get(seg.index) if manual_titles else None
            final_title = manual_title or match or tvdb_title or ocr_text or filename_title
            final_score = score if match else None
            
            if manual_title and verbose:
                print(f"[cyan]Using manual title for ep{seg.index}: {manual_title}[/cyan]")

            table.add_row(
                str(seg.index),
                f"{seg.start:.1f} → {seg.end:.1f}",
                intro_info,
                sample_t_display,
                (ocr_text[:60] + "…") if len(ocr_text) > 60 else ocr_text or "-",
                filename_title or "-",
                f"{final_title} ({final_score:.0f})" if final_title and final_score is not None else (final_title if final_title else "-"),
            )

            results.append(
                {
                    "episode": seg.index,
                    "range": [seg.start, seg.end],
                    "intro": [seg.intro_start, seg.intro_end] if seg.has_intro else None,
                    "sample_time": sample_t_display,
                    "ocr_text": ocr_text,
                    "filename_title": filename_title,
                    "title_match": match,
                    "title_score": score,
                    "tvdb_title": tvdb_title,
                    "final_title": final_title,
                }
            )

    print(table)

    # Print suggested titles and filenames
    print("\n[cyan]Suggested titles / filenames:[/cyan]")
    for entry in results:
        ep_idx = entry["episode"]
        title_text = entry["title_match"] or entry["ocr_text"] or ""
        slug = slugify_title(title_text)
        print(f"  ep{ep_idx}: title='{title_text}' filename='{slug}'")

    if json_out:
        payload = {
            "file": str(input_path),
            "duration": duration,
            "scene_count": len(scenes),
            "scene_threshold": scene_threshold,
            "assume_two": assume_two,
            "results": results,
        }
        json_out.write_text(json.dumps(payload, indent=2))
        print(f"[green]Wrote summary to[/green] {json_out}")

    if skip_split:
        # In dry-run mode, suggest what would be renamed to
        print("[magenta]Dry run only; no files written.[/magenta]")
        print("[cyan]Suggested file renames:[/cyan]")
        for r in results:
            seg_idx = r["episode"]
            final_title = r["final_title"]
            if final_title:
                slug = slugify_title(final_title)
                print(f"  Would rename episode {seg_idx} to: {slug}.mkv")
        return

    # Auto-rename the input file based on detected titles
    # For single episode files, rename to "Title.mkv"
    # For multi-episode files, rename to "Title_ep1 - Title_ep2.mkv" or similar
    if len(results) == 1:
        r = results[0]
        final_title = r["final_title"]
        if final_title:
            slug = slugify_title(final_title)
            new_name = input_path.parent / f"{slug}.mkv"
            print(f"[cyan]Renaming:[/cyan] {input_path.name} → {new_name.name}")
            input_path.rename(new_name)
            return
    elif len(results) == 2:
        titles = [r["final_title"] for r in results if r["final_title"]]
        if len(titles) == 2:
            slug1 = slugify_title(titles[0])
            slug2 = slugify_title(titles[1])
            new_name = input_path.parent / f"{slug1} - {slug2}.mkv"
            print(f"[cyan]Renaming:[/cyan] {input_path.name} → {new_name.name}")
            input_path.rename(new_name)
            return

    # If no valid titles found, don't split or rename
    print("[yellow]Could not detect episode titles; no action taken.[/yellow]")
    return

    # Old logic: split into separate files
    # (This is now commented out in favor of renaming)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Detect intro, optional OCR on title cards, then split video")
    parser.add_argument("input", help="Input video file")
    parser.add_argument("--scene-threshold", type=float, default=0.4, help="Scene detection threshold (ffmpeg)")
    parser.add_argument("--assume-two", action="store_true", help="Assume file has two episodes and split near middle")
    parser.add_argument("--num-episodes", type=int, help="Override episode detection (1 or 2); use if auto-detection fails")
    parser.add_argument("--ocr-lang", default="eng", help="Tesseract language (default: eng)")
    parser.add_argument("--titles-file", type=Path, help="Optional text file with known episode titles (one per line)")
    parser.add_argument("--manual-titles", help="Manual title overrides as 'ep=Title' pairs, e.g. '1=Pups Make a Splash,2=Pups Fall Festival'")
    parser.add_argument("--no-split", action="store_true", help="Analyze + OCR only; do not write output videos")
    parser.add_argument("--json-out", type=Path, help="Optional path to write JSON summary")
    parser.add_argument("--save-frames", type=Path, help="Optional directory to copy OCR sample frames for inspection")
    parser.add_argument(
        "--post-intro-offsets",
        default="-20,-15,-10,-5,0,1,3,5,8,13,15,20,25,30",
        help="Comma-separated seconds after intro end to sample for titles (default: -20,-15,-10,-5,0,1,3,5,8,13,15,20,25,30)",
    )
    parser.add_argument(
        "--episode-offsets",
        default="20,60,120",
        help="Comma-separated seconds from episode start to sample (default: 20,60,120)",
    )
    parser.add_argument(
        "--sample-times",
        help="Explicit samples per episode, e.g. '1=45,2=11:45' (hh:mm:ss, mm:ss, or seconds)",
    )
    parser.add_argument(
        "--series-name",
        help="Series name for TVDB lookup (e.g., 'Paw Patrol'); auto-detected from filename if omitted",
    )
    parser.add_argument(
        "--auto-rename",
        action="store_true",
        help="Automatically rename input file using extracted/matched title (moves original)",
    )
    parser.add_argument("--verbose", action="store_true", help="Print additional detection/OCR details")
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    tvdb_api_key = os.getenv("TVDB_API_KEY")
    
    # Load episodes database for air date detection
    episodes_db = load_episodes_database(Path("episodes.csv"))
    
    # Parse manual title overrides if provided
    manual_titles = parse_manual_titles(args.manual_titles)
    
    run_pipeline(
        input_file=args.input,
        scene_threshold=args.scene_threshold,
        assume_two=args.assume_two,
        ocr_lang=args.ocr_lang,
        titles_path=args.titles_file,
        skip_split=args.no_split,
        verbose=args.verbose,
        json_out=args.json_out,
        save_frames_dir=args.save_frames,
        post_intro_offsets=parse_float_list(args.post_intro_offsets),
        episode_offsets=parse_float_list(args.episode_offsets),
        explicit_samples=parse_sample_times_map(args.sample_times),
        series_name=args.series_name,
        tvdb_api_key=tvdb_api_key,
        num_episodes=args.num_episodes,
        manual_titles=manual_titles,
        episodes_db=episodes_db,
    )
    
    # If manual titles provided and we're not in dry-run mode, rename files using them
    if manual_titles and not args.no_split:
        input_path = Path(args.input)
        base = str(input_path.with_suffix(""))
        for ep_idx, title in manual_titles.items():
            ep_file = f"{base}_ep{ep_idx}.mkv"
            ep_path = Path(ep_file)
            if ep_path.exists():
                slug = slugify_title(title)
                new_name = f"S{ep_idx:02d} - {slug}.mkv"
                new_path = input_path.parent / new_name
                try:
                    ep_path.rename(new_path)
                    print(f"[green]Renamed: {ep_file} → {new_path.name}[/green]")
                except Exception as e:
                    print(f"[yellow]Failed to rename {ep_file}: {e}[/yellow]")

    # Handle auto-rename if requested
    if args.auto_rename and args.sample_times:
        input_path = Path(args.input)
        explicit_samples = parse_sample_times_map(args.sample_times)
        if explicit_samples and len(explicit_samples) >= 1:
            first_ep_idx = min(explicit_samples.keys())
            print(f"\n[cyan]Auto-rename: extracting title for episode {first_ep_idx}[/cyan]")
            
            # Quick re-analyze to get title for first episode
            segments, _, _ = detect_segments(args.input, args.scene_threshold, args.assume_two)
            if segments:
                seg = segments[0]
                with tempfile.TemporaryDirectory() as tmpdir:
                    tmpdir_path = Path(tmpdir)
                    sample_t_list = explicit_samples.get(seg.index, [])
                    if sample_t_list:
                        sample_t = sample_t_list[0]
                        frame_path = tmpdir_path / f"ep_sample.png"
                        try:
                            extract_frame(args.input, sample_t, frame_path)
                            ocr_text = ocr_image(frame_path, args.ocr_lang).strip()
                            title = ocr_text or "unknown"
                            slug = slugify_title(title)
                            ext = input_path.suffix
                            new_name = f"{slug}{ext}"
                            rename_file(input_path, new_name)
                        except Exception as e:
                            print(f"[yellow]Auto-rename failed: {e}[/yellow]")


if __name__ == "__main__":
    main()
