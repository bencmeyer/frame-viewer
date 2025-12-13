FROM python:3.12-slim

WORKDIR /app

# Install system dependencies
RUN apt-get update && apt-get install -y \
    ffmpeg \
    && rm -rf /var/lib/apt/lists/*

# Copy requirements and install Python dependencies
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy application files
COPY frame_viewer_server.py .
COPY tvdb_loader.py .
COPY templates/ templates/

# Create volume mount point for video files
VOLUME ["/videos"]

# Expose port
EXPOSE 5000

# Run the application
CMD ["python", "frame_viewer_server.py"]
