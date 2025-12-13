# Episode Detection & Title Extraction Tool

**The Problem**: TV episode files often have incorrect or incomplete filenames. A file named `S09E22.mkv` might actually contain episodes 37 and 38, or just episode 1, or anything else. OCR on title cards is unreliable.

**The Solution**: Detect episode boundaries automatically, then use manual title specification for reliable renaming.

## Quick Start

### Single Test Run
```bash
# Dry run (no files written, just analysis)
.venv/bin/python pipeline.py "video.mkv" --assume-two --no-split

# Look at the output:
# - Auto-detected: 1 or 2 episodes?
# - OCR results (for reference)
# - Suggested filenames
```

### With Manual Titles
```bash
# Dry run with manual titles (OCR bypassed)
.venv/bin/python pipeline.py "video.mkv" --assume-two --no-split \
  --manual-titles "1=Episode Title 1,2=Episode Title 2"

# Actually split and rename
.venv/bin/python pipeline.py "video.mkv" --assume-two \
  --manual-titles "1=Episode Title 1,2=Episode Title 2"
```

### Batch Processing
```bash
# Generate commands from CSV mapping
python generate_commands.py > run_all.sh
bash run_all.sh  # runs all tests
```

## Features

### Episode Detection
- **Auto-detect 1 vs 2 episodes** based on intro patterns
- **Override with `--num-episodes`** if auto-detection fails
- **Snap split points to scene boundaries** for clean cuts

### Title Extraction (Priority Order)
1. **OCR + Fuzzy Matching** (if `--titles-file` provided)
   - Tesseract extracts text from title card frames
   - RapidFuzz matches against known episode titles
   - Falls back to filename titles if OCR fails

2. **Filename Extraction** (automatic)
   - Parses `S##E##-E## - Title1 and Title2` patterns
   - Shown for reference (not relied upon)

3. **Manual Override** (if `--manual-titles` provided)
   - Direct title specification: `"1=Title1,2=Title2"`
   - Takes priority over OCR and filename

4. **Web Lookup** (experimental, requires TVDB API key)
   - Fallback lookup if other methods fail

## Real-World Examples

### Case 1: Filename Correct, 2 Episodes
```bash
# File: "S01E01-E02 - Pups Make a Splash and Pups Fall Festival.mkv"
.venv/bin/python pipeline.py "file.mkv" --assume-two --titles-file titles.txt

# Result:
# - Auto-detects: 2 episodes
# - Extracts filename titles as reference
# - OCR attempts to match against titles.txt
# - Falls back to filename titles if OCR fails
```

### Case 2: Single Episode (Not Two)
```bash
# File: "S09E08 - Big Truck Pups Stop a Flood.mkv"
# Actually contains: 1 episode (not 2)
.venv/bin/python pipeline.py "file.mkv" --num-episodes 1

# Result:
# - Treats entire file as single episode
# - No split attempted
```

### Case 3: Two Episodes, Wrong Filename
```bash
# File: "S09E24 - Aqua Pups.mkv"
# Actually contains: Episodes 41 & 42 (not 24)
.venv/bin/python pipeline.py "file.mkv" --assume-two \
  --manual-titles "1=Aqua Pups,2=Pups and the Big Freeze"

# Result:
# - Detects 2 episodes
# - Splits at boundary
# - Names them with actual episode titles
# - Creates: file_ep1.mkv (Episode 41) and file_ep2.mkv (Episode 42)
```

### Case 4: Unknown What's in File
```bash
# File: "S09E22.mkv" (unknown content)
.venv/bin/python pipeline.py "file.mkv" --assume-two --no-split --verbose

# Look at output:
# - Scene detection shows if 1 or 2 episodes
# - OCR results (raw text at various timestamps)
# - Manual verification before proceeding
```

## Command Reference

### Core Options
- `input` - Input video file
- `--assume-two` - Treat as potentially 2-episode file (enables auto-detection)
- `--num-episodes N` - Override: force 1 or 2 episodes

### Title Extraction
- `--titles-file PATH` - Known episode titles (one per line) for fuzzy matching
- `--manual-titles "1=Title1,2=Title2"` - Explicit title override
- `--sample-times "1=45,2=11:45"` - Explicit frame times for OCR sampling
- `--series-name NAME` - For TVDB lookup (requires API key)

### Output Control
- `--no-split` - Dry run: analyze only, don't write files
- `--json-out PATH` - Save analysis results as JSON
- `--save-frames PATH` - Save OCR sample frames for inspection
- `--auto-rename` - Rename original file with extracted title (experimental)

### Fine-tuning
- `--scene-threshold FLOAT` - Scene detection sensitivity (default: 0.4)
- `--ocr-lang LANG` - Tesseract language (default: eng)
- `--post-intro-offsets TIMES` - Seconds after intro for title card sampling
- `--episode-offsets TIMES` - Seconds from episode start for sampling
- `--verbose` - Show detailed detection/OCR results

## Workflow

### Step 1: Analyze Unknown Files
```bash
for file in *.mkv; do
  echo "=== $file ==="
  .venv/bin/python pipeline.py "$file" --assume-two --no-split --verbose | head -30
done
```

### Step 2: Create Mapping File
Edit `file_mapping.csv`:
```csv
filename,actual_ep1,actual_ep1_title,actual_ep2,actual_ep2_title,notes
S09E24.mkv,41,Aqua Pups,42,Pups and the Big Freeze,Filename wrong
S09E22.mkv,?,Episode Title,?,Episode Title,Unknown content
```

### Step 3: Generate Commands
```bash
python generate_commands.py > process_all.sh
```

### Step 4: Test Each
```bash
bash process_all.sh  # runs all with --no-split first
```

### Step 5: Execute Real Processing
Remove `--no-split` from commands and run to actually split files.

## File Structure After Processing

```
Original:
  Paw Patrol - S09E24 - Aqua Pups.mkv (1.3 GB)

After processing:
  Paw_Patrol_S09E24_Aqua_Pups_ep1.mkv        (650 MB) - Episode 41
  Paw_Patrol_S09E24_Aqua_Pups_ep1_intro.mkv  (50 MB)  - Intro for ep1
  Paw_Patrol_S09E24_Aqua_Pups_ep2.mkv        (650 MB) - Episode 42
  Paw_Patrol_S09E24_Aqua_Pups_ep2_intro.mkv  (50 MB)  - Intro for ep2
```

## Troubleshooting

### "Auto-detected: 1 episode" but file contains 2?
- Use `--num-episodes 2` to override

### "Auto-detected: 2 episodes" but file contains 1?
- Use `--num-episodes 1` to override

### OCR not finding title?
- Use explicit frame times: `--sample-times "1=45,2=700"`
- Use manual titles: `--manual-titles "1=Title,2=Title"`
- Check `--save-frames DIR` to inspect what's being OCR'd

### Split point is wrong?
- Adjust `--scene-threshold` (lower = more sensitive, higher = less)
- Or check if file actually has clean episode boundary

## Dependencies

- FFmpeg (scene detection, video manipulation)
- Tesseract (OCR)
- Python packages: ffmpeg-python, pytesseract, rapidfuzz, pillow, etc.

See `requirements.txt` and `USAGE.md` for full details.

## Why This Tool Exists

Standard workflows assume:
- Filenames are accurate
- OCR on title cards is reliable
- You know exactly what episodes are in each file

Reality:
- Filenames are often wrong or misleading
- OCR captures credits, not titles
- File contents don't match filename metadata

This tool handles all three problems.
