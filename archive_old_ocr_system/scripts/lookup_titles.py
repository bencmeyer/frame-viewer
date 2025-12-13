#!/usr/bin/env python3
"""Quick TVDB title lookup helper."""
import os
import sys
import requests

def lookup_tvdb_episode(series_name: str, season: int, episode: int) -> str:
    """Look up episode title from TVDB."""
    api_key = os.getenv("TVDB_API_KEY")
    if not api_key:
        print("[ERROR] TVDB_API_KEY not set", file=sys.stderr)
        return ""
    
    try:
        # Search for series
        headers = {"Authorization": f"Bearer {api_key}"}
        resp = requests.get(
            "https://api4.thetvdb.com/v4/search",
            params={"query": series_name, "type": "series"},
            headers=headers,
            timeout=5,
        )
        resp.raise_for_status()
        data = resp.json()
        if not data.get("data"):
            print(f"[ERROR] Series '{series_name}' not found", file=sys.stderr)
            return ""
        
        series_id = data["data"][0]["tvdb_id"]
        print(f"Found series ID: {series_id}", file=sys.stderr)
        
        # Get episode
        resp = requests.get(
            f"https://api4.thetvdb.com/v4/series/{series_id}/episodes/default",
            headers=headers,
            timeout=5,
        )
        resp.raise_for_status()
        eps = resp.json().get("data", {}).get("episodes", [])
        for ep in eps:
            if ep.get("seasonNumber") == season and ep.get("number") == episode:
                return ep.get("name", "")
        
        print(f"[ERROR] Episode S{season}E{episode} not found", file=sys.stderr)
        return ""
    
    except Exception as e:
        print(f"[ERROR] {e}", file=sys.stderr)
        return ""

if __name__ == "__main__":
    if len(sys.argv) != 4:
        print("Usage: lookup_titles.py <series_name> <season> <episode>")
        sys.exit(1)
    
    series_name = sys.argv[1]
    season = int(sys.argv[2])
    episode = int(sys.argv[3])
    
    title = lookup_tvdb_episode(series_name, season, episode)
    print(title)
