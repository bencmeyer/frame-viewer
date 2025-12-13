#!/usr/bin/env python3
"""
Frame Viewer Server
A Flask-based web server for extracting and viewing video frames
and matching them to TVDB episodes
"""

import os
import subprocess
import json
import base64
import re
from pathlib import Path
from flask import Flask, render_template, request, jsonify
from flask_cors import CORS
from tvdb_loader import TVDBClient
import requests

app = Flask(__name__)
CORS(app)

# Load configuration from environment variables
TVDB_API_KEY = os.getenv('TVDB_API_KEY', '585432a6-f441-4db3-a106-2d5a05fa95d7')
SONARR_URL = os.getenv('SONARR_URL', 'http://10.0.1.90:8993')
SONARR_API_KEY = os.getenv('SONARR_API_KEY', 'd6903236b2c24107b60c5f9423fc30e7')
VIDEO_PATH = os.getenv('VIDEO_PATH', f'/run/user/{os.getuid()}/gvfs/smb-share:server=redpanda.local,share=data/media/tv')
FLASK_HOST = os.getenv('FLASK_HOST', '0.0.0.0')
FLASK_PORT = int(os.getenv('FLASK_PORT', '5000'))
FLASK_DEBUG = os.getenv('FLASK_DEBUG', 'true').lower() == 'true'

# Parse Sonarr URL
if SONARR_URL:
    SONARR_BASE_URL = f"{SONARR_URL.rstrip('/')}/api/v3"
else:
    SONARR_BASE_URL = None

# Global TVDB client
tvdb_client = None

def sonarr_request(endpoint: str, params: dict = None) -> dict:
    """Make authenticated request to Sonarr API."""
    if not SONARR_BASE_URL or not SONARR_API_KEY:
        return None
    
    headers = {"X-Api-Key": SONARR_API_KEY}
    url = f"{SONARR_BASE_URL}/{endpoint}"
    try:
        response = requests.get(url, headers=headers, params=params, timeout=10)
        response.raise_for_status()
        return response.json()
    except requests.exceptions.RequestException as e:
        print(f"Sonarr API Error: {e}")
        return None

def extract_frames(video_path, start_time=0, num_frames=10, interval=1.0):
    """
    Extract frames from a video file
    
    Args:
        video_path: Path to the video file
        start_time: Starting time in seconds
        num_frames: Number of frames to extract
        interval: Time interval between frames in seconds
    
    Returns:
        List of base64-encoded image data
    """
    frames = []
    
    for i in range(num_frames):
        timestamp = start_time + (i * interval)
        
        # Use ffmpeg to extract a single frame
        cmd = [
            'ffmpeg',
            '-ss', str(timestamp),
            '-i', video_path,
            '-vframes', '1',
            '-f', 'image2pipe',
            '-vcodec', 'png',
            '-'
        ]
        
        try:
            result = subprocess.run(
                cmd,
                capture_output=True,
                check=True
            )
            
            # Convert to base64 for transmission
            img_base64 = base64.b64encode(result.stdout).decode('utf-8')
            frames.append({
                'index': i,
                'timestamp': timestamp,
                'data': f'data:image/png;base64,{img_base64}'
            })
            
        except subprocess.CalledProcessError as e:
            print(f"Error extracting frame at {timestamp}s: {e}")
            continue
    
    return frames


def get_video_duration(video_path):
    """Get the duration of a video in seconds"""
    cmd = [
        'ffprobe',
        '-v', 'error',
        '-show_entries', 'format=duration',
        '-of', 'json',
        video_path
    ]
    
    try:
        result = subprocess.run(cmd, capture_output=True, check=True, text=True)
        data = json.loads(result.stdout)
        return float(data['format']['duration'])
    except Exception as e:
        print(f"Error getting video duration: {e}")
        return None


@app.route('/')
def index():
    """Serve the main page"""
    return render_template('frame_viewer.html')


