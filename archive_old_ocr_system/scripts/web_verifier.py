#!/usr/bin/env python3
"""
Web-based title card verification interface.
Quick visual inspection with instant feedback.
Generic for any TV show via config.json
"""

from flask import Flask, render_template_string, request, jsonify, send_from_directory
from pathlib import Path
import json
from episode_detector import parse_filename_episodes
from tvdb_loader import load_episode_database
import os

app = Flask(__name__)

# Load configuration
def load_config():
    """Load config from config.json or environment variables."""
    config = {
        "show_name": "Paw Patrol",
        "tvdb_series_id": 272472,
        "season": 9,
        "season_dir": "Paw Patrol/Season 09",
        "candidates_dir": "title_card_candidates",
        "verification_file": "verified_s09.json"
    }
    
    # Try to load from config.json
    config_file = Path("config.json")
    if config_file.exists():
        try:
            with open(config_file) as f:
                file_config = json.load(f)
                config.update(file_config)
        except Exception as e:
            print(f"Warning: Could not load config.json: {e}")
    
    # Environment variables override config file
    if os.getenv("TVDB_SERIES_ID"):
        config["tvdb_series_id"] = int(os.getenv("TVDB_SERIES_ID"))
    if os.getenv("SEASON"):
        config["season"] = int(os.getenv("SEASON"))
    if os.getenv("SEASON_DIR"):
        config["season_dir"] = os.getenv("SEASON_DIR")
    if os.getenv("SHOW_NAME"):
        config["show_name"] = os.getenv("SHOW_NAME")
    
    return config

CONFIG = load_config()

# Configuration
SHOW_NAME = CONFIG["show_name"]
TVDB_SERIES_ID = CONFIG["tvdb_series_id"]
SEASON = CONFIG["season"]
SEASON_DIR = Path(CONFIG["season_dir"])
CANDIDATES_DIR = Path(CONFIG["candidates_dir"])
VERIFICATION_FILE = Path(CONFIG["verification_file"])

# Load data
verified_episodes = {}
episode_database = {}

def load_data():
    """Load TVDB episodes and verifications."""
    global episode_database, verified_episodes
    
    if VERIFICATION_FILE.exists():
        with open(VERIFICATION_FILE) as f:
            verified_episodes = json.load(f)
    
    # Load TVDB episodes
    try:
        episode_database = load_episode_database([SEASON])
    except:
        print("Warning: Could not load TVDB data")

def get_all_files():
    """Get all video files with their candidates."""
    files = []
    
    video_files = sorted(SEASON_DIR.glob("*.mkv"))
    video_files.extend(sorted(SEASON_DIR.glob("*.mp4")))
    
    # Build mapping of episodes to filenames for duplicate detection
    episode_to_file = {}  # {episode_num: filename}
    for fname, ep_data in verified_episodes.items():
        for ep_num in ep_data.get('episodes', []):
            episode_to_file[ep_num] = fname
    
    for video_path in video_files:
        candidates_dir = CANDIDATES_DIR / video_path.stem
        
        if not candidates_dir.exists():
            continue
        
        # Get candidate frames
        frames = sorted(candidates_dir.glob("*.png"))
        if not frames:
            continue
        
        # Parse filename info
        _, filename_episodes = parse_filename_episodes(video_path.name)
        
        # Get verified info
        verified = verified_episodes.get(video_path.name, {})
        
        # Build all episode titles (all 46 episodes in season)
        all_episode_titles = {}
        all_episode_air_dates = {}
        verified_eps = set()
        for ep_data in verified_episodes.values():
            verified_eps.update(ep_data.get('episodes', []))
        
        for ep_num in range(1, 47):  # Season 9 has 46 episodes
            ep_info = episode_database.get((SEASON, ep_num), {})
            all_episode_titles[ep_num] = ep_info.get('title', f'Episode {ep_num}')
            all_episode_air_dates[ep_num] = ep_info.get('air_date', '')
        
        files.append({
            'filename': video_path.name,
            'short_name': video_path.name[:60] + '...' if len(video_path.name) > 60 else video_path.name,
            'filename_episodes': filename_episodes,
            'verified_episodes': verified.get('episodes', []),
            'verified_timestamp': verified.get('title_card_timestamp', 0),
            'verified_notes': verified.get('notes', ''),
            'is_verified': video_path.name in verified_episodes,
            'frames': [{'path': str(f), 'name': f.name} for f in frames],
            'episode_titles': all_episode_titles,
            'episode_air_dates': all_episode_air_dates,
            'verified_eps': list(verified_eps),
            'episode_to_file': episode_to_file
        })
    
    return files

