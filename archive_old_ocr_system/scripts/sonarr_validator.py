#!/usr/bin/env python3
"""
Sonarr integration to identify mislabeled files.
Compares Sonarr's "missing" episodes with actual air dates to find multi-episode files.
"""

import requests
import json
from typing import Dict, List, Tuple
from datetime import datetime

SONARR_HOST = "10.0.1.90"
SONARR_PORT = 8993
SONARR_API_KEY = "d6903236b2c24107b60c5f9423fc30e7"
SONARR_BASE_URL = f"http://{SONARR_HOST}:{SONARR_PORT}/api/v3"

def sonarr_request(endpoint: str, params: dict = None) -> dict:
    """Make authenticated request to Sonarr API."""
    headers = {"X-Api-Key": SONARR_API_KEY}
    url = f"{SONARR_BASE_URL}/{endpoint}"
    try:
        response = requests.get(url, headers=headers, params=params, timeout=10)
        response.raise_for_status()
        return response.json()
    except requests.exceptions.RequestException as e:
        print(f"❌ Sonarr API Error: {e}")
        return {}

def get_series_by_name(series_name: str) -> dict:
    """Find series ID by name."""
    series_list = sonarr_request("series")
    for series in series_list:
        if series["title"].lower() == series_name.lower():
            return series
    return {}

def get_series_episodes(series_id: int) -> Dict[Tuple[int, int], dict]:
    """Get all episodes for a series, indexed by (season, episode)."""
    episodes = sonarr_request(f"series/{series_id}/episodes")
    result = {}
    for ep in episodes:
        key = (ep["seasonNumber"], ep["episodeNumber"])
        result[key] = {
            "title": ep.get("title", ""),
            "airDate": ep.get("airDate", ""),
            "hasFile": ep.get("hasFile", False),
            "episodeFileId": ep.get("episodeFileId"),
        }
    return result

def get_missing_episodes(series_id: int, season: int) -> List[Tuple[int, str, str]]:
    """Get missing episodes for a season. Returns list of (episode_num, title, air_date)."""
    episodes = sonarr_request(f"series/{series_id}/episodes")
    missing = []
    
    for ep in episodes:
        if ep["seasonNumber"] == season and not ep.get("hasFile", False):
            ep_num = ep["episodeNumber"]
            title = ep.get("title", "Unknown")
            air_date = ep.get("airDate", "")
            missing.append((ep_num, title, air_date))
    
    return missing

def get_season_episodes_by_date(series_id: int, season: int) -> Dict[str, List[Tuple[int, str]]]:
    """Group season episodes by air date. Returns {air_date: [(ep_num, title), ...]}"""
    episodes = sonarr_request(f"series/{series_id}/episodes")
    by_date = {}
    
    for ep in episodes:
        if ep["seasonNumber"] == season:
            air_date = ep.get("airDate", "")
            ep_num = ep["episodeNumber"]
            title = ep.get("title", "")
            
            if air_date not in by_date:
                by_date[air_date] = []
            by_date[air_date].append((ep_num, title))
    
    return by_date

def analyze_missing_episodes(series_name: str, season: int):
    """Analyze missing episodes and find candidates for mislabeling."""
    print(f"\n{'='*60}")
    print(f"Analyzing {series_name} Season {season}")
    print(f"{'='*60}")
    
    # Get series
    series = get_series_by_name(series_name)
    if not series:
        print(f"❌ Series '{series_name}' not found in Sonarr")
        return
    
    series_id = series["id"]
    print(f"✓ Found series ID: {series_id}")
    
    # Get missing episodes
    missing = get_missing_episodes(series_id, season)
    if not missing:
        print(f"✓ No missing episodes in Season {season}")
        return
    
    print(f"\n📊 Missing Episodes ({len(missing)} total):")
    print(f"{'Ep':<4} {'Title':<40} {'Air Date':<12}")
    print("-" * 58)
    
    for ep_num, title, air_date in missing:
        print(f"E{ep_num:<2} {title[:38]:<40} {air_date:<12}")
    
    # Group by air date
    episodes_by_date = get_season_episodes_by_date(series_id, season)
    
    print(f"\n📅 Episodes Grouped by Air Date:")
    print("-" * 58)
    
    for air_date in sorted(episodes_by_date.keys()):
        episodes = episodes_by_date[air_date]
        ep_nums = [ep[0] for ep in episodes]
        titles = [ep[1] for ep in episodes]
        
        # Check if this date contains missing episodes
        missing_on_date = [e for e in missing if e[2] == air_date]
        
        if len(episodes) > 1:
            # Multi-episode air date
            ep_range = f"E{ep_nums[0]}-E{ep_nums[-1]}"
            marker = " 🔴 CANDIDATE" if missing_on_date else ""
            print(f"{air_date}: {ep_range:<20} {marker}")
            for i, (ep_num, title) in enumerate(episodes):
                has_missing = any(m[0] == ep_num for m in missing_on_date)
                marker = " ← MISSING" if has_missing else ""
                print(f"  E{ep_num}: {title}{marker}")
        elif missing_on_date:
            # Single episode but some missing on same date
            ep_num = ep_nums[0]
            print(f"{air_date}: E{ep_num} (Title: {titles[0]})")
            for m in missing_on_date:
                print(f"  ← MISSING: E{m[0]} {m[1]}")
    
    # Summary
    print(f"\n💡 Recommendation:")
    print("If a file is labeled as a single episode (e.g., S09E20)")
    print("but Sonarr is also missing E21 on the same air date,")
    print("the file likely contains both episodes E20-E21.")
    print("Use OCR to verify and rename accordingly.")

if __name__ == "__main__":
    try:
        # Test connection
        print("Testing Sonarr connection...")
        status = sonarr_request("system/status")
        if status:
            print(f"✓ Connected to Sonarr: {status.get('appName', 'Unknown')}")
        else:
            print("❌ Failed to connect to Sonarr")
            exit(1)
        
        # Analyze seasons (series name is just "Paw Patrol")
        analyze_missing_episodes("Paw Patrol", 9)
        analyze_missing_episodes("Paw Patrol", 10)
        
    except Exception as e:
        print(f"Error: {e}")
        import traceback
        traceback.print_exc()