@app.route('/api/list_videos', methods=['GET'])
def list_videos():
    """List all video files in the workspace organized by folder"""
    video_extensions = {'.mkv', '.mp4', '.avi', '.mov', '.m4v', '.webm'}
    
    workspace_path = Path(VIDEO_PATH)
    
    # Build folder tree structure with natural sorting
    folder_tree = {}
    folder_count = 0
    max_folders = 500  # Limit to prevent timeout on huge libraries
    
    print(f"Scanning video library at: {workspace_path}")
    
    for root, dirs, files in os.walk(workspace_path):
        # Skip __pycache__ and hidden directories
        dirs[:] = [d for d in dirs if not d.startswith('.') and d != '__pycache__']
        
        # Sort directories naturally (Season 1, Season 2, ..., Season 10, Season 11)
        def natural_sort_key(s):
            import re
            return [int(text) if text.isdigit() else text.lower() 
                    for text in re.split('([0-9]+)', s)]
        dirs.sort(key=natural_sort_key)
        
        # Get video files in this directory
        video_files = []
        for file in files:
            if Path(file).suffix.lower() in video_extensions:
                full_path = Path(root) / file
                video_files.append({
                    'path': str(full_path),
                    'name': file,
                    'type': 'file'
                })
        
        # Only include folders with video files
        if video_files:
            rel_path = Path(root).relative_to(workspace_path)
            folder_key = str(rel_path) if str(rel_path) != '.' else 'Root'
            
            folder_tree[folder_key] = {
                'path': str(root),
                'files': sorted(video_files, key=lambda x: natural_sort_key(x['name'])),
                'type': 'folder'
            }
            
            folder_count += 1
            if folder_count % 50 == 0:
                print(f"Scanned {folder_count} folders with videos...")
            
            # Limit total folders to prevent timeout
            if folder_count >= max_folders:
                print(f"Reached folder limit ({max_folders}), stopping scan")
                break
    
    print(f"Scan complete: {folder_count} folders, {sum(len(f['files']) for f in folder_tree.values())} videos")
    return jsonify(folder_tree)


@app.route('/api/extract_frames', methods=['POST'])
def extract_frames_endpoint():
    """Extract frames from a video"""
    data = request.json
    
    video_path = data.get('video_path')
    start_time = float(data.get('start_time', 0))
    num_frames = int(data.get('num_frames', 10))
    interval = float(data.get('interval', 1.0))
    
    if not video_path or not os.path.exists(video_path):
        return jsonify({'error': 'Video file not found'}), 404
    
    # Get video duration
    duration = get_video_duration(video_path)
    
    # Extract frames
    frames = extract_frames(video_path, start_time, num_frames, interval)
    
    # Try to parse season/episode from filename
    parsed_info = parse_filename(video_path)
    
    return jsonify({
        'frames': frames,
        'duration': duration,
        'video_path': video_path,
        'parsed_info': parsed_info
    })


@app.route('/api/search_series', methods=['GET'])
def search_series():
    """Search for TV series on TVDB"""
    global tvdb_client
    
    query = request.args.get('q', '')
    if not query:
        return jsonify({'error': 'Query parameter required'}), 400
    
    # Initialize TVDB client if needed
    if not tvdb_client:
        tvdb_client = TVDBClient(TVDB_API_KEY)
        if not tvdb_client.login():
            return jsonify({'error': 'Failed to authenticate with TVDB'}), 500
    
    try:
        url = f"https://api4.thetvdb.com/v4/search"
        params = {'query': query, 'type': 'series'}
        response = requests.get(
            url,
            headers=tvdb_client.get_headers(),
            params=params,
            timeout=10
        )
        
        if response.status_code != 200:
            return jsonify({'error': f'TVDB API error: {response.status_code}'}), 500
        
        data = response.json()
        series_list = []
        
        for item in data.get('data', []):
            series_list.append({
                'id': item.get('tvdb_id'),
                'name': item.get('name'),
                'year': item.get('year'),
                'image': item.get('image_url'),
                'overview': item.get('overview', '')[:200] if item.get('overview') else ''
            })
        
        return jsonify({'series': series_list})
        
    except Exception as e:
        return jsonify({'error': str(e)}), 500


