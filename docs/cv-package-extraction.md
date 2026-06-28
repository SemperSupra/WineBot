# CV/OCR Package Extraction Plan

**Goal:** Extract the CV/OCR pipeline into an installable Python package (`desktop-ui-cv`) served from GitHub, decoupled from the WineBot monorepo while keeping everything working during the transition.

---

## Target Package Structure

```
packages/desktop-ui-cv/
├── pyproject.toml
├── README.md
├── LICENSE
├── annotation_tool/
│   ├── __init__.py
│   └── server.py              # Current annotation_server.py
├── src/
│   └── winebot_cv/
│       ├── __init__.py
│       ├── detectors/
│       │   ├── __init__.py
│       │   ├── base.py            # UIDetector ABC (from ui_detectors.py)
│       │   ├── contour.py         # ContourDetector
│       │   ├── yolo.py            # YOLOUIDetector
│       │   ├── omniparser.py      # OmniParserDetector
│       │   ├── screenparser.py    # ScreenParserDetector
│       │   ├── wine.py            # WineUIDetector (our fine-tuned model)
│       │   └── vlm_ground.py      # VLMGroundingDetector
│       ├── ocr/
│       │   ├── __init__.py
│       │   ├── base.py            # OCREngine ABC
│       │   ├── tesseract.py       # TesseractEngine
│       │   └── paddle_onnx.py     # PaddleOCREngine
│       ├── classification/
│       │   ├── __init__.py
│       │   ├── state.py           # ML state classifier
│       │   └── heuristics.py      # Geometry-based fallback
│       ├── embedding/
│       │   ├── __init__.py
│       │   ├── clip.py            # CLIP embedder
│       │   └── siglip.py          # SigLIP2 embedder
│       ├── tracking/
│       │   ├── __init__.py
│       │   └── temporal.py        # IoU matching, persistence
│       ├── dataset/
│       │   ├── __init__.py
│       │   ├── generator.py       # winebot-gt-generator (scene functions)
│       │   ├── oversample.py      # Rare class oversampling
│       │   └── eval_split.py      # Held-out eval dataset generation
│       ├── registry/
│       │   ├── __init__.py
│       │   └── model_registry.py  # Model provenance tracking
│       └── server.py              # FastAPI sidecar (current cv-sidecar-server.py)
├── scripts/                       # CLI entrypoints (thin wrappers)
│   ├── serve.sh                   # Starts the sidecar
│   ├── train-yolo.py
│   ├── train-state-classifier.py
│   ├── generate-dataset.py
│   ├── evaluate.py
│   └── annotate.sh                # Launches annotation tool
└── tests/
    ├── test_detectors.py
    ├── test_ocr.py
    ├── test_classification.py
    └── test_dataset.py
```

---

## pyproject.toml

```toml
[build-system]
requires = ["setuptools>=75", "wheel"]
build-backend = "setuptools.backends._legacy:_Backend"

[project]
name = "desktop-ui-cv"
version = "0.1.0"
description = "Desktop UI element detection, OCR, state classification, and dataset generation"
license = {text = "MIT"}
requires-python = ">=3.12"
dependencies = [
    "opencv-python-headless>=4.9",
    "numpy>=2.0",
    "Pillow>=10.0",
]

[project.optional-dependencies]
gpu = [
    "torch>=2.12",
    "torchvision>=0.27",
    "ultralytics>=8.4",
]
ocr = [
    "pytesseract>=0.3",
    "onnxruntime>=1.17",
]
server = [
    "fastapi>=0.129",
    "uvicorn>=0.41",
]
clip = [
    "open-clip-torch>=2.24",
    "faiss-cpu>=1.8",
]
all = [
    "desktop-ui-cv[gpu,ocr,server,clip]",
]

[tool.setuptools.packages.find]
where = ["src"]
```

---

## Migration Path — 5 Phases

### Phase 1: Create Package Skeleton (no code moved yet)

```bash
mkdir -p packages/desktop-ui-cv/src/winebot_cv/{detectors,ocr,classification,embedding,tracking,dataset,registry}
mkdir -p packages/desktop-ui-cv/{annotation_tool,scripts,tests}
```

**Result:** Package structure exists, `pip install -e packages/desktop-ui-cv` works (imports nothing yet). Docker build unaffected.

### Phase 2: Move Core Detection + OCR (first working package)

