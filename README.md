# Frame Viewer - TV Episode Validator & Renamer

A web-based tool for validating and renaming TV episode files by extracting video frames and matching them against TVDB episode data. Perfect for managing multi-episode files and ensuring proper naming conventions.

## 🎯 Features

- **Visual Frame Extraction**: Extract frames at custom time intervals to verify episode content
- **TVDB Integration**: Search and validate episodes against The Movie Database
- **Sonarr Integration**: Optional integration with Sonarr for existing library management
- **Multi-Episode Support**: Handle files containing multiple episodes with visual grouping
- **Smart Episode Detection**: Auto-detect episode numbers from filenames
- **Time Navigation**: Jump forward/backward with frame-based time controls
- **Episode Search**: Filter and find episodes quickly
- **File Renaming**: Rename files with suggested naming based on selected episodes
- **Natural Sorting**: Properly handles Season 1, 2, ... 10, 11 ordering

## 📋 Prerequisites

- Python 3.12 or higher
- FFmpeg (for frame extraction)
- Docker and Docker Compose (for containerized deployment)

## 🚀 Quick Start with Docker

### 1. Clone the repository

```bash
git clone <your-repo-url>
cd introdetectandrename
```

### 2. Set up environment variables

Copy the example environment file and configure it:

```bash
cp .env.example .env
```

Edit `.env` and set your configuration:

```env
# TVDB API Key (Required)
TVDB_API_KEY=your_tvdb_api_key_here

# Sonarr Integration (Optional)
SONARR_URL=http://localhost:8989
SONARR_API_KEY=your_sonarr_api_key_here

# Video Library Path (Required)
VIDEO_PATH=/path/to/your/video/library

# Flask Configuration (Optional)
FLASK_HOST=0.0.0.0
FLASK_PORT=5000
FLASK_DEBUG=false
```

#### Getting a TVDB API Key

1. Go to [TVDB](https://thetvdb.com/)
2. Create a free account
3. Navigate to your profile settings
4. Generate an API key under "API Access"

### 3. Run with Docker Compose

```bash
docker-compose up -d
```

The application will be available at `http://localhost:5000`

### 4. Stop the container

```bash
docker-compose down
```

## 💻 Manual Installation

### 1. Install system dependencies

**Ubuntu/Debian:**
```bash
sudo apt-get update
sudo apt-get install python3.12 python3-pip ffmpeg
```

**macOS:**
```bash
brew install python@3.12 ffmpeg
```

### 2. Install Python dependencies

```bash
pip install -r requirements.txt
```

### 3. Set up configuration

Create a `.env` file or export environment variables:

```bash
export TVDB_API_KEY="your_tvdb_api_key_here"
export VIDEO_PATH="/path/to/your/video/library"
# Optional Sonarr integration
export SONARR_URL="http://localhost:8989"
export SONARR_API_KEY="your_sonarr_api_key_here"
```

### 4. Run the server

```bash
python frame_viewer_server.py
```

The application will be available at `http://localhost:5000`

## 📖 Workflow

### Step 1: Select Video File
- Browse your video library in the left panel
- Click on a folder to expand and view files
- Select a video file to begin validation

### Step 2: Search for Show
- The show name is auto-populated from the filename
- Click "Search" to find the show on TVDB
- Select the correct show from the dropdown

### Step 3: Select Season
- Choose the season number
- Episodes will load automatically

### Step 4: Extract Frames
- Set start time (MM:SS format)
- Set number of frames to extract
- Set interval between frames (seconds)
- Use ◄ and ► buttons to jump backward/forward
- View time range preview: "Will extract: XX:XX to YY:YY"
- Click "Extract Frames" to preview video content
- Frames display horizontally with scroll support

### Step 5: Select Episode(s)
- Episodes detected from filename are highlighted with a green glow
- Use the search box to filter episodes
- Click on episode(s) that match the video content
- Multi-episode files show connected with orange borders
- Legend shows: Missing (no file), Has File (already exists), Multi-Episode

### Step 6: Rename File
- Review current filename and suggested new filename
- Edit the new filename if needed
- Click "✓ Rename File" to apply changes
- UI resets automatically after successful rename

## 🔧 Configuration

### Environment Variables

| Variable | Required | Default | Description |
|----------|----------|---------|-------------|
| `TVDB_API_KEY` | Yes | - | Your TVDB API key for show metadata |
| `VIDEO_PATH` | Yes | - | Path to your video library |
| `SONARR_URL` | No | - | Sonarr server URL (e.g., http://localhost:8989) |
| `SONARR_API_KEY` | No | - | Sonarr API key for integration |
| `FLASK_HOST` | No | 0.0.0.0 | Flask server host |
| `FLASK_PORT` | No | 5000 | Flask server port |
| `FLASK_DEBUG` | No | false | Enable Flask debug mode |

### Docker Volumes

The Docker container mounts your video library at `/videos`. Make sure your `VIDEO_PATH` in `.env` points to the correct location on your host system.

## 🏗️ Project Structure

```
.
├── frame_viewer_server.py       # Flask backend server
├── templates/
│   └── frame_viewer.html        # Frontend UI
├── tvdb_loader.py               # TVDB API client
├── requirements.txt             # Python dependencies
├── Dockerfile                   # Docker image definition
├── docker-compose.yml           # Docker Compose configuration
├── .env.example                 # Environment variable template
├── .gitignore                   # Git ignore patterns
└── README.md                    # This file
```

## 🐛 Troubleshooting

### FFmpeg not found
Make sure FFmpeg is installed and in your PATH:
```bash
ffmpeg -version
```

### TVDB API errors
- Verify your API key is correct in `.env`
- Check that the API key has proper permissions
- Ensure you have internet connectivity

### Sonarr connection issues
- Verify Sonarr URL and API key in `.env`
- Check that Sonarr is running and accessible
- Note: Sonarr integration is optional

### Frame extraction fails
- Check video file permissions
- Verify FFmpeg can read the video format
- Check server logs for detailed error messages

### Docker container issues
```bash
# View logs
docker-compose logs -f

# Restart container
docker-compose restart

# Rebuild after changes
docker-compose up -d --build
```

## 📝 API Endpoints

- `GET /` - Main UI
- `GET /api/list_videos` - List all video files organized by folder
- `GET /api/search_series?q=<query>` - Search TVDB for shows
- `GET /api/series/<id>/seasons` - Get seasons for a show
- `GET /api/unified/series/<id>/season/<num>` - Get episodes with Sonarr data
- `POST /api/extract_frames` - Extract frames from video
- `POST /api/rename_file` - Rename video file

## 🤝 Contributing

Contributions are welcome! Please feel free to submit issues or pull requests.

## 📄 License

This project is provided as-is for personal use.

## 🙏 Credits

- TVDB for show metadata
- FFmpeg for video processing
- Flask for the web framework