@app.route('/api/series/<int:series_id>/seasons', methods=['GET'])
def get_series_seasons(series_id):
    """Get all seasons for a series"""
    global tvdb_client
    
    if not tvdb_client:
        tvdb_client = TVDBClient(TVDB_API_KEY)
        if not tvdb_client.login():
            return jsonify({'error': 'Failed to authenticate with TVDB'}), 500
    
    try:
        # Get all episodes to determine available seasons
        episodes = tvdb_client.get_series_episodes(series_id)
        
        # Group by season
        seasons = {}
        for (season, ep_num), ep_data in episodes.items():
            if season not in seasons:
                seasons[season] = []
            seasons[season].append({
                'episode_number': ep_num,
                'title': ep_data['title'],
                'air_date': ep_data['air_date'],
                'tvdb_id': ep_data['tvdb_id']
            })
        
        # Sort episodes within each season
        for season in seasons:
            seasons[season].sort(key=lambda x: x['episode_number'])
        
        return jsonify({'seasons': seasons})
        
    except Exception as e:
        return jsonify({'error': str(e)}), 500


@app.route('/api/series/<int:series_id>/season/<int:season_num>', methods=['GET'])
def get_season_episodes(series_id, season_num):
    """Get all episodes for a specific season"""
    global tvdb_client
    
    if not tvdb_client:
        tvdb_client = TVDBClient(TVDB_API_KEY)
        if not tvdb_client.login():
            return jsonify({'error': 'Failed to authenticate with TVDB'}), 500
    
    try:
        episodes = tvdb_client.get_season_episodes(series_id, season_num)
        
        episode_list = []
        for (season, ep_num), ep_data in sorted(episodes.items()):
            episode_list.append({
                'season': season,
                'episode': ep_num,
                'title': ep_data['title'],
                'air_date': ep_data['air_date'],
                'overview': ep_data['overview'],
                'tvdb_id': ep_data['tvdb_id']
            })
        
        return jsonify({'episodes': episode_list})
        
    except Exception as e:
        return jsonify({'error': str(e)}), 500


@app.route('/api/rename_file', methods=['POST'])
def rename_file():
    """Rename a video file"""
    data = request.json
    
    old_path = data.get('old_path')
    new_name = data.get('new_name')
    
    if not old_path or not new_name:
        return jsonify({'error': 'Missing required parameters'}), 400
    
    if not os.path.exists(old_path):
        return jsonify({'error': 'File not found'}), 404
    
    try:
        old_path_obj = Path(old_path)
        new_path = old_path_obj.parent / new_name
        
        # Check if target already exists
        if new_path.exists():
            return jsonify({'error': 'Target file already exists'}), 400
        
        # Rename the file
        os.rename(old_path, new_path)
        
        return jsonify({
            'success': True,
            'old_path': str(old_path),
            'new_path': str(new_path)
        })
        
    except Exception as e:
        return jsonify({'error': str(e)}), 500


@app.route('/api/sonarr/search', methods=['GET'])
def sonarr_search_series():
    """Search for series in Sonarr"""
    query = request.args.get('q', '')
    if not query:
        return jsonify({'error': 'Query parameter required'}), 400
    
    try:
        series_list = sonarr_request("series")
        if series_list is None:
            return jsonify({'error': 'Failed to connect to Sonarr'}), 500
        
        # Filter by query
        results = []
        for series in series_list:
            if query.lower() in series.get('title', '').lower():
                results.append({
                    'id': series['id'],
                    'title': series['title'],
                    'year': series.get('year'),
                    'tvdb_id': series.get('tvdbId'),
                    'path': series.get('path'),
                    'statistics': series.get('statistics', {})
                })
        
        return jsonify({'series': results})
        
    except Exception as e:
        return jsonify({'error': str(e)}), 500


@app.route('/api/sonarr/series/<int:series_id>/missing', methods=['GET'])
def sonarr_missing_episodes(series_id):
    """Get missing episodes for a series from Sonarr"""
    season = request.args.get('season', type=int)
    
    try:
        episodes = sonarr_request(f"episode", params={'seriesId': series_id})
        if episodes is None:
            return jsonify({'error': 'Failed to connect to Sonarr'}), 500
        
        missing = []
        for ep in episodes:
            # Filter by season if specified
            if season is not None and ep['seasonNumber'] != season:
                continue
            
            # Skip season 0 (specials)
            if ep['seasonNumber'] == 0:
                continue
            
            if not ep.get('hasFile', False):
                missing.append({
                    'season': ep['seasonNumber'],
                    'episode': ep['episodeNumber'],
                    'title': ep.get('title', ''),
                    'airDate': ep.get('airDate', ''),
                    'airDateUtc': ep.get('airDateUtc', ''),
                    'monitored': ep.get('monitored', False)
                })
        
        # Sort by season and episode
        missing.sort(key=lambda x: (x['season'], x['episode']))
        
        return jsonify({'missing': missing})
        
    except Exception as e:
        return jsonify({'error': str(e)}), 500