HTML_TEMPLATE = r'''
<!DOCTYPE html>
<html>
<head>
    <title>Paw Patrol Episode Verification</title>
    <style>
        * { margin: 0; padding: 0; box-sizing: border-box; }
        body { font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif; background: #f5f5f5; }
        
        .container { max-width: 1600px; margin: 0 auto; padding: 20px; }
        
        header {
            background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
            color: white;
            padding: 20px;
            border-radius: 8px;
            margin-bottom: 30px;
        }
        
        header h1 { font-size: 28px; margin-bottom: 5px; }
        header p { opacity: 0.9; }
        
        .stats {
            display: flex;
            gap: 20px;
            margin-top: 15px;
            font-size: 14px;
        }
        
        .stat { display: flex; gap: 5px; }
        .stat-number { font-weight: bold; font-size: 18px; }
        
        .file-grid {
            display: grid;
            grid-template-columns: 1fr;
            gap: 30px;
        }
        
        .file-card {
            background: white;
            border-radius: 8px;
            overflow: hidden;
            box-shadow: 0 2px 8px rgba(0,0,0,0.1);
            transition: box-shadow 0.3s;
        }
        
        .file-card:hover { box-shadow: 0 4px 16px rgba(0,0,0,0.15); }
        
        .file-header {
            background: #f9f9f9;
            padding: 15px 20px;
            border-bottom: 1px solid #e0e0e0;
            display: flex;
            justify-content: space-between;
            align-items: center;
        }
        
        .file-name {
            font-weight: 500;
            font-size: 14px;
            flex: 1;
        }
        
        .file-status {
            padding: 4px 12px;
            border-radius: 20px;
            font-size: 12px;
            font-weight: 500;
        }
        
        .status-verified { background: #d4edda; color: #155724; }
        .status-pending { background: #fff3cd; color: #856404; }
        
        .file-content {
            padding: 20px;
        }
        
        .episode-info {
            margin-bottom: 15px;
            padding-bottom: 15px;
            border-bottom: 1px solid #e0e0e0;
        }
        
        .info-row {
            display: flex;
            gap: 20px;
            margin-bottom: 8px;
            font-size: 13px;
        }
        
        .info-label { font-weight: 500; color: #666; min-width: 120px; }
        .info-value { color: #333; }
        
        .frames-container {
            display: grid;
            grid-template-columns: repeat(auto-fill, minmax(200px, 1fr));
            gap: 15px;
            margin-bottom: 20px;
        }
        
        .frame-item {
            position: relative;
            cursor: pointer;
            border: 2px solid transparent;
            border-radius: 6px;
            overflow: hidden;
            transition: all 0.2s;
        }
        
        .frame-item:hover { border-color: #667eea; }
        .frame-item.selected { border-color: #28a745; background: #f0f8f4; }
        
        .frame-img {
            width: 100%;
            height: 120px;
            object-fit: cover;
            transition: transform 0.3s, filter 0.3s;
        }
        
        .frame-item.zoomed .frame-img {
            transform: scale(1.5);
            filter: brightness(1.2);
        }
        
        .frame-label {
            padding: 8px;
            font-size: 12px;
            color: #666;
            text-align: center;
            background: #fafafa;
        }
        
        .frame-label.selected { background: #e8f5e9; color: #2e7d32; font-weight: 500; }
        
        .control-panel {
            display: flex;
            gap: 10px;
            flex-wrap: wrap;
            margin-bottom: 20px;
        }
        
        input[type="text"] {
            flex: 1;
            min-width: 150px;
            padding: 8px 12px;
            border: 1px solid #ddd;
            border-radius: 4px;
            font-size: 13px;
        }
        
        button {
            padding: 8px 16px;
            border: none;
            border-radius: 4px;
            font-size: 13px;
            font-weight: 500;
            cursor: pointer;
            transition: all 0.2s;
        }
        
        .btn-save { background: #28a745; color: white; }
        .btn-save:hover { background: #218838; }
        
        .btn-skip { background: #6c757d; color: white; }
        .btn-skip:hover { background: #5a6268; }
        .btn-rescan { background: #17a2b8; color: white; }
        .btn-rescan:hover { background: #138496; }
        
        .episode-selector-group {
            display: flex;
            gap: 10px;
            margin-bottom: 10px;
            width: 100%;
        }
        
        .episode-selector {
            width: 100%;
            padding: 8px 12px;
            border: 1px solid #ddd;
            border-radius: 4px;
            font-size: 0.9em;
            background: white;
            cursor: pointer;
            font-family: inherit;
        }
        
        .episode-selector:focus {
            outline: none;
            border-color: #007bff;
            box-shadow: 0 0 0 2px rgba(0,123,255,0.1);
        }
        
        .episode-selector[multiple] {
            min-height: 100px;
            padding: 8px;
        }
        
        .episode-selector[multiple] option {
            padding: 4px;
            margin-bottom: 2px;
        }
        
        .episode-selector[multiple] option:checked {
            background: #007bff;
            color: white;
        }
        .btn-skip:hover { background: #5a6268; }
        
        .btn-clear { background: #ffc107; color: #333; }
        .btn-clear:hover { background: #ffb300; }
        
        .textarea-notes {
            width: 100%;
            min-height: 60px;
            padding: 8px 12px;
            border: 1px solid #ddd;
            border-radius: 4px;
            font-family: monospace;
            font-size: 12px;
            resize: vertical;
        }
        
        .toast {
            position: fixed;
            bottom: 20px;
            right: 20px;
            padding: 15px 20px;
            background: #333;
            color: white;
            border-radius: 4px;
            opacity: 0;
            transition: opacity 0.3s;
            z-index: 1000;
        }
        
        .toast.show { opacity: 1; }
        .toast.success { background: #28a745; }
        .toast.error { background: #dc3545; }
        
        .verified-indicator {
            display: inline-block;
            width: 12px;
            height: 12px;
            background: #28a745;
            border-radius: 50%;
            margin-right: 8px;
        }
        
        .filter-bar {
            display: flex;
            gap: 10px;
            margin-bottom: 20px;
        }
        
        .filter-bar button {
            padding: 8px 16px;
            background: white;
            border: 1px solid #ddd;
            border-radius: 4px;
        }
        
        .filter-bar button.active {
            background: #667eea;
            color: white;
            border-color: #667eea;
        }
        
        @keyframes spin {
            0% { transform: rotate(0deg); }
            100% { transform: rotate(360deg); }
        }
        
        .spinner {
            display: inline-block;
            width: 16px;
            height: 16px;
            border: 2px solid #f3f3f3;
            border-top: 2px solid #667eea;
            border-radius: 50%;
            animation: spin 0.8s linear infinite;
            margin-right: 8px;
            vertical-align: middle;
        }
        
        .btn-rescan.loading {
            opacity: 0.7;
            cursor: not-allowed;
        }
        
        .btn-rescan.loading::before {
            content: '';
            display: inline-block;
            width: 14px;
            height: 14px;
            border: 2px solid rgba(255,255,255,0.3);
            border-top: 2px solid white;
            border-radius: 50%;
            animation: spin 0.8s linear infinite;
            margin-right: 6px;
            vertical-align: middle;
        }
    </style>
</head>
<body>
    <div class="container">
        <header>
            <h1>🎬 {{ show_name }} Episode Verification</h1>
            <p>Season {{ season }} - Visual Title Card Review</p>
            <div class="stats">
                <div class="stat">
                    <span>Total Files:</span>
                    <span class="stat-number" id="stat-total">{{ files|length }}</span>
                </div>
                <div class="stat">
                    <span>✓ Verified:</span>
                    <span class="stat-number" id="stat-verified">{{ verified_count }}</span>
                </div>
                <div class="stat">
                    <span>⏳ Pending:</span>
                    <span class="stat-number" id="stat-pending">{{ files|length - verified_count }}</span>
                </div>
            </div>
        </header>
        
        <div class="filter-bar">
            <button class="filter-btn active" data-filter="all">All Files</button>
            <button class="filter-btn" data-filter="verified">✓ Verified</button>
            <button class="filter-btn" data-filter="pending">⏳ Pending</button>
        </div>
        
        <div class="file-grid" id="fileGrid">
            {% for file in files %}
            <div class="file-card" data-verified="{{ file.is_verified|lower }}" data-filename="{{ file.filename }}" data-air-dates="{{ file.episode_air_dates|tojson|safe }}" data-all-verified-eps="{{ file.verified_eps|tojson|safe }}" data-episode-to-file="{{ file.episode_to_file|tojson|safe }}" data-all-titles="{{ file.episode_titles|tojson|safe }}">
                <div class="file-header">
                    <div class="file-name">
                        {% if file.is_verified %}
                        <span class="verified-indicator"></span>
                        {% endif %}
                        {{ file.short_name }}
                    </div>
                    <div class="file-status {{ 'status-verified' if file.is_verified else 'status-pending' }}">
                        {{ '✓ Verified' if file.is_verified else '⏳ Pending' }}
                    </div>
                </div>
                
                <div class="file-content">
                    <div class="episode-info">
                        <div class="info-row">
                            <div class="info-label">Filename Says:</div>
                            <div class="info-value">E{{ file.filename_episodes|join('-E') }}</div>
                        </div>
                        {% if file.episode_titles %}
                        <div class="info-row">
                            <div class="info-label">Titles:</div>
                            <div class="info-value">
                                {% for ep in file.filename_episodes %}
                                    <div>E{{ ep }}: {{ file.episode_titles.get(ep, 'Unknown') }}{% if file.episode_air_dates.get(ep) %} <span style="color: #666; font-size: 0.9em;">({{ file.episode_air_dates.get(ep) }})</span>{% endif %}</div>
                                {% endfor %}
                            </div>
                        </div>
                        {% endif %}
                        {% if file.is_verified %}
                        <div class="info-row" style="color: #28a745;">
                            <div class="info-label">✓ Verified As:</div>
                            <div class="info-value">E{{ file.verified_episodes|join('-E') }} @ {{ file.verified_timestamp }}s</div>
                        </div>
                        {% endif %}
                    </div>
                    
                    <div class="frames-container">
                        <div style="background: #e7f3ff; border-left: 4px solid #2196F3; padding: 12px; margin-bottom: 15px; border-radius: 4px; font-size: 0.9em;">
                            <strong>👆 Frame Selection:</strong> Click a frame to select it, then enter episode number(s) below. Double-click to zoom and inspect. The frame you select will be marked as the title card timestamp.
                        </div>
                        {% for frame in file.frames[:10] %}
                        <div class="frame-item" data-frame="{{ frame.name }}" data-timestamp="{{ frame.name.split('_')[1].replace('s.png', '') }}">
                            <img src="/image/{{ frame.path }}" class="frame-img" alt="{{ frame.name }}">
                            <div class="frame-label">{{ frame.name.split('_')[1].replace('s.png', '') }}s</div>
                        </div>
                        {% endfor %}
                    </div>
                    
                    {% if not file.is_verified %}
                    <div class="control-panel">
                        <div class="episode-selector-group">
                            <div style="flex: 1;">
                                <label style="display: block; font-size: 0.85em; margin-bottom: 4px; color: #666;">Select Episode(s):</label>
                                <input type="text" class="episode-search" placeholder="Type to filter episodes..." style="width: 100%; padding: 8px; margin-bottom: 5px; border: 1px solid #ddd; border-radius: 4px;" oninput="filterEpisodes(this)">
                                <select class="episode-selector" multiple onchange="selectEpisodesFromDropdown(this)" size="10">
                                    <option value="" disabled>-- Select episode(s) --</option>
                                    {% for ep in range(1, 47) %}
                                        {% if ep in file.verified_eps %}
                                        <option value="{{ ep }}" data-title="{{ file.episode_titles.get(ep, 'Unknown') }}" data-airdate="{{ file.episode_air_dates.get(ep, '?') }}" style="background: #ffebee; color: #d32f2f;">E{{ ep }}: {{ file.episode_titles.get(ep, 'Unknown') }} ({{ file.episode_air_dates.get(ep, '?') }}) ✓ VERIFIED</option>
                                        {% else %}
                                        <option value="{{ ep }}" data-title="{{ file.episode_titles.get(ep, 'Unknown') }}" data-airdate="{{ file.episode_air_dates.get(ep, '?') }}">E{{ ep }}: {{ file.episode_titles.get(ep, 'Unknown') }} ({{ file.episode_air_dates.get(ep, '?') }})</option>
                                        {% endif %}
                                    {% endfor %}
                                </select>
                            </div>
                            <div style="flex: 1; margin-left: 10px;">
                                <label style="display: block; font-size: 0.85em; margin-bottom: 4px; color: #666;">Selected episodes:</label>
                                <input type="text" class="episode-input" placeholder="e.g., 20 or 11-12" value="E{{ file.filename_episodes|join('-E') }}" onchange="validateEpisodeInput(this)" oninput="validateEpisodeInput(this)">
                                <div class="episode-validation" style="font-size: 0.8em; margin-top: 3px; min-height: 18px;"></div>
                            </div>
                        </div>
                        <button class="btn-save" onclick="saveVerification(this)">Save</button>
                        <button class="btn-rescan" onclick="rescanFrames(this)">Rescan Frames</button>
                        <button class="btn-skip" onclick="skipFile(this)">Skip</button>
                    </div>
                    <textarea class="textarea-notes" placeholder="Notes (optional)"></textarea>
                    {% else %}
                    <div class="control-panel">
                        <button class="btn-skip" onclick="deleteVerification(this)" style="background: #dc3545; color: white;">Delete Verification</button>
                        <button class="btn-rescan" onclick="rescanFrames(this)">Rescan Frames</button>
                    </div>
                    {% endif %}
                </div>
            </div>
            {% endfor %}
        </div>
        
        <!-- Post-Verification Management -->
        <div style="margin-top: 40px; padding: 20px; background: #f8f9fa; border-radius: 8px; display: none;" id="postVerificationPanel">
            <h2>✅ All Files Verified!</h2>
            <p style="color: #666; margin-bottom: 20px;">Time to finalize and organize your files.</p>
            
            <div style="display: grid; grid-template-columns: 1fr; gap: 15px; margin-bottom: 30px;">
                <div style="padding: 20px; background: linear-gradient(135deg, #667eea 0%, #764ba2 100%); border-radius: 6px; border: 2px solid #667eea;">
                    <h3 style="margin-top: 0; color: white;">🚀 Finalize & Clean Up</h3>
                    <p style="color: rgba(255,255,255,0.9);">Rename verified files with proper titles and delete any skipped/duplicate files.</p>
                    <button onclick="finalizeAll()" style="background: white; color: #667eea; font-weight: bold; padding: 12px 24px; border: none; border-radius: 4px; cursor: pointer; width: 100%; font-size: 1em;">
                        ✨ Finalize Everything
                    </button>
                </div>
            </div>
            
            <div style="display: grid; grid-template-columns: 1fr 1fr; gap: 20px;">
                <div style="padding: 15px; background: white; border-radius: 6px; border: 1px solid #ddd;">
                    <h3 style="margin-top: 0;">🗑️ Delete Skipped Files</h3>
                    <p style="font-size: 0.9em; color: #666;">Permanently delete files marked as skipped (never verified).</p>
                    <button onclick="deleteSkippedFiles()" class="btn-skip" style="width: 100%;">Delete Skipped</button>
                    <div id="skippedCount" style="font-size: 0.85em; color: #999; margin-top: 10px;"></div>
                </div>
                
                <div style="padding: 15px; background: white; border-radius: 6px; border: 1px solid #ddd;">
                    <h3 style="margin-top: 0;">📝 Batch Rename Files</h3>
                    <p style="font-size: 0.9em; color: #666;">Rename all verified files to: S##E##-E## - Title.mkv</p>
                    <button onclick="batchRenameVerified()" class="btn-save" style="width: 100%;">Rename Verified</button>
                    <div id="verifiedCount" style="font-size: 0.85em; color: #999; margin-top: 10px;"></div>
                </div>
            </div>
        </div>
    </div>
    
    <div class="toast" id="toast"></div>
    
    <script>
        let selectedFrame = {};
        
        // Frame selection and zoom
        document.querySelectorAll('.frame-item').forEach(item => {
            item.addEventListener('click', function() {
                const card = this.closest('.file-card');
                const filename = card.dataset.filename;
                
                // Toggle selection
                if (selectedFrame[filename]) {
                    document.querySelector(`[data-filename="${filename}"] .frame-item.selected`).classList.remove('selected');
                    if (selectedFrame[filename] === this.dataset.frame) {
                        delete selectedFrame[filename];
                        return;
                    }
                }
                
                this.classList.add('selected');
                selectedFrame[filename] = {
                    frame: this.dataset.frame,
                    timestamp: parseFloat(this.dataset.timestamp)
                };
                
                // Update input with selected frame time
                card.querySelector('.episode-input').placeholder = `Episode(s): selected @ ${this.dataset.timestamp}s`;
            });
            
            // Double-click to zoom
            item.addEventListener('dblclick', function(e) {
                e.stopPropagation();
                this.classList.toggle('zoomed');
            });
        });
        
        // Click outside zoomed image to close
        document.addEventListener('click', function() {
            document.querySelectorAll('.frame-item.zoomed').forEach(item => {
                item.classList.remove('zoomed');
            });
        });
        
        function saveVerification(button) {
            console.log('[SAVE] Button clicked!');
            const card = button.closest('.file-card');
            const filename = card.dataset.filename;
            const episodesInput = card.querySelector('.episode-input').value.trim();
            const notes = card.querySelector('.textarea-notes').value.trim();
            const timestamp = selectedFrame[filename]?.timestamp || 0;
            
            console.log(`[SAVE] Starting save for ${filename}, episodes: ${episodesInput}`);
            
            if (!episodesInput) {
                showToast('Please enter episode number(s)', 'error');
                return;
            }
            
            // Parse episode input (e.g., "20" or "11-12" or "E11-E12" or "E1-E2")
            let episodes = [];
            // Remove all 'E' prefixes and split on dash
            const cleaned = episodesInput.replace(/E/g, '');
            console.log(`[SAVE] Cleaned input: "${cleaned}"`);
            if (cleaned.includes('-')) {
                episodes = cleaned.split('-').map(e => parseInt(e.trim()));
            } else {
                episodes = [parseInt(cleaned)];
            }
            
            console.log(`[SAVE] Parsed episodes: [${episodes}]`);
            
            if (episodes.some(isNaN) || episodes.length === 0) {
                showToast('Invalid episode format', 'error');
                console.error(`[SAVE] Invalid episode format detected`);
                return;
            }
            
            // Extract title from filename to help detect mislabels
            const filenameMatch = filename.match(/S\d+E\d+(?:-E\d+)?\s*-\s*(.+?)\s*\[/);
            const filenameTitle = filenameMatch ? filenameMatch[1].trim() : '';
            console.log(`[SAVE] Extracted filename title: "${filenameTitle}"`);
            
            // Check air date conflicts - if single episode but has matching air dates with another episode
            if (episodes.length === 1) {
                const ep = episodes[0];
                const airDatesStr = card.dataset.airDates || '{}';
                console.log(`[SAVE] Air dates data: ${airDatesStr}`);
                const airDates = JSON.parse(airDatesStr);
                const selectedAirDate = airDates[ep];
                
                console.log(`[SAVE] Episode ${ep} air date: ${selectedAirDate}`);
                
                if (selectedAirDate) {
                    // Check if any other episode has the same air date
                    for (const [epNum, date] of Object.entries(airDates)) {
                        if (epNum !== ep.toString() && date === selectedAirDate && date) {
                            const warning = `⚠️ Episode ${ep} and ${epNum} share air date (${selectedAirDate}). This might be a multi-episode file!`;
                            showToast(warning, 'warning');
                            console.warn(`[SAVE] ${warning}`);
                            // Don't return - let user override if they want
                        }
                    }
                }
            }
            
            // Check for duplicate episodes - if these episodes are already verified in other files
            const allVerifiedEps = JSON.parse(card.dataset.allVerifiedEps || '[]');
            const episodeToFile = JSON.parse(card.dataset.episodeToFile || '{}');
            const duplicates = episodes.filter(ep => allVerifiedEps.includes(ep));
            if (duplicates.length > 0) {
                // Find which files have these episodes
                const filesWithDuplicates = new Set();
                for (const ep of duplicates) {
                    const file = episodeToFile[ep];
                    if (file) filesWithDuplicates.add(file);
                }
                const fileList = Array.from(filesWithDuplicates).map(f => f.substring(0, 50) + (f.length > 50 ? '...' : '')).join('\n  • ');
                const warning = `⚠️ Episodes ${duplicates.join(', ')} already verified in:\n  • ${fileList}\n\nFix the other file(s) first or remove them.`;
                showToast(warning, 'error');
                console.error(`[SAVE] ${warning}`);
                return; // Block the save
            }
            
            // Send to server
            console.log(`[SAVE] Sending POST to /verify with: filename=${filename}, episodes=[${episodes}], timestamp=${timestamp}`);
            fetch('/verify', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ filename, episodes, timestamp, notes })
            })
            .then(r => {
                console.log(`[SAVE] Response status: ${r.status}`);
                return r.json();
            })
            .then(data => {
                console.log(`[SAVE] Response data: ${JSON.stringify(data)}`);
                if (data.success) {
                    showToast(`✓ Verified as E${episodes.join('-E')}`, 'success');
                    card.dataset.verified = 'true';
                    card.querySelector('.file-status').textContent = '✓ Verified';
                    card.querySelector('.file-status').className = 'file-status status-verified';
                    updateStats();
                    setTimeout(() => location.reload(), 1500);
                } else {
                    showToast('Error: ' + data.error, 'error');
                }
            })
            .catch(err => {
                console.error(`[SAVE] Fetch error: ${err}`);
                showToast('Network error: ' + err.message, 'error');
            });
        }
        
        function skipFile(button) {
            const card = button.closest('.file-card');
            card.style.opacity = '0.5';
            card.style.pointerEvents = 'none';
            showToast('⏭️ Skipped', 'success');
        }
        
        function deleteVerification(button) {
            const card = button.closest('.file-card');
            const filename = card.dataset.filename;
            
            if (!confirm(`Delete verification for this file?\n\n${filename}\n\nThis will allow you to re-verify with correct episode numbers.`)) {
                return;
            }
            
            button.disabled = true;
            button.textContent = 'Deleting...';
            
            fetch('/delete_verification', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ filename })
            })
            .then(r => r.json())
            .then(data => {
                if (data.success) {
                    showToast('✓ Verification deleted - reloading...', 'success');
                    setTimeout(() => location.reload(), 1000);
                } else {
                    showToast('Error: ' + data.error, 'error');
                    button.disabled = false;
                    button.textContent = 'Delete Verification';
                }
            })
            .catch(err => {
                showToast('Network error: ' + err.message, 'error');
                button.disabled = false;
                button.textContent = 'Delete Verification';
            });
        }
        
        function selectEpisodesFromDropdown(select) {
            const card = select.closest('.file-card');
            const selected = Array.from(select.selectedOptions).map(opt => opt.value).filter(v => v);
            
            if (selected.length > 0) {
                // Format as: 20 or 11-12
                const input = card.querySelector('.episode-input');
                input.value = 'E' + selected.join('-E');
                // Keep selections visible - don't reset dropdown
                validateEpisodeInput(input);
            }
        }
        
        function filterEpisodes(searchInput) {
            const card = searchInput.closest('.file-card');
            const select = card.querySelector('.episode-selector');
            const filter = searchInput.value.toLowerCase();
            
            if (!filter) {
                // Show all if no filter
                Array.from(select.options).forEach(option => {
                    option.style.display = '';
                });
                return;
            }
            
            // First pass: find episodes that match the search
            const matchingEpisodes = [];
            const matchingAirDates = new Set();
            
            Array.from(select.options).forEach(option => {
                if (option.value === '') return;
                
                const title = option.dataset.title.toLowerCase();
                const epNum = option.value;
                const airDate = option.dataset.airdate;
                
                if (title.includes(filter) || epNum.includes(filter) || airDate.includes(filter)) {
                    matchingEpisodes.push(option);
                    if (airDate && airDate !== '?') {
                        matchingAirDates.add(airDate);
                    }
                }
            });
            
            // Second pass: show matching episodes AND episodes with same air dates
            Array.from(select.options).forEach(option => {
                if (option.value === '') {
                    option.style.display = 'none';
                    return;
                }
                
                const airDate = option.dataset.airdate;
                const isDirectMatch = matchingEpisodes.includes(option);
                const hasSameAirDate = airDate && matchingAirDates.has(airDate);
                
                option.style.display = (isDirectMatch || hasSameAirDate) ? '' : 'none';
                
                // Highlight direct matches vs air date matches
                if (isDirectMatch) {
                    option.style.fontWeight = 'bold';
                } else if (hasSameAirDate) {
                    option.style.fontWeight = 'normal';
                    option.style.fontStyle = 'italic';
                }
            });
        }
        
        function validateEpisodeInput(input) {
            const card = input.closest('.file-card');
            const validationDiv = card.querySelector('.episode-validation');
            const episodesInput = input.value.trim();
            const filename = card.dataset.filename;
            
            if (!episodesInput) {
                validationDiv.textContent = '';
                validationDiv.style.color = '#999';
                return;
            }
            
            // Parse episode input
            let episodes = [];
            const cleaned = episodesInput.replace(/E/g, '');
            if (cleaned.includes('-')) {
                episodes = cleaned.split('-').map(e => parseInt(e.trim()));
            } else {
                episodes = [parseInt(cleaned)];
            }
            
            // Check validity
            const invalid = episodes.filter(ep => isNaN(ep) || ep < 1 || ep > 46);
            const valid = episodes.filter(ep => !isNaN(ep) && ep >= 1 && ep <= 46);
            
            let msg = '';
            let color = '#999';
            
            if (invalid.length > 0) {
                msg = `⚠️ Invalid episodes: ${invalid.join(', ')} (must be 1-46)`;
                color = '#d9534f';
            } else if (valid.length > 0) {
                // Extract title from filename
                const filenameMatch = filename.match(/S\d+E(\d+)(?:-E(\d+))?\s*-\s*(.+?)\s*\[/);
                const fileEpisodes = filenameMatch ? [parseInt(filenameMatch[1]), filenameMatch[2] ? parseInt(filenameMatch[2]) : null].filter(Boolean) : [];
                const filenameTitle = filenameMatch ? filenameMatch[3].trim() : '';
                
                // Get TVDB titles for selected episodes
                const allTitles = JSON.parse(card.dataset.allTitles || '{}') || {};
                const selectedTitles = valid.map(ep => allTitles[ep] || `E${ep}`).join(' + ');
                
                // Check if any selected episodes are already verified
                const allVerifiedEps = JSON.parse(card.dataset.allVerifiedEps || '[]');
                const episodeToFile = JSON.parse(card.dataset.episodeToFile || '{}');
                const alreadyVerified = valid.filter(ep => allVerifiedEps.includes(ep));
                
                if (alreadyVerified.length > 0) {
                    // Show which files have these episodes
                    const files = alreadyVerified.map(ep => {
                        const file = episodeToFile[ep];
                        return `E${ep} in: ${file ? file.substring(0, 40) + '...' : 'unknown'}`;
                    }).join('<br>');
                    msg = `⚠️ ALREADY VERIFIED:<br>${files}<br>Delete those verifications first!`;
                    color = '#d32f2f'; // Red
                } else if (filenameTitle && fileEpisodes.length > 0 && JSON.stringify(fileEpisodes.sort()) !== JSON.stringify(valid.sort())) {
                    msg = `⚠️ Filename says E${fileEpisodes.join('-E')} but you selected E${valid.join('-E')}<br>✓ Selected: ${selectedTitles}`;
                    color = '#ff9800'; // Orange warning
                } else {
                    msg = `✓ Valid: E${valid.join('-E')}`;
                    color = '#5cb85c';
                }
            }
            
            validationDiv.innerHTML = msg.replace(/\n/g, '<br>');
            validationDiv.style.color = color;
        }
        
        function rescanFrames(button) {
            console.log('[RESCAN] Button clicked');
            const card = button.closest('.file-card');
            const filename = card.dataset.filename;
            console.log('[RESCAN] Filename:', filename);
            button.disabled = true;
            button.classList.add('loading');
            button.textContent = 'Rescanning...';
            
            // Abort controller for timeout
            const controller = new AbortController();
            const timeoutId = setTimeout(() => controller.abort(), 120000); // 2 minute timeout
            
            console.log('[RESCAN] Sending POST to /rescan');
            fetch('/rescan', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ filename }),
                signal: controller.signal
            })
            .then(r => {
                clearTimeout(timeoutId);
                console.log('[RESCAN] Response status:', r.status);
                return r.json();
            })
            .then(data => {
                console.log('[RESCAN] Response data:', data);
                if (data.success) {
                    showToast(`✓ Rescanned: ${data.new_frames} frames found`, 'success');
                    setTimeout(() => location.reload(), 1500);
                } else {
                    showToast('Error: ' + data.error, 'error');
                    button.disabled = false;
                    button.classList.remove('loading');
                    button.textContent = 'Rescan Frames';
                }
            })
            .catch(err => {
                clearTimeout(timeoutId);
                if (err.name === 'AbortError') {
                    console.error('[RESCAN] Timeout after 2 minutes');
                    showToast('Rescan took too long (>2 min). Try again or check server logs.', 'error');
                } else {
                    console.error('[RESCAN] Error:', err);
                    showToast('Error: ' + err, 'error');
                }
                button.disabled = false;
                button.classList.remove('loading');
                button.textContent = 'Rescan Frames';
            });
        }
        
        function showToast(message, type = 'success') {
            const toast = document.getElementById('toast');
            toast.textContent = message;
            toast.className = `toast show ${type}`;
            setTimeout(() => toast.classList.remove('show'), 3000);
        }
        
        function updateStats() {
            const verified = document.querySelectorAll('[data-verified="true"]').length;
            const total = document.querySelectorAll('.file-card').length;
            document.getElementById('stat-verified').textContent = verified;
            document.getElementById('stat-pending').textContent = total - verified;
        }
        
        // Detect title mismatches on page load
        function detectMismatches() {
            document.querySelectorAll('.file-card').forEach(card => {
                const filename = card.dataset.filename;
                const allTitles = JSON.parse(card.dataset.allTitles || '{}');
                const episodeToFile = JSON.parse(card.dataset.episodeToFile || '{}');
                
                // Extract episodes from filename
                const filenameMatch = filename.match(/S\d+E(\d+)(?:-E(\d+))?/);
                if (!filenameMatch) return;
                
                const fileEp1 = parseInt(filenameMatch[1]);
                const fileEp2 = filenameMatch[2] ? parseInt(filenameMatch[2]) : null;
                
                // Extract title from filename
                const titleMatch = filename.match(/S\d+E\d+(?:-E\d+)?\s*-\s*(.+?)\s*\[/);
                if (!titleMatch) return;
                
                const filenameTitle = titleMatch[1].trim().toLowerCase();
                const tvdbTitle = allTitles[fileEp1] ? allTitles[fileEp1].toLowerCase() : '';
                
                // Check if filename title doesn't match TVDB title
                if (filenameTitle && tvdbTitle && !filenameTitle.includes(tvdbTitle.substring(0, 20)) && !tvdbTitle.includes(filenameTitle.substring(0, 20))) {
                    // Find which episode has this title
                    let correctEp = null;
                    for (const [ep, title] of Object.entries(allTitles)) {
                        if (title.toLowerCase().includes(filenameTitle.substring(0, 30)) || filenameTitle.includes(title.toLowerCase().substring(0, 30))) {
                            correctEp = ep;
                            break;
                        }
                    }
                    
                    if (correctEp && correctEp != fileEp1) {
                        const conflictFile = episodeToFile[correctEp];
                        const warning = document.createElement('div');
                        warning.style.cssText = 'background: #ff9800; color: white; padding: 10px; margin: 10px 0; border-radius: 4px; font-weight: bold;';
                        if (conflictFile) {
                            warning.innerHTML = '\u26a0\ufe0f MISMATCH DETECTED!<br>Filename says E' + fileEp1 + ' but content is E' + correctEp + '<br>E' + correctEp + ' already verified in: ' + conflictFile.substring(0, 50) + '...';
                        } else {
                            warning.innerHTML = '\u26a0\ufe0f MISMATCH DETECTED!<br>Filename says E' + fileEp1 + ' but content appears to be E' + correctEp + '<br>Consider deleting this verification and re-verifying as E' + correctEp;
                        }
                        const episodeInfo = card.querySelector('.episode-info');
                        if (episodeInfo) {
                            episodeInfo.parentNode.insertBefore(warning, episodeInfo);
                        }
                    }
                }
            });
        }
        
        // Run mismatch detection after page loads
        setTimeout(detectMismatches, 500);
        
        // Filter buttons
        document.querySelectorAll('.filter-btn').forEach(btn => {
            btn.addEventListener('click', function() {
                console.log('[FILTER] Clicked:', this.dataset.filter);
                document.querySelectorAll('.filter-btn').forEach(b => b.classList.remove('active'));
                this.classList.add('active');
                
                const filter = this.dataset.filter;
                document.querySelectorAll('.file-card').forEach(card => {
                    if (filter === 'all') {
                        card.style.display = '';
                    } else if (filter === 'verified') {
                        card.style.display = card.dataset.verified === 'true' ? '' : 'none';
                    } else if (filter === 'pending') {
                        card.style.display = card.dataset.verified === 'false' ? '' : 'none';
                    }
                });
            });
        });
        
        // Update post-verification panel visibility
        function updatePostVerificationPanel() {
            const verified = document.querySelectorAll('[data-verified="true"]').length;
            const total = document.querySelectorAll('.file-card').length;
            const skipped = total - verified;
            
            const panel = document.getElementById('postVerificationPanel');
            if (verified === total) {
                // All verified, show post-verification panel
                panel.style.display = 'block';
                document.getElementById('skippedCount').textContent = '0 skipped files';
                document.getElementById('verifiedCount').textContent = verified + ' files ready to rename';
            } else {
                panel.style.display = 'none';
            }
        }
        
        function deleteSkippedFiles() {
            const skipped = Array.from(document.querySelectorAll('[data-verified="false"]'))
                .map(card => card.dataset.filename);
            
            if (skipped.length === 0) {
                showToast('No skipped files to delete', 'success');
                return;
            }
            
            if (!confirm(`Delete ${skipped.length} skipped file(s)? This cannot be undone!`)) {
                return;
            }
            
            fetch('/delete_skipped', { method: 'POST' })
                .then(r => r.json())
                .then(data => {
                    if (data.success) {
                        showToast(`✓ Deleted ${data.count} skipped file(s)`, 'success');
                        setTimeout(() => location.reload(), 1500);
                    } else {
                        showToast('Error: ' + data.error, 'error');
                    }
                })
                .catch(err => {
                    console.error('Delete error:', err);
                    showToast('Error: ' + err, 'error');
                });
        }
        
        function batchRenameVerified() {
            const verified = document.querySelectorAll('[data-verified="true"]').length;
            
            if (verified === 0) {
                showToast('No verified files to rename', 'error');
                return;
            }
            
            if (!confirm(`Rename ${verified} file(s) to proper format? This will use TVDB episode titles.`)) {
                return;
            }
            
            fetch('/batch_rename', { method: 'POST' })
                .then(r => r.json())
                .then(data => {
                    if (data.success) {
                        const message = `✓ Renamed ${data.count} file(s)`;
                        showToast(message, 'success');
                        
                        // Show renamed files
                        if (data.renamed.length > 0) {
                            console.log('Renamed files:', data.renamed);
                        }
                        
                        setTimeout(() => location.reload(), 1500);
                    } else {
                        showToast('Error: ' + data.error, 'error');
                        if (data.traceback) console.error(data.traceback);
                    }
                })
                .catch(err => {
                    console.error('Rename error:', err);
                    showToast('Error: ' + err, 'error');
                });
        }
        
        function finalizeAll() {
            const verified = document.querySelectorAll('[data-verified="true"]').length;
            const total = document.querySelectorAll('.file-card').length;
            const skipped = total - verified;
            
            const summary = `
✓ Verified: ${verified}/${total} files
🗑️ Skipped: ${skipped} files to delete

This will:
1. Rename verified files with proper titles
2. Delete all skipped/unverified files

Continue?`;
            
            if (!confirm(summary)) {
                return;
            }
            
            showToast('⏳ Finalizing...', 'success');
            
            // First rename, then delete
            Promise.all([
                fetch('/batch_rename', { method: 'POST' }),
                fetch('/delete_skipped', { method: 'POST' })
            ])
            .then(responses => Promise.all(responses.map(r => r.json())))
            .then(results => {
                const renameResult = results[0];
                const deleteResult = results[1];
                
                const summary = `✅ Finalized!
• Renamed: ${renameResult.count} file(s)
• Deleted: ${deleteResult.count} file(s)`;
                
                showToast(summary, 'success');
                console.log('Finalize results:', { renameResult, deleteResult });
                
                setTimeout(() => location.reload(), 2000);
            })
            .catch(err => {
                console.error('Finalize error:', err);
                showToast('Error during finalization: ' + err, 'error');
            });
        }

        
        // Check post-verification panel on load and when files change
        updatePostVerificationPanel();
        // Recheck when a file is saved/deleted
        const observer = new MutationObserver(updatePostVerificationPanel);
        observer.observe(document.getElementById('fileGrid'), { childList: true, attributes: true, subtree: true });
    </script>
</body>
</html>
'''

