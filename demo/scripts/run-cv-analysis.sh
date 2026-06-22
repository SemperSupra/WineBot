#!/usr/bin/env bash
# run-cv-analysis.sh — Batch CV/OCR analysis over all WineBot demo videos
# Extracts frames, runs element detection + OCR, generates annotated reports.
# Usage: bash demo/scripts/run-cv-analysis.sh
set -u

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
DEMO_OUTPUT="$SCRIPT_DIR/../output"
ANALYSIS_DIR="$DEMO_OUTPUT/analysis"

echo "============================================================"
echo "  WineBot CV/OCR Demo Video Analysis"
echo "============================================================"
echo ""
echo "  Input:  $DEMO_OUTPUT"
echo "  Output: $ANALYSIS_DIR"
echo ""

# Check prerequisites
if ! command -v ffmpeg &> /dev/null; then
  echo "ERROR: ffmpeg not found — required for frame extraction"
  exit 2
fi

if ! python3 -c "import cv2" 2>/dev/null; then
  echo "ERROR: OpenCV not available — pip install opencv-python-headless"
  exit 2
fi

HAS_TESSERACT=0
if python3 -c "import pytesseract" 2>/dev/null; then
  HAS_TESSERACT=1
  echo "  Tesseract OCR: available"
else
  echo "  Tesseract OCR: NOT available — text detection disabled"
  echo "    Install: pip install pytesseract && apt-get install tesseract-ocr-eng"
fi
echo ""

# Run batch analyzer over all demo MKVs
echo "--- Running batch CV analysis ---"
echo ""

# Choose mode based on available dependencies
MODE="built-in"
if [ "$HAS_TESSERACT" -eq 0 ]; then
  echo "WARNING: Running without OCR — text detection will be empty"
fi

python3 "$SCRIPT_DIR/../../scripts/diagnostics/cv-batch-analyze.py" \
  --input "$DEMO_OUTPUT" \
  --output "$ANALYSIS_DIR" \
  --frame-interval 1.0 \
  --mode "$MODE"

EXIT_CODE=$?

echo ""
echo "============================================================"
if [ $EXIT_CODE -eq 0 ]; then
  echo "  CV Analysis: CLEAN — no warnings detected"
else
  echo "  CV Analysis: COMPLETE (exit code: $EXIT_CODE)"
fi
echo ""
echo "  Per-demo analysis:"
for d in "$ANALYSIS_DIR"/*/; do
  name=$(basename "$d")
  if [ -f "$d/summary.json" ]; then
    frames=$(python3 -c "import json; d=json.load(open('$d/summary.json')); print(d.get('frames_analyzed',0))" 2>/dev/null)
    warnings=$(python3 -c "import json; d=json.load(open('$d/summary.json')); print(d.get('total_warnings',0))" 2>/dev/null)
    targets=$(python3 -c "import json; d=json.load(open('$d/summary.json')); print(d.get('frames_with_click_targets',0))" 2>/dev/null)
    echo "    $name: ${frames}frames ${warnings}warnings ${targets}targets"
  fi
done
echo ""
echo "  Batch report: $ANALYSIS_DIR/batch_report.json"
echo ""
echo "  To view per-demo reports:"
for d in "$ANALYSIS_DIR"/*/; do
  name=$(basename "$d")
  if [ -f "$d/report.html" ]; then
    echo "    open $d/report.html"
  fi
done
echo ""
echo "============================================================"

exit $EXIT_CODE