@app.route('/api/sonarr/series/<int:series_id>/files', methods=['GET'])
def sonarr_series_files(series_id):
    """Get all episode files for a series from Sonarr"""
    season = request.args.get('season', type=int)
    
    try:
        # Get episodes with files
        episodes = sonarr_request(f"episode", params={'seriesId': series_id})
        if episodes is None:
            return jsonify({'error': 'Failed to connect to Sonarr'}), 500
        
        files = []
        episode_file_ids = set()
        
        for ep in episodes:
            # Filter by season if specified
            if season is not None and ep['seasonNumber'] != season:
                continue
            
            # Skip season 0 (specials)
            if ep['seasonNumber'] == 0:
                continue
            
            if ep.get('hasFile', False) and ep.get('episodeFileId'):
                file_id = ep['episodeFileId']
                
                # Collect all episodes for this file
                if file_id not in episode_file_ids:
                    episode_file_ids.add(file_id)
        
        # Get file details for each unique file
        for file_id in episode_file_ids:
            try:
                file_data = sonarr_request(f"episodefile/{file_id}")
                if file_data:
                    # Find all episodes using this file
                    file_episodes = []
                    for ep in episodes:
                        if ep.get('episodeFileId') == file_id:
                            file_episodes.append({
                                'season': ep['seasonNumber'],
                                'episode': ep['episodeNumber'],
                                'title': ep.get('title', '')
                            })
                    
                    file_episodes.sort(key=lambda x: (x['season'], x['episode']))
                    
                    files.append({
                        'id': file_id,
                        'path': file_data.get('path', ''),
                        'relativePath': file_data.get('relativePath', ''),
                        'size': file_data.get('size', 0),
                        'quality': file_data.get('quality', {}).get('quality', {}).get('name', ''),
                        'episodes': file_episodes
                    })
            except Exception as e:
                print(f"Error fetching file {file_id}: {e}")
                continue
        
        # Sort by season and episode
        files.sort(key=lambda x: (x['episodes'][0]['season'] if x['episodes'] else 0, 
                                  x['episodes'][0]['episode'] if x['episodes'] else 0))
        
        return jsonify({'files': files})
        
    except Exception as e:
        return jsonify({'error': str(e)}), 500


@app.route('/api/unified/series/<int:tvdb_id>/season/<int:season_num>', methods=['GET'])
def unified_season_view(tvdb_id, season_num):
    """
    Get unified view of episodes combining TVDB data with Sonarr status.
    Returns episodes with status (missing/matched) and file info if available.
    """
    sonarr_id = request.args.get('sonarr_id', type=int)
    
    try:
        # Get TVDB episode data
        if not tvdb_client:
            init_tvdb()
        
        tvdb_episodes = tvdb_client.get_season_episodes(tvdb_id, season_num)
        
        # Initialize result with TVDB data
        unified_episodes = []
        for (season, ep_num), ep_data in sorted(tvdb_episodes.items()):
            unified_episodes.append({
                'season': season,
                'episode': ep_num,
                'title': ep_data['title'],
                'air_date': ep_data['air_date'],
                'overview': ep_data['overview'],
                'tvdb_id': ep_data['tvdb_id'],
                'status': 'unknown',  # Will be updated if Sonarr data available
                'has_file': False,
                'file_info': None
            })
        
        # If Sonarr ID provided, merge Sonarr status
        if sonarr_id:
            sonarr_episodes = sonarr_request(f"episode", params={'seriesId': sonarr_id})
            if sonarr_episodes:
                # Create lookup for file info
                file_lookup = {}  # file_id -> file_data
                
                # Get all file IDs and fetch their data
                file_ids = set()
                for ep in sonarr_episodes:
                    if ep.get('hasFile') and ep.get('episodeFileId'):
                        file_ids.add(ep['episodeFileId'])
                
                for file_id in file_ids:
                    try:
                        file_data = sonarr_request(f"episodefile/{file_id}")
                        if file_data:
                            file_lookup[file_id] = {
                                'path': file_data.get('path', ''),
                                'relativePath': file_data.get('relativePath', ''),
                                'size': file_data.get('size', 0),
                                'quality': file_data.get('quality', {}).get('quality', {}).get('name', '')
                            }
                    except:
                        pass
                
                # Update unified episodes with Sonarr data
                for unified_ep in unified_episodes:
                    # Find matching Sonarr episode
                    sonarr_ep = next(
                        (ep for ep in sonarr_episodes 
                         if ep['seasonNumber'] == unified_ep['season'] 
                         and ep['episodeNumber'] == unified_ep['episode']),
                        None
                    )
                    
                    if sonarr_ep:
                        unified_ep['has_file'] = sonarr_ep.get('hasFile', False)
                        unified_ep['status'] = 'matched' if unified_ep['has_file'] else 'missing'
                        unified_ep['monitored'] = sonarr_ep.get('monitored', False)
                        
                        if unified_ep['has_file']:
                            file_id = sonarr_ep.get('episodeFileId')
                            if file_id and file_id in file_lookup:
                                unified_ep['file_info'] = file_lookup[file_id]
        
        # Group episodes by air date to identify multi-episode releases
        by_date = {}
        for ep in unified_episodes:
            date = ep['air_date']
            if date:
                if date not in by_date:
                    by_date[date] = []
                by_date[date].append(ep['episode'])
        
        # Mark episodes that aired together
        for ep in unified_episodes:
            date = ep['air_date']
            if date and len(by_date.get(date, [])) > 1:
                ep['multi_episode_date'] = True
                ep['same_day_episodes'] = by_date[date]
            else:
                ep['multi_episode_date'] = False
        
        return jsonify({'episodes': unified_episodes})
        
    except Exception as e:
        return jsonify({'error': str(e)}), 500