@app.route('/')
def index():
    """Main page."""
    load_data()
    files = get_all_files()
    verified_count = len([f for f in files if f['is_verified']])
    
    return render_template_string(HTML_TEMPLATE, 
                                 show_name=SHOW_NAME,
                                 season=SEASON, 
                                 files=files,
                                 verified_count=verified_count)

@app.route('/image/<path:filename>')
def serve_image(filename):
    """Serve image files."""
    try:
        # filename will be like: title_card_candidates/Paw Patrol.../frame_0011.0s.png
        # We need to strip the title_card_candidates/ prefix if present
        if filename.startswith('title_card_candidates/'):
            filename = filename[len('title_card_candidates/'):]
        return send_from_directory('title_card_candidates', filename)
    except Exception as e:
        return str(e), 404

@app.route('/verify', methods=['POST'])
def verify():
    """Save verification."""
    try:
        data = request.json
        filename = data['filename']
        episodes = data['episodes']
        timestamp = data.get('timestamp', 0)
        notes = data.get('notes', '')
        
        verified_episodes[filename] = {
            'episodes': episodes,
            'title_card_timestamp': timestamp,
            'notes': notes
        }
        
        # Save to file
        with open(VERIFICATION_FILE, 'w') as f:
            json.dump(verified_episodes, f, indent=2)
        
        return jsonify({'success': True})
    
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)})


