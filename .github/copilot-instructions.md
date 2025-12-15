# Frame Viewer - AI Coding Instructions

## Project Purpose
Visual episode validation tool for TV shows. Users select video files, extract frames at timestamps, visually confirm episode content, then rename files based on verified episodes. Integrates with TVDB for metadata and Sonarr for library management.

**Critical Context:** This project REPLACED an old OCR-based detection system (archived in `archive_old_ocr_system/`). User explicitly moved to pure visual validation. Never suggest OCR approaches.

## Architecture Overview

### Core Components
- **`frame_viewer_server.py`** (704 lines) - Flask backend on port 5000
  - Frame extraction via ffmpeg subprocess calls
  - TVDB API integration for episode metadata
  - Sonarr API integration for library status
  - File renaming endpoint
  - All API endpoints return JSON

- **`templates/frame_viewer.html`** (1250 lines) - Single-page frontend
  - Split-pane: left 450px (controls), right flex (frame preview)
  - Collapsible tree file browser with natural sorting
  - Episode list with status indicators (missing/matched/multi-episode)
  - Modal zoom with brightness/contrast/saturation controls
  - No external JS frameworks - vanilla JavaScript

- **`tvdb_loader.py`** - TVDB API v4 client
  - Bearer token authentication
  - Series search, season/episode fetching
  - Imported by server, credentials hardcoded

### Data Flow
1. User selects video file → `/api/list_videos` (tree structure)
2. Search show → `/api/sonarr/search` or `/api/search_series`
3. Select season → `/api/unified/series/<tvdb_id>/season/<num>` (combines TVDB + Sonarr data)
4. Extract frames → `/api/extract_frames` (ffmpeg with base64 encoding)
5. Select episodes → Client-side state management
6. Rename → `/api/rename_file` (Python `os.rename`)

## Critical Patterns

### Frame Extraction (frame_viewer_server.py:55-105)
```python
# FFmpeg subprocess call - DO NOT change without testing
subprocess.run([
    'ffmpeg', '-ss', str(timestamp), '-i', video_path,
    '-vf', 'scale=320:-1', '-frames:v', '1',
    '-f', 'image2pipe', '-vcodec', 'mjpeg', '-'
], stdout=subprocess.PIPE, stderr=subprocess.DEVNULL, check=True)
```
- Uses pipe to stdout (no temp files)
- Scale to 320px width for performance
- Returns base64-encoded JPEG images

### Episode Status Indicators (templates/frame_viewer.html)
- **Red badge:** Missing from Sonarr (target for download)
- **Green badge:** Already in Sonarr (has file)
- **Orange border:** Multi-episode candidate (aired same day, no file)
- Status determined by `/api/unified` endpoint combining TVDB + Sonarr data

### Multi-Episode Timestamps
For 22-minute episodes (standard 30-min slots):
- E1: 10s (skip intro)
- E2: 660s (11:00 - first episode + intro)
- E3: 1320s (22:00)
- E4: 1980s (33:00)

Formula: `10s + (episode_index * 660s)` - Adjust for different show lengths.

### Natural Sorting (frame_viewer_server.py:154-160)
Custom sort for "Season 1", "Season 2", ... "Season 10" order. Do NOT use default string sort or you'll get "Season 1", "Season 10", "Season 2".

## Environment & Configuration

### API Credentials
**IMPORTANT:** Credentials are HARDCODED in `frame_viewer_server.py` for user's environment:
```python
TVDB_API_KEY = "585432a6-f441-4db3-a106-2d5a05fa95d7"
SONARR_URL = "http://10.0.1.90:8993"
SONARR_API_KEY = "d6903236b2c24107b60c5f9423fc30e7"
```

Environment variables (`.env`) are supported but fallback to hardcoded values. For production use, encourage environment variables via `.env` file.

### Python Environment
- Use `venv/` (NOT `.venv`)
- Activate: `source venv/bin/activate`
- Python 3.12.3 required
- Dependencies: Flask 3.1.2, flask-cors 6.0.2, requests

### Required System Dependencies
- **ffmpeg/ffprobe** - Must be in PATH for frame extraction
- Test: `ffmpeg -version`

### Docker Deployment
- `docker-compose.yml` - Single service definition
- Mounts video library read-only at `/videos`
- Set `VIDEO_MOUNT` in `.env` or defaults to `./videos`
- Port 5000 exposed

## Developer Workflows

### Running Locally
```bash
cd /home/ben/Documents/github/introdetectandrename
source venv/bin/activate
python frame_viewer_server.py
# Server runs on http://localhost:5000
# Flask auto-reloads in debug mode (FLASK_DEBUG=true)
```

### Making Changes
- **Backend:** Edit `frame_viewer_server.py` → auto-reloads in debug mode
- **Frontend:** Edit `templates/frame_viewer.html` → hard refresh browser (Ctrl+Shift+R)
- **Test frame extraction:** Use browser console network tab, look for 200 responses
- **Check server logs:** Terminal output shows all requests and errors