Move into `packages/desktop-ui-cv/src/winebot_cv/`:
- `detectors/` — `UIDetector`, `ContourDetector`, `YOLOUIDetector`, `OmniParserDetector`, `ScreenParserDetector`, `WineUIDetector`, `VLMGroundingDetector`
- `ocr/` — `OCREngine`, `TesseractEngine`, `PaddleOCREngine`
- `registry/` — `ModelRegistry`

Keep originals in `scripts/diagnostics/` as thin re-exports or symlinks so nothing breaks:

```python
# scripts/diagnostics/ui_detectors.py → becomes:
from winebot_cv.detectors import *  # noqa: F401, F403
```

**Result:** Sidecar still works. Package installable. WinBot can `pip install desktop-ui-cv` for detection + OCR only.

### Phase 3: Move Dataset + Training Scripts

Move into package:
- `dataset/` — GT generator, oversampling, eval split
- `classification/` — State classifier
- `embedding/` — CLIP, SigLIP2
- `tracking/` — Temporal consistency

**Result:** Full pipeline available as package. Training scripts become thin CLI wrappers.

### Phase 4: Move Annotation Tool + Sidecar Server

Move into package:
- `server.py` — Sidecar FastAPI app
- `annotation_tool/` — Annotation WebUI

Sidecar Dockerfile changes:
```dockerfile
# Before: COPY scripts/diagnostics/cv-sidecar-server.py /scripts/
# After:
RUN pip install "desktop-ui-cv[server,gpu] @ git+https://github.com/SemperSupra/WineBot.git@main#subdirectory=packages/desktop-ui-cv"
COPY packages/desktop-ui-cv/scripts/serve.sh /entrypoint.sh
```

**Result:** Sidecar container installs from GitHub. Same code, different delivery mechanism.

### Phase 5: Optional Repo Split

If CV/OCR grows independently (WinBot, research, external contributors), move to its own repo:

```
github.com/SemperSupra/desktop-ui-cv    # New repo, copied from packages/
github.com/SemperSupra/WineBot           # Removes packages/, installs via pip
```

WineBot's Dockerfile then:
```dockerfile
RUN pip install "desktop-ui-cv[server,gpu] @ git+https://github.com/SemperSupra/desktop-ui-cv.git@v1.0.0"
```

---

## CI Changes

### In WineBot CI (`.github/workflows/ci.yml`)

Add a job to test the package independently:

```yaml
cv-package:
  name: CV Package Tests
  runs-on: ubuntu-latest
  steps:
    - uses: actions/checkout@v4
    - name: Install package
      run: pip install -e packages/desktop-ui-cv[all]
    - name: Run CV package tests
      run: pytest packages/desktop-ui-cv/tests/
```

Add a release job to build the wheel:

```yaml
build-cv-wheel:
  name: Build CV Package Wheel
  needs: [pre-flight, integration]
  runs-on: ubuntu-latest
  steps:
    - uses: actions/checkout@v4
    - name: Build wheel
      run: |
        pip install build
        python -m build packages/desktop-ui-cv/
    - name: Upload wheel artifact
      uses: actions/upload-artifact@v4
      with:
        name: desktop-ui-cv-wheel
        path: packages/desktop-ui-cv/dist/*.whl
```

---

## What Doesn't Change

| Component | Stays As-Is |
|-----------|-------------|
| **Sidecar API** | `POST /analyze` still returns `{elements, text, state}` — no API break |
| **Sidecar port** | Still port 8001 |
| **YOLO model paths** | Still `/models/wine-yolo26s-v3.pt` |
| **Annotation tool** | Still on port 8080 |
| **Model registry** | Still scans `/models` |
| **Docker compose** | Services unchanged |
| **WineBot scripts** | Thin wrappers still work from same CLI paths |

---

## Timeline

| Phase | What | Effort | Risk |
|-------|------|--------|------|
| 1 | Package skeleton | 30 min | None (no code moved) |
| 2 | Detection + OCR move | 2-3 hours | Low (re-exports keep compat) |
| 3 | Dataset + training move | 2-3 hours | Low |
| 4 | Server + annotation move | 2 hours | Medium (Dockerfile change) |
| 5 | Optional repo split | 1 hour | Low (pip URL just changes) |

**Can be done incrementally.** Phase 2 alone unlocks the main goal — WinBot and research projects can `pip install desktop-ui-cv` for detection and OCR.