@app.route('/delete_verification', methods=['POST'])
def delete_verification():
    """Delete verification for a file."""
    try:
        data = request.json
        filename = data['filename']
        
        if filename in verified_episodes:
            del verified_episodes[filename]
            
            # Save to file
            with open(VERIFICATION_FILE, 'w') as f:
                json.dump(verified_episodes, f, indent=2)
            
            return jsonify({'success': True})
        else:
            return jsonify({'success': False, 'error': 'File not found in verified episodes'})
    
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)})


@app.route('/delete_skipped', methods=['POST'])
def delete_skipped():
    """Delete all skipped (unverified) files."""
    try:
        deleted = []
        failed = []
        
        # Get list of verified filenames
        verified_filenames = set(verified_episodes.keys())
        
        # Find and delete unverified files
        for video_file in sorted(SEASON_DIR.glob('*')):
            if video_file.is_file() and video_file.suffix in ['.mkv', '.mp4', '.avi']:
                if video_file.name not in verified_filenames:
                    try:
                        video_file.unlink()
                        deleted.append(video_file.name)
                    except Exception as e:
                        failed.append({'file': video_file.name, 'error': str(e)})
        
        return jsonify({
            'success': True,
            'deleted': deleted,
            'failed': failed,
            'count': len(deleted)
        })
    
    except Exception as e:
        import traceback
        return jsonify({'success': False, 'error': str(e), 'traceback': traceback.format_exc()})


