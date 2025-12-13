#!/bin/bash
# Cleanup script for Frame Viewer project
# Moves deprecated OCR-related files to archive folder

echo "🧹 Cleaning up deprecated files..."

# Create archive directory
mkdir -p archive_old_ocr_system
mkdir -p archive_old_ocr_system/docs
mkdir -p archive_old_ocr_system/scripts
mkdir -p archive_old_ocr_system/tests
mkdir -p archive_old_ocr_system/logs
mkdir -p archive_old_ocr_system/data

# Move old documentation
echo "📄 Archiving old documentation..."
mv DETECTION_STATUS.md archive_old_ocr_system/docs/ 2>/dev/null
mv GENERIC_SETUP.md archive_old_ocr_system/docs/ 2>/dev/null
mv IMPLEMENTATION_CHECKLIST.md archive_old_ocr_system/docs/ 2>/dev/null
mv OCR_APPROACH.md archive_old_ocr_system/docs/ 2>/dev/null
mv OCR_MATCHER_GUIDE.md archive_old_ocr_system/docs/ 2>/dev/null
mv OCR_SOLUTION.md archive_old_ocr_system/docs/ 2>/dev/null
mv OCR_TITLE_MATCHER_SUMMARY.md archive_old_ocr_system/docs/ 2>/dev/null
mv README.md archive_old_ocr_system/docs/ 2>/dev/null
mv SOLUTION.md archive_old_ocr_system/docs/ 2>/dev/null
mv SYSTEM_OVERVIEW.md archive_old_ocr_system/docs/ 2>/dev/null
mv TVDB_GUIDE.md archive_old_ocr_system/docs/ 2>/dev/null
mv TVDB_INTEGRATION.md archive_old_ocr_system/docs/ 2>/dev/null
mv USAGE.md archive_old_ocr_system/docs/ 2>/dev/null
mv VERIFICATION_WORKFLOW.md archive_old_ocr_system/docs/ 2>/dev/null
mv WORKFLOW.md archive_old_ocr_system/docs/ 2>/dev/null

# Move OCR scripts
echo "🔧 Archiving OCR scripts..."
mv ocr_title_detector.py archive_old_ocr_system/scripts/ 2>/dev/null
mv ocr_title_matcher.py archive_old_ocr_system/scripts/ 2>/dev/null
mv ocr_batch_scanner.py archive_old_ocr_system/scripts/ 2>/dev/null
mv smart_ocr.py archive_old_ocr_system/scripts/ 2>/dev/null
mv visual_title_finder.py archive_old_ocr_system/scripts/ 2>/dev/null
mv batch_extract_candidates.py archive_old_ocr_system/scripts/ 2>/dev/null
mv batch_scanner.py archive_old_ocr_system/scripts/ 2>/dev/null
mv check_suspicious.py archive_old_ocr_system/scripts/ 2>/dev/null
mv debug_matching.py archive_old_ocr_system/scripts/ 2>/dev/null
mv debug_ocr.py archive_old_ocr_system/scripts/ 2>/dev/null
mv episode_detector.py archive_old_ocr_system/scripts/ 2>/dev/null
mv episode_splitter.py archive_old_ocr_system/scripts/ 2>/dev/null
mv example_real_video.py archive_old_ocr_system/scripts/ 2>/dev/null
mv file_analyzer.py archive_old_ocr_system/scripts/ 2>/dev/null
mv find_title_cards.py archive_old_ocr_system/scripts/ 2>/dev/null
mv generate_commands.py archive_old_ocr_system/scripts/ 2>/dev/null
mv generate_renames.py archive_old_ocr_system/scripts/ 2>/dev/null
mv interactive_verify.py archive_old_ocr_system/scripts/ 2>/dev/null
mv lookup_titles.py archive_old_ocr_system/scripts/ 2>/dev/null
mv pipeline.py archive_old_ocr_system/scripts/ 2>/dev/null
mv scene_detector.py archive_old_ocr_system/scripts/ 2>/dev/null
mv smart_detector.py archive_old_ocr_system/scripts/ 2>/dev/null
mv smart_matcher.py archive_old_ocr_system/scripts/ 2>/dev/null
mv title_matcher.py archive_old_ocr_system/scripts/ 2>/dev/null
mv web_verifier.py archive_old_ocr_system/scripts/ 2>/dev/null
mv sonarr_validator.py archive_old_ocr_system/scripts/ 2>/dev/null

# Move test files
echo "🧪 Archiving test files..."
mv test_ocr_detector.py archive_old_ocr_system/tests/ 2>/dev/null
mv test_ocr_matcher.py archive_old_ocr_system/tests/ 2>/dev/null
mv test_quick_batch.py archive_old_ocr_system/tests/ 2>/dev/null
mv test_single_file.py archive_old_ocr_system/tests/ 2>/dev/null
mv test_smart_detector.py archive_old_ocr_system/tests/ 2>/dev/null
mv test_suspected_files.py archive_old_ocr_system/tests/ 2>/dev/null
mv test_tvdb_integration.py archive_old_ocr_system/tests/ 2>/dev/null

# Move log files
echo "📋 Archiving log files..."
mv batch_extraction.log archive_old_ocr_system/logs/ 2>/dev/null
mv ocr_scan.log archive_old_ocr_system/logs/ 2>/dev/null
mv ocr_scan_full.log archive_old_ocr_system/logs/ 2>/dev/null
mv scan_output.log archive_old_ocr_system/logs/ 2>/dev/null

# Move data files
echo "💾 Archiving data files..."
mv ocr_scan_report.json archive_old_ocr_system/data/ 2>/dev/null
mv verified_s09.json archive_old_ocr_system/data/ 2>/dev/null
mv title_card_candidates archive_old_ocr_system/data/ 2>/dev/null

# Move Makefile
mv Makefile archive_old_ocr_system/ 2>/dev/null

# Create README in archive
cat > archive_old_ocr_system/README.txt << 'EOF'
ARCHIVED OCR SYSTEM
===================

These files are from the deprecated OCR-based episode detection approach.
The project has moved to a visual validation system using the Frame Viewer.

This archive is kept for reference only. Do not use these files.

Active system files:
- frame_viewer_server.py
- templates/frame_viewer.html
- tvdb_loader.py
- config.json
- requirements.txt

See FRAME_VIEWER_AI_GUIDE.md for current system documentation.

Archived on: December 12, 2025
EOF

echo ""
echo "✅ Cleanup complete!"
echo ""
echo "📦 Archived files moved to: archive_old_ocr_system/"
echo ""
echo "🎯 Active system files:"
echo "   - frame_viewer_server.py"
echo "   - templates/frame_viewer.html"
echo "   - tvdb_loader.py"
echo "   - config.json"
echo "   - requirements.txt"
echo "   - VALIDATION_WORKFLOW.md"
echo "   - FRAME_VIEWER_README.md"
echo "   - FRAME_VIEWER_AI_GUIDE.md"
echo ""
echo "📁 Protected folders:"
echo "   - Paw Patrol/"
echo "   - venv/"
echo "   - templates/"
echo ""
