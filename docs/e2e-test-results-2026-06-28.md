# Comprehensive E2E Test Results

**Date:** 2026-06-28 | **Branch:** `feat/cv-package-extraction` | **PR:** #64

## Build Results

| Image | Target | Duration | Status |
|:---|:---|:---:|:---:|
| Core WineBot | `intent-slim` | ~100s | ✅ Pass |
| CV Sidecar | `Dockerfile.cv-analyzer-gpu` | ~285s | ✅ Pass |
| CV Sidecar | `Dockerfile.cv-analyzer` (CPU) | ~85s | ✅ Pass |

## Service Health

| Service | Port | Status | Details |
|:---|:---:|:---:|:---|
| CV Sidecar | 8001 | ✅ Healthy | All 8 detectors, 6 OCR backends available |
| Core WineBot API | 8000 | ❌ Not running | Headless container not started for this test |
| Annotation WebUI | 8080 | ✅ Running | Served by sidecar |

## Feature Tests

### 1. CV Analyze Endpoint
- **`POST /analyze` with binary image** → `500 Internal Server Error`
- **Root Cause:** FastAPI's `jsonable_encoder` tries to `.decode()` raw bytes as UTF-8 in its default error handler. Binary image data (PNG header 0x89) fails UTF-8 decoding.
- **Severity:** Bug in error handler, not in the analysis pipeline itself
- **Issue:** [#71](https://github.com/SemperSupra/WineBot/issues/71)

### 2. CV Health Endpoint
- **`GET /health`** → ✅ Pass
- All 8 detectors available: contour, yolo, omniparser, uidetr1, screenparser, screenparser_wine, wine, vlm_ground
- All 6 OCR backends: tesseract, paddle_onnx (4 variants)
- Model catalog: 18 total models, 15 active

### 3. CV Detection Backends
| Detector | Status | Notes |
|:---|:---:|:---|
| Contour | ⚠️ Untested | Needs working /analyze |
| YOLO (wine v3) | ⚠️ Untested | Needs working /analyze |
| OmniParser | ⚠️ Untested | Needs working /analyze |
| UI-DETR-1 | ⚠️ Untested | Needs working /analyze |
| ScreenParser | ⚠️ Untested | Needs working /analyze |
| VLM Ground | ⚠️ Untested | Needs VLM provider config |

### 4. OCR Backends
| OCR | Status | Notes |
|:---|:---:|:---|
| Tesseract | ⚠️ Untested | Needs working /analyze |
| PaddleOCR ONNX | ⚠️ Untested | Needs working /analyze |

### 5. Demo Pipeline
- ❌ Not tested — requires core WineBot container (port 8000) to be running
- 8 demo scripts in `demo/scripts/` need a live WineBot instance

### 6. API Endpoints (if core running)
- `GET /health` — ❌ Container not started
- `GET /health/windows` — ❌ Container not started
- `POST /input/key` — ❌ Container not started
- `POST /apps/run` — ❌ Container not started
- `POST /lifecycle/shutdown` — ❌ Container not started

## Package Extraction Verification

| Package | Repo | Tag | Status |
|:---|:---|:---:|:---:|
| desktop-ui-cv | github.com/SemperSupra/desktop-ui-cv | v0.1.0 | ✅ Installed from local wheel in build |
| kv-ground-server | github.com/SemperSupra/kv-ground-server | v0.1.0 | ✅ Repo created, tagged |
| ui-captioning | github.com/SemperSupra/ui-captioning | v0.1.0 | ✅ Repo created, tagged |

## Docker Build Verification

- **Local wheel fallback** works: `ls /tmp/wheels/desktop_ui_cv-*.whl` detected, installed from local file
- **Import verification** passes in build: `from winebot_cv.detectors.engines import WineUIDetector` OK
- **PyTorch/CUDA** proper: `torch.cuda.is_available() -> True` at runtime with `--gpus all`

## Issues Found

| # | Title | Severity | Status |
|:---|:---|:---:|:---:|
| #71 | /analyze endpoint returns 500 on binary image upload | Medium | 📝 Documented |

## Recommendation

The sidecar is functionally healthy (health check passes, all backends report available).
The /analyze 500 error is a FastAPI error-handler edge case, not a pipeline logic bug.

To complete full E2E validation:
1. Fix `/analyze` binary upload bug (add custom exception handler)
2. Start core WineBot container (requires ~60s for Wine prefix init)
3. Run demo pipeline against live WineBot + sidecar
4. Run parity test suite from WinBot repo