@app.route('/batch_rename', methods=['POST'])
def batch_rename():
    """Rename all verified files to proper format."""
    try:
        import re
        renamed = []
        failed = []
        
        for filename, verif_data in verified_episodes.items():
            video_file = SEASON_DIR / filename
            if not video_file.exists():
                continue
            
            episodes = verif_data.get('episodes', [])
            if not episodes:
                continue
            
            # Get episode info from TVDB
            ep_titles = []
            for ep_num in episodes:
                for ep in episode_database:
                    if ep.get('episode') == ep_num:
                        ep_titles.append(ep.get('title', f'Episode {ep_num}'))
                        break
            
            # Build new filename
            if len(episodes) == 1:
                ep_range = f"E{episodes[0]:02d}"
            else:
                ep_range = f"E{episodes[0]:02d}-E{episodes[-1]:02d}"
            
            title_part = ' and '.join(ep_titles) if ep_titles else 'Unknown'
            # Clean title of problematic characters
            title_part = re.sub(r'[<>:"/\\|?*]', '', title_part)
            title_part = title_part[:60]  # Limit length
            
            new_filename = f"Paw Patrol (2013) - S09{ep_range} - {title_part}{video_file.suffix}"
            
            if new_filename == filename:
                continue  # Already correct format
            
            try:
                new_path = SEASON_DIR / new_filename
                video_file.rename(new_path)
                
                # Update verified_episodes dict with new filename
                verified_episodes[new_filename] = verified_episodes.pop(filename)
                renamed.append({'old': filename, 'new': new_filename})
            except Exception as e:
                failed.append({'file': filename, 'error': str(e)})
        
        # Save updated verification data
        if renamed:
            with open(VERIFICATION_FILE, 'w') as f:
                json.dump(verified_episodes, f, indent=2)
        
        return jsonify({
            'success': True,
            'renamed': renamed,
            'failed': failed,
            'count': len(renamed)
        })
    
    except Exception as e:
        import traceback
        return jsonify({'success': False, 'error': str(e), 'traceback': traceback.format_exc()})


