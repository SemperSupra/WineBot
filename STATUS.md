# Status — 2026-06-23

## Current State

- **Version:** v0.9.7a release containers published on GHCR.
- **Status:** Demo infrastructure complete, CV/OCR sidecar built and live-tested, contracts repo live. PaddleOCR + OmniParser builds deferred (Docker VM crashed overnight).
- **Handoff Point:** `main` at `1c5bb9b`, synced with `origin/main`.
- **Base Runtime:** `ghcr.io/sempersupra/winebot-base:base-2026-05-04`.
- **Contracts Repo:** [winebot-contracts](https://github.com/mark-e-deyoung/winebot-contracts) — 15/15 conformance tests pass.

## Completed This Session

### Demo Infrastructure
- **`_demo_common.sh`** (924 lines, 30 functions) — shared library sourced by all 10 demos
- **`demo-cv-control.sh`** (NEW) — CV-driven control with OCR verification
- **Desktop cleanup** — `fresh_session()` kills app windows + restarts recording between demos
- **Download cache** — Python `linux_dl()` caches to `/wineprefix/drive_c/.winebot_cache/` (persists across runs)
- **Video output** — `stop_recording()` auto-copies to `demo/output/<name>.mkv/.gif/.vtt`
- **Smart trim** — uses `ls -t` for latest video segment
- **AHK pipe dialog** — `pipe_cmd "open_gui"` replaces Ctrl+S (no Wine Save As triggered)
- **All 10 demos** — live-verified against WineBot container, 10/10 pass with output

### CV/OCR Pipeline
- **`cv-sidecar-server.py`** (470 lines) — FastAPI: `/health`, `/analyze`, `/batch`, `/watch/start`, `/watch/stop`
- **`cv-test-runner.py`** (618 lines) — frame extraction + contour detection + annotated HTML reports
- **`cv-batch-analyze.py`** (289 lines) — CI gate with `--exit-on-warnings`
- **`merge-timeline.py`** (303 lines) — 4-layer unified timeline, timestamp bug fixed
- **`demo-expect.py`** (226 lines) — expected-state assertion checker
- **`cv-eval-dataset.py`** (292 lines) — 49-frame evaluation dataset, 100% recall
- **`cv-analyze-demos.py`** (181 lines) — unified best-quality analysis

### Swappable Engine Layers
- **`ocr_engines.py`** (304 lines) — `TesseractEngine` + `PaddleOCREngine`, factory via `OCR_BACKEND` env var
- **`ui_detectors.py`** (567 lines) — `ContourDetector` + `YOLOUIDetector` + `OmniParserDetector`, factory via `UI_DETECTOR` env var
- **Tuned for Wine desktop:** CLAHE, bilateral filter, multi-PSM, Canny thresholds, morphological closing, OmniParser weights (38.7MB cached)

### CV-Driven Control
- **`cv_wait "Notepad"`** — found in 1s (vs 3-6s hardcoded sleep)
- **`cv_wait "VLC"`** — found in 2s (vs 6s sleep)
- **`cv_verify_text`** — OCR PASSING via Tesseract sidecar
- **`cv_click`** — YOLO-detected coordinates
- **7 demos** upgraded with `cv_wait` replacing hardcoded sleeps

### Architecture: Sidecar
- **`Dockerfile.cv-analyzer`** — 4 build tiers (baseline, PaddleOCR, YOLO, OmniParser)
- **`docker-compose.yml`** — `winebot-cv` service on port 8001
- **`requirements-rel.txt`** — dropped opencv + pytesseract (~150MB pip savings)
- **Sidecar live-tested** with YOLO + Tesseract on port 8001

### Security
- **`winebot-credential.py`** (231 lines) — OS credential manager (Windows/macOS/Linux)
- **`winebotctl credential`** subcommand
- **`_demo_common.sh` `detect_token()`** — credential store fallback
- **keyring==25.6.0** added to requirements
- **3 personal paths** removed from source
- **`session.md`** with token deleted + gitignored
- Full audit: no tokens, passwords, keys, or emails in source

### Contracts Repo (winebot-contracts)
- `api/openapi.yaml` — 20+ endpoint specification
- `cli/winebotctl.md` — CLI command contract
- `cli/idempotency.md` — Idempotency contract (`X-Operation-Id`)
- `mcp/tools.json` — 14 MCP tool definitions
- `tests/conformance/run_conformance.py` — 15/15 tests pass
- `docs/architecture.md` — 7 principles, platform differences, rendering divergence
- `docs/compatibility.md` — versioning and deprecation rules
- `schemas/session.json` — session manifest schema

### Rendering Divergence — Documented in Both Repos
- WineBot Xvfb (no GPU) vs WinBot (native GPU) — architectural limitation
- Alpha Centauri: works with `DirectDraw=0` in `.ini`
- SuperTux: requires OpenGL 3.3, Xvfb has no GLX
- `gpu_available` field added to conformance tests

## What Didn't Work / Is Deferred

| Issue | Status |
|:---|:---|
| **Docker VM crashed** | Backend daemon offline — client returns 500. All containers/images lost. |
| **PaddleOCR build** | Deferred — `docker build --build-arg WITH_PADDLE=1` (~500MB, ~15 min) when Docker VM is stable |
| **OmniParser v2 build** | Deferred — `docker build --build-arg WITH_YOLO=1 --build-arg WITH_OMNIPARSER=1` (~2GB, ~25 min) when Docker VM is stable |
| **Comparative benchmarks** | Deferred — Tesseract vs PaddleOCR, Contour vs YOLO vs OmniParser on same frames |
| **SuperTux cv_wait** | Expected — OpenGL 3.3 required, Xvfb has no GPU. GDI renderer flag test pending. |
| **Notepad++ OCR** | Dark theme low contrast for Tesseract |
| **Installer file checks** | Wine 10.0 paths — not our code |

## CI Gates (All Verified Without Docker)

| Gate | Result |
|:---|:---|
| bash -n (13 scripts) | 13/13 pass |
| py_compile (15 tools) | 15/15 pass |
| Security audit | CLEAN |
| Repo sync | WineBot + Contracts both synced |
| Demo output | 10 videos on disk (from live run 2026-06-22) |

## New Files Created (This Session)

| File | Lines | Purpose |
|:---|:---|:---|
| `demo/scripts/_demo_common.sh` | 924 | 30 shared functions |
| `demo/scripts/demo-cv-control.sh` | 208 | CV-driven control demo |
| `scripts/diagnostics/cv-sidecar-server.py` | 470 | Sidecar API server |
| `scripts/diagnostics/cv-test-runner.py` | 618 | Frame extraction + analysis |
| `scripts/diagnostics/cv-batch-analyze.py` | 289 | CI batch gate |
| `scripts/diagnostics/merge-timeline.py` | 303 | 4-layer timeline |
| `scripts/diagnostics/demo-expect.py` | 226 | Assertion checker |
| `scripts/diagnostics/ocr_engines.py` | 304 | Swappable OCR |
| `scripts/diagnostics/ui_detectors.py` | 567 | Swappable UI detectors |
| `scripts/diagnostics/cv-eval-dataset.py` | 292 | Evaluation dataset |
| `scripts/diagnostics/cv-analyze-demos.py` | 181 | Best-quality analysis |
| `scripts/bin/winebot-credential.py` | 231 | OS credential manager |
| `models/yolo/omniparser_icon_detect.pt` | 38.7MB | OmniParser weights (cached) |

## When Docker VM Is Back

```bash
# 1. Rebuild sidecar with PaddleOCR
docker build --build-arg WITH_PADDLE=1 -f docker/Dockerfile.cv-analyzer -t winebot-cv:paddle .

# 2. Rebuild sidecar with YOLO + OmniParser
docker build --build-arg WITH_YOLO=1 --build-arg WITH_OMNIPARSER=1 \
  -f docker/Dockerfile.cv-analyzer -t winebot-cv:full .

# 3. Start WineBot + Sidecar, run all demos
docker run -d --name winebot-interactive -p 8000:8000 \
  -e MODE=interactive -e ENABLE_API=1 -e WINEBOT_RECORD=1 -e API_TOKEN=xxx \
  -v wineprefix:/wineprefix -v ./artifacts:/artifacts winebot:local-rel

docker run -d --name winebot-cv -p 8001:8001 \
  -e OCR_BACKEND=paddle -e UI_DETECTOR=yolo \
  -v ./artifacts:/artifacts -v ./models/yolo:/models:ro winebot-cv:full

export API_TOKEN=xxx WB_CONTAINER=winebot-interactive CV_SIDECAR_URL=http://localhost:8001
bash demo/scripts/input-pipeline-demo.sh  # verify everything works

# 4. Run comparative benchmarks (Task #81)
# Compare Tesseract vs PaddleOCR, Contour vs YOLO vs OmniParser on same frames
```

## GitHub Issues

| # | Title | Status |
|:---|:---|:---|
| 58-62 | Session-created issues | ✅ Closed |
| 54 | Input pipeline health endpoint | Open |
| 55 | Trace explorer dashboard | Open |
| 56 | Wine UIA support for pywinauto | Open |
| 57 | Add LICENSE file | Open |

## Next Steps (Priority Order)

1. **Fix Docker Desktop** — restart Docker VM, verify daemon responds
2. **Task #79** — build PaddleOCR sidecar, test OCR quality vs Tesseract
3. **Task #80** — build OmniParser full sidecar, test Florence-2 captions
4. **Task #81** — run comparative benchmarks, document results
5. **Task #78 follow-up** — test SuperTux with GDI renderer flag
6. **Open issues #54-57** — pipeline health, trace dashboard, UIA, license
7. **Transfer contracts repo** to SemperSupra org
8. **Run WinBot conformance** tests against WinBot API
