# Computer Vision & OCR for WineBot

## Architecture

WineBot has two CV modes with different resource requirements:

| Mode | Runtime | Models | Container | Purpose |
|:---|:---|:---|:---|:---|
| **Pixel Diff (built-in)** | 0.5s intervals | None | WineBot | Detect WHEN things change |
| **OCR Text Reading (built-in)** | On-demand | Tesseract (lightweight) | WineBot | Read text from screenshots |
| **UI Element Detection (built-in)** | On-demand | OpenCV DNN (no GPU needed) | WineBot | Find buttons, menus, dialogs |
| **OmniParser v2 (offline)** | Post-recording | YOLOv8 + Florence-2 (~2GB) | **Separate container** | Full GUI parsing + annotation enrichment |

## Why Offline OmniParser Is the Right Approach

OmniParser v2 needs PyTorch, Ultralytics, and Transformers — adding ~3GB to the WineBot image.
Running it in a separate container avoids this. The workflow:

```
1. WineBot records session → video_001.mkv + watcher.jsonl
2. Offline container extracts frames from MKV
3. OmniParser v2 analyzes each frame:
   - Detects ALL UI elements (buttons, menus, text fields, dropdowns)
   - Reads text from each element
   - Produces element coordinates with labels
4. Results merged back into watcher.jsonl as annotations
5. cv-analyze.py compares expected vs actual UI state
```

## Offline Analysis Pipeline

### Container Setup

```bash
# Separate container with PyTorch + OmniParser
docker build -t winebot-cv-analyzer -f docker/Dockerfile.cv-analyzer .

# Mount recordings volume, run analysis
docker run --rm \
  -v $(pwd)/artifacts/sessions:/sessions \
  winebot-cv-analyzer \
  --session-dir /sessions/session-2026-06-21-abc123 \
  --output /sessions/session-2026-06-21-abc123/analysis/
```

### What OmniParser Detects Per Frame

From a Wine Notepad + Save As dialog screenshot:

```json
{
  "frame": 87,
  "timestamp_ms": 45123,
  "elements": [
    {"id": 0, "type": "window", "bbox": [5, 43, 557, 355],
     "title": "Save As", "confidence": 0.98},
    {"id": 1, "type": "label", "bbox": [15, 52, 80, 18],
     "text": "Save in:", "confidence": 0.95},
    {"id": 2, "type": "dropdown", "bbox": [100, 50, 420, 22],
     "text": "", "confidence": 0.93},
    {"id": 3, "type": "label", "bbox": [15, 305, 75, 18],
     "text": "File name:", "confidence": 0.96},
    {"id": 4, "type": "text_field", "bbox": [95, 303, 420, 24],
     "text": "*.txt", "confidence": 0.94},
    {"id": 5, "type": "label", "bbox": [15, 280, 90, 18],
     "text": "Save as type:", "confidence": 0.95},
    {"id": 6, "type": "dropdown", "bbox": [100, 278, 420, 22],
     "text": "Text Documents (*.txt)", "confidence": 0.93},
    {"id": 7, "type": "button", "bbox": [370, 325, 80, 25],
     "text": "Save", "confidence": 0.97},
    {"id": 8, "type": "button", "bbox": [455, 325, 80, 25],
     "text": "Cancel", "confidence": 0.97},
    {"id": 9, "type": "button", "bbox": [15, 325, 50, 25],
     "text": "Help", "confidence": 0.91}
  ]
}
```

### Annotation Enrichment

This data feeds back into the demo scripts to provide **exact element coordinates**:

```bash
# Instead of: "click somewhere near x=370, y=320 to hit Save"
# You get:     "Save button is at bbox [370, 325, 80, 25] → click center 410, 337"

# The enriched annotation becomes:
annotate "Save button at (410, 337) — click via /input/mouse/click"
api_post "/input/mouse/click" '{"x":410,"y":337,"button":1,"window_title":"Save As"}'
```

## Built-in CV Tools (No OmniParser)

### Pixel Diff (`cv-watcher.py`)

Watches the desktop and logs pixel changes + window inventory:

```bash
python3 scripts/diagnostics/cv-watcher.py --watch --duration 180
```

Output: `watcher.jsonl` with per-frame pixel diffs and visible window titles.

### CV Analyzer (`cv-analyze.py`)

Reads `watcher.jsonl` and reports warnings, errors, window appearance timeline:

```bash
python3 scripts/diagnostics/cv-analyze.py /tmp/winebot_watcher/watcher.jsonl
```

Auto-detects content start (first frame with >10Kpx change) to skip stale windows.

### Element Detection (`cv-element-detect.py`)

OpenCV + Tesseract OCR. Detects rectangular UI regions and reads text:

```bash
python3 scripts/diagnostics/cv-element-detect.py --screenshot
```

Output: JSON with window titles, key text snippets, detected element bboxes.

### Template Matching (`find_and_click.py`)

OpenCV template matching for "find this icon and click it":

```bash
python3 automation/examples/find_and_click.py --template button.png --click
```

## Integration Points

### For Demo Scripts

Each demo writes annotation events to the recording. After offline OmniParser analysis,
the annotations can be enriched with element coordinates:

```bash
# Before enrichment:
[ANNOTATION] Ctrl+S: Wine Save As dialog opened

# After enrichment:
[ANNOTATION] Ctrl+S: Wine Save As dialog opened
[ELEMENT] Save As dialog: bbox [5,43,557,355]
[ELEMENT] File name field: bbox [95,303,420,24] text="*.txt"
[ELEMENT] Save button: bbox [370,325,80,25] click_target=(410,337)
[ELEMENT] Cancel button: bbox [455,325,80,25] click_target=(495,337)
```

### For Automated Testing

The analyzer can assert expected UI state:

```python
assertions = [
    {"frame_range": [85, 95], "expected": "window 'Save As' visible"},
    {"frame_range": [85, 95], "expected": "button 'Save' at [370, 325, 80, 25]"},
    {"frame_range": [100, 110], "expected": "window 'Save As' NOT visible"},
]
```

## Dependency Matrix

| Dependency | Built-in | Offline Analyzer | Purpose |
|:---|:---:|:---:|:---|
| OpenCV | ✅ | ✅ | Image processing |
| NumPy | ✅ | ✅ | Array operations |
| Pillow | ✅ | ✅ | Image I/O |
| Tesseract OCR | ✅ | ✅ | Text reading |
| pytesseract | ✅ | ✅ | OCR Python bindings |
| PyTorch | ❌ | ✅ | Deep learning runtime |
| Ultralytics | ❌ | ✅ | YOLOv8 inference |
| Transformers | ❌ | ✅ | Florence-2 model |
| OmniParser v2 weights | ❌ | ✅ | ~200MB model files |

## File Structure

```
scripts/diagnostics/
├── cv-watcher.py              # Pixel diff + window inventory (built-in)
├── cv-analyze.py              # Warning/error detection (built-in)
└── cv-element-detect.py       # OCR + element detection (built-in)

docker/
├── Dockerfile                  # WineBot image (OpenCV + Tesseract only)
└── Dockerfile.cv-analyzer     # Offline analyzer (PyTorch + OmniParser)

docs/
└── computer-vision.md          # This file
```