def detect_multi_episode(filename, video_file):
    """
    Detect if file contains multiple episodes using hierarchical approach:
    1. Filename parsing (e.g., S09E13-E14 format)
    2. Air date lookup from TVDB
    3. OCR scan fallback
    """
    import re
    
    # Strategy 1: Parse filename for episode range (e.g., E13-E14)
    match = re.search(r'E(\d+)-E(\d+)', filename, re.IGNORECASE)
    if match:
        ep_start = int(match.group(1))
        ep_end = int(match.group(2))
        if ep_end > ep_start:
            return True, "filename"
    
    # Strategy 2: Check TVDB air date for multi-episode info
    try:
        season_match = re.search(r'S(\d+)E(\d+)', filename, re.IGNORECASE)
        if season_match and episode_database:
            season_num = int(season_match.group(1))
            ep_num = int(season_match.group(2))
            
            # Look up episode in database to see if it's multi-episode
            for ep in episode_database:
                if ep.get('season') == season_num and ep.get('episode') == ep_num:
                    # Check if episode title or description indicates multi-episode
                    title = ep.get('title', '').lower()
                    if 'and' in title or '&' in title or ep.get('episode_count', 1) > 1:
                        return True, "tvdb_airdate"
                    break
    except:
        pass
    
    # Strategy 3: OCR scan fallback - search for second title card
    try:
        from visual_title_finder import TitleCardFinder
        finder = TitleCardFinder()
        
        # Quick scan for second title card around midpoint + 52 min mark
        import subprocess
        cmd = ['ffprobe', '-v', 'quiet', '-print_format', 'json', '-show_format', str(video_file)]
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=10)
        duration = float(json.loads(result.stdout)['format']['duration'])
        
        # Estimate second episode start around midpoint
        if duration > 60:
            ep2_start = int(duration / 2 - 60)
            ep2_check_time = ep2_start + 20  # Check ~20 seconds into second episode
            
            # Extract and score frame at this point
            frame_path = finder.extract_frame(video_file, ep2_check_time)
            if frame_path:
                score = finder.score_frame_as_title_card(frame_path)
                if score > 0.5:  # High confidence threshold
                    return True, "ocr_scan"
    except:
        pass
    
    return False, None


