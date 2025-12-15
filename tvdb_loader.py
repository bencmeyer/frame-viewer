#!/usr/bin/env python3
"""
TVDB Episode Database Loader
Fetches episode metadata from TVDB API v4.
"""

import requests
from typing import Dict, Tuple, Optional
from datetime import datetime

# TVDB API Configuration
TVDB_API_URL = "https://api4.thetvdb.com/v4"

class TVDBClient:
    """Client for TVDB API v4."""
    
    def __init__(self, api_key: str):
        self.api_key = api_key
        self.token = None
        self.token_expires = None
    
    def login(self) -> bool:
        """
        Authenticate with TVDB and get bearer token.
        
        Returns:
            True if successful
        """
        try:
            response = requests.post(
                f"{TVDB_API_URL}/login",
                json={"apikey": self.api_key},
                timeout=10
            )
            
            if response.status_code != 200:
                print(f"TVDB login failed: {response.status_code}")
                return False
            
            data = response.json()
            self.token = data['data']['token']
            
            print("✓ TVDB authentication successful")
            return True
            
        except Exception as e:
            print(f"Error logging into TVDB: {e}")
            return False
    
    def get_headers(self) -> Dict[str, str]:
        """Get request headers with bearer token."""
        return {
            "Authorization": f"Bearer {self.token}",
            "Content-Type": "application/json"
        }
    
    def get_series_episodes(self, series_id: int, season: Optional[int] = None) -> Dict[Tuple[int, int], Dict]:
        """
        Fetch all episodes for a series.
        
        Args:
            series_id: TVDB series ID
            season: Optional season number to filter (None for all)
        
        Returns:
            Dict mapping (season, episode) -> episode data
        """
        if not self.token:
            if not self.login():
                return {}
        
        episodes = {}
        page = 0
        
        while True:
            try:
                # Fetch page of episodes
                url = f"{TVDB_API_URL}/series/{series_id}/episodes/default"
                params = {"page": page}
                
                if season is not None:
                    # TVDB v4 doesn't support season filtering in URL
                    # We'll filter after fetching
                    pass
                
                response = requests.get(
                    url,
                    headers=self.get_headers(),
                    params=params,
                    timeout=10
                )
                
                if response.status_code != 200:
                    print(f"Error fetching episodes page {page}: {response.status_code}")
                    break
                
                data = response.json()
                
                # Process episodes
                for ep in data.get('data', {}).get('episodes', []):
                    ep_season = ep.get('seasonNumber')
                    ep_number = ep.get('number')
                    
                    # Skip specials
                    if ep_season == 0:
                        continue
                    
                    # Filter by season if specified
                    if season is not None and ep_season != season:
                        continue
                    
                    if ep_season and ep_number:
                        episodes[(ep_season, ep_number)] = {
                            'title': ep.get('name', ''),
                            'air_date': ep.get('aired', ''),
                            'overview': ep.get('overview', ''),
                            'tvdb_id': ep.get('id', 0)
                        }
                
                # Check if more pages
                links = data.get('links', {})
                if not links.get('next'):
                    break
                
                page += 1
                
            except Exception as e:
                print(f"Error fetching episodes: {e}")
                break
        
        return episodes
    
    def get_season_episodes(self, series_id: int, season: int) -> Dict[Tuple[int, int], Dict]:
        """
        Fetch all episodes for a specific season.
        
        Args:
            series_id: TVDB series ID
            season: Season number
        
        Returns:
            Dict mapping (season, episode) -> episode data
        """
        return self.get_series_episodes(series_id, season=season)


def load_episode_database(seasons: list[int]) -> Dict[Tuple[int, int], Dict]:
    """
    Load episode database for specified seasons.
    
    Args:
        seasons: List of season numbers to load
    
    Returns:
        Dict mapping (season, episode) -> episode data
    """
    client = TVDBClient(TVDB_API_KEY)
    
    if not client.login():
        print("Failed to authenticate with TVDB")
        return {}
    
    all_episodes = {}
    
    for season in seasons:
        print(f"Fetching Season {season} episodes from TVDB...")
        
        episodes = client.get_season_episodes(TVDB_SERIES_ID, season)
        all_episodes.update(episodes)
        
        print(f"  ✓ Loaded {len(episodes)} episodes")
    
    return all_episodes


def main():
    """Test TVDB episode loading."""
    print("Testing TVDB Episode Database Loader\n")
    
    # Load Season 9 episodes
    episodes = load_episode_database([9])
    
    if episodes:
        print(f"\n✓ Successfully loaded {len(episodes)} episodes")
        print("\nSample episodes:")
        
        for (season, ep_num), data in sorted(episodes.items())[:5]:
            print(f"  S{season:02d}E{ep_num:02d}: {data['title']}")
            if data['air_date']:
                print(f"    Aired: {data['air_date']}")
    else:
        print("\n✗ Failed to load episodes")


if __name__ == '__main__':
    main()