### Common Issues
- **Port 5000 in use:** Change `FLASK_PORT` or kill conflicting process
- **ffmpeg not found:** Install via package manager, ensure in PATH
- **Frame extraction "not working":** Check server logs - usually returns 200, issue is UI confusion
- **Virtual env wrong:** User has both `venv/` and `.venv/`, always use `venv/`
- **Mobile scrolling:** Body has `overflow: hidden` by default, mobile media query at max-width 768px enables scrolling

## Project-Specific Conventions

### File Naming Format
Generated by frontend after episode selection:
```
Show Name - S##E##-E## - Title1 and Title2 and Title3 [Quality].ext
```
- Preserves quality tags from original (WEBDL-1080p, AAC 2.0, etc.)
- Combines titles with " and " separator
- Episode range format: E01-E03

### Status Badge Logic (templates/frame_viewer.html:renderEpisodeList)
```javascript
// Missing from Sonarr (red)
if (!ep.sonarr_has_file) {
  badge.className = 'status-badge missing';
}
// Has file in Sonarr (green)
else {
  badge.className = 'status-badge has-file';
}
// Multi-episode candidate (orange border)
if (ep.is_multi_episode_candidate) {
  li.classList.add('multi-episode-candidate');
}
```

### Tree Browser State Management
Folders maintain expand/collapse state in `folderStates` object. When navigating, preserve user's exploration context. Natural sorting applied to both folders and files.

### Mobile Responsive Design
- Media query at `@media screen and (max-width: 768px)`
- Body allows scrolling (`overflow-y: auto`, `height: auto`)
- Left panel becomes full-width, stacks above main content
- Episode list switches to column layout for easier mobile navigation

### Frame Thumbnails
- Fixed height of 150px with `object-fit: contain`
- Shows full frame without cutting off content
- Eliminates blank space below thumbnails

## Documentation Hierarchy

1. **FRAME_VIEWER_AI_GUIDE.md** - Comprehensive AI assistant guide (467 lines)
   - Technical details, API endpoints, common workflows
   - Known issues, deprecated files, user context
   - **Read this first** for system understanding

2. **VALIDATION_WORKFLOW.md** - User-facing workflow guide
   - Step-by-step instructions for validation
   - Multi-episode handling strategies
   - Timestamp guides for different show lengths

3. **README.md** - General setup and usage
   - Installation instructions (Docker + manual)
   - Environment variable reference
   - API endpoint documentation

4. **archive_old_ocr_system/docs/** - DEPRECATED OCR approach
   - DO NOT reference or use these files
   - Kept for historical context only

## Integration Points

### TVDB API v4
- Endpoint: `https://api4.thetvdb.com/v4`
- Authentication: Bearer token from `/login` endpoint
- Key endpoints: `/search`, `/series/{id}/extended`, `/series/{id}/episodes/default`
- Client class: `TVDBClient` in `tvdb_loader.py`

### Sonarr API v3
- Base URL: `http://10.0.1.90:8993/api/v3`
- Authentication: `X-Api-Key` header
- Key endpoints: `/series`, `/episodefile`, `/wanted/missing`, `/command` (for RescanSeries)
- Helper function: `sonarr_request()` in `frame_viewer_server.py`
- Refresh endpoint: `POST /api/sonarr/series/<id>/refresh` triggers RescanSeries command

### Unified Endpoint Pattern
`/api/unified/series/<tvdb_id>/season/<num>?sonarr_id=<id>` combines data:
1. Fetch TVDB episodes for metadata
2. Fetch Sonarr files for status
3. Match by season/episode number
4. Return enriched episode list with both datasets

This pattern eliminates duplicate API calls from frontend.

## User Context & Preferences

- **User:** ben, Linux, bash shell
- **Primary use case:** Managing "Paw Patrol" episodes (TVDB: 272472, Sonarr: 222)
- **Challenge:** Multi-episode files with incorrect filenames
- **Preference:** Visual validation over automated detection
- **Working style:** Goal-oriented, iterative, prefers seeing results
- **Video library:** SMB mount at `/run/user/{uid}/gvfs/smb-share:...`

### User's Past Decisions
- Abandoned OCR system after extensive attempts (see `archive_old_ocr_system/`)
- Chose Flask over other frameworks (simple, no build step)
- Chose vanilla JS over React/Vue (no complexity, single file)
- Hardcoded credentials during development (aware of `.env` for production)

## When User Reports Issues

1. **Always check server logs first** - Terminal output shows all activity
2. **Common false alarms:**
   - "Frames not extracting" → Check server logs for 200 responses, usually working
   - "UI not updating" → Hard refresh browser (Ctrl+Shift+R)
   - "Selection not working" → JavaScript console for errors
3. **Don't immediately rewrite** - Often UI/UX confusion, not bugs
4. **Ask clarifying questions** - User appreciates thoughtful analysis

## Files to NEVER Delete or Suggest Removing
- `frame_viewer_server.py` - Active backend
- `templates/frame_viewer.html` - Active frontend
- `tvdb_loader.py` - Active TVDB client
- `config.json` - Show configuration
- `requirements.txt` - Dependencies
- `venv/` - Python environment
- `Paw Patrol/` - User's video library

## Multi-Replace Pattern
For changes spanning multiple sections of a file, use `multi_replace_string_in_file` tool instead of sequential edits. More efficient and atomic.