def init_tvdb():
    """Initialize TVDB client if not already done"""
    global tvdb_client
    if not tvdb_client:
        tvdb_client = TVDBClient(TVDB_API_KEY)
        if not tvdb_client.login():
            raise Exception('Failed to authenticate with TVDB')


@app.route('/api/sonarr/series', methods=['GET'])
def sonarr_list_series():
    """List all series in Sonarr"""
    try:
        series_list = sonarr_request("series")
        if series_list is None:
            return jsonify({'error': 'Failed to connect to Sonarr'}), 500
        
        results = []
        for series in series_list:
            stats = series.get('statistics', {})
            results.append({
                'id': series['id'],
                'title': series['title'],
                'year': series.get('year'),
                'tvdb_id': series.get('tvdbId'),
                'seasonCount': stats.get('seasonCount', 0),
                'episodeCount': stats.get('episodeCount', 0),
                'episodeFileCount': stats.get('episodeFileCount', 0),
                'totalEpisodeCount': stats.get('totalEpisodeCount', 0),
                'percentOfEpisodes': stats.get('percentOfEpisodes', 0)
            })
        
        # Sort by title
        results.sort(key=lambda x: x['title'])
        
        return jsonify({'series': results})
        
    except Exception as e:
        return jsonify({'error': str(e)}), 500


def parse_filename(filepath):
    """
    Parse season and episode information from filename
    
    Returns dict with show_name, season, episodes, etc.
    """
    filename = Path(filepath).name
    
    result = {
        'show_name': None,
        'season': None,
        'episodes': [],
        'title': None,
        'quality': None,
        'source': None
    }
    
    # Pattern: Show Name (Year) - S##E## or S##E##-E##
    pattern = r'^(.+?)\s*(?:\((\d{4})\))?\s*-\s*S(\d+)E(\d+)(?:-E(\d+))?\s*-\s*(.+?)\s*\[([^\]]+)\]'
    match = re.search(pattern, filename, re.IGNORECASE)
    
    if match:
        result['show_name'] = match.group(1).strip()
        result['year'] = match.group(2)
        result['season'] = int(match.group(3))
        
        ep_start = int(match.group(4))
        ep_end = match.group(5)
        
        if ep_end:
            result['episodes'] = list(range(ep_start, int(ep_end) + 1))
        else:
            result['episodes'] = [ep_start]
        
        result['title'] = match.group(6).strip()
        result['quality'] = match.group(7).strip()
    
    return result


if __name__ == '__main__':
    app.run(debug=FLASK_DEBUG, host=FLASK_HOST, port=FLASK_PORT)