@app.route('/rescan', methods=['POST'])
def rescan():
    """Rescan a file for more frame candidates, checking multiple episodes if present."""
    try:
        from visual_title_finder import TitleCardFinder
        import threading
        import time
        
        data = request.json
        filename = data['filename']
        
        # Find the video file
        video_file = SEASON_DIR / filename
        if not video_file.exists():
            return jsonify({'success': False, 'error': 'Video file not found'})
        
        # Clear existing verification to update timestamp
        if filename in verified_episodes:
            del verified_episodes[filename]
        
        # Detect if multi-episode using hierarchical approach
        is_multi_episode, detection_method = detect_multi_episode(filename, video_file)
        
        # Extract candidates (will overwrite existing ones)
        finder = TitleCardFinder()
        output_dir = CANDIDATES_DIR / video_file.stem
        
        # Check if this is a rescan by looking for existing frames
        existing_frames = list(output_dir.glob('frame_*.png')) if output_dir.exists() else []
        rescan_count = len(existing_frames) // 6  # Each rescan generates ~6 frames
        rescan_offset = rescan_count * 0.5  # Offset by 0.5s per rescan
        
        # For multi-episode, search both episode windows
        if is_multi_episode:
            candidates = finder.find_title_card_candidates_multi_episode(video_file, output_dir, max_candidates=6, rescan_offset=rescan_offset)
        else:
            candidates = finder.find_title_card_candidates(video_file, output_dir, max_candidates=6, rescan_offset=rescan_offset)
        
        # Save cleared verification data (timestamp will be updated when re-verified)
        with open(VERIFICATION_FILE, 'w') as f:
            json.dump(verified_episodes, f, indent=2)
        
        # Generate helpful message
        ep_info = f"(E{list(range(1, 47))[-1]} range)" if not is_multi_episode else f"(multi-episode detected via {detection_method})"
        
        return jsonify({
            'success': True,
            'new_frames': len(candidates),
            'message': f'✓ Extracted {len(candidates)} candidate frames. Click to select, double-click to zoom.'
        })
    
    except Exception as e:
        import traceback
        return jsonify({'success': False, 'error': str(e), 'traceback': traceback.format_exc()})



if __name__ == '__main__':
    print(f"\n{'='*60}")
    print(f"Title Card Verification Interface")
    print(f"{'='*60}\n")
    print(f"Show: {SHOW_NAME}")
    print(f"Season: {SEASON}")
    print(f"Source: {SEASON_DIR}")
    print(f"Config: config.json (or use env vars)")
    print(f"Open browser to: http://localhost:5000\n")
    
    app.run(debug=False, port=5000, host='127.0.0.1')
