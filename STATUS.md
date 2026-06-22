# Status — 2026-06-22

## Current State

- **Version:** v0.9.7a release containers published on GHCR.
- **Status:** Demo infrastructure + CV/OCR pipeline + sidecar + contracts — all verified live. 10/10 demos pass.
- **Handoff Point:** `main` at `9e91e29`, synced with `origin/main`.
- **Base Runtime:** `ghcr.io/sempersupra/winebot-base:base-2026-05-04`.
- **Sidecar:** `winebot-cv:latest` (1.28GB base, 3.35GB w/YOLO) — OpenCV + Tesseract + YOLOv8 + OmniParser weights, port 8001.
- **Contracts Repo:** [winebot-contracts](https://github.com/mark-e-deyoung/winebot-contracts) — API spec, CLI contract, MCP tools, conformance tests (15/15 pass).

## What Worked

### Demo Infrastructure
- **`_demo_common.sh`** — 30 shared functions, all 10 demos source it
- **`demo-cv-control.sh`** — CV-driven control with OCR verification
- **Desktop cleanup** — `fresh_session()` kills app windows + restarts recording between demos
- **Download cache** — Python `linux_dl()` caches to `.winebot_cache/`, ~1.6MB saved per download
- **Video output** — Auto-copied to `demo/output/<name>.mkv/.gif/.vtt` via `stop_recording()`
- **Session segments** — `smart_trim()` uses `ls -t` for latest video segment
- **AHK pipe dialog** — `pipe_cmd "open_gui"` replaces Ctrl+S (no Wine dialogs triggered)

### CV/OCR Pipeline
- **Sidecar operational** — `/health`, `/analyze`, `/batch`, `/watch/start`, `/watch/stop`
- **Swappable backends** — `UI_DETECTOR=contour|yolo|omniparser`, `OCR_BACKEND=tesseract|paddle`
- **OmniParser YOLO** — 38.7MB icon_detect weights, 11.0 UI elements/frame avg
- **Tesseract OCR** — CLAHE + bilateral filter + multi-PSM (6,11,3) + confidence 40
- **CV watcher** — 31-35 frames/demo via sidecar `/watch/start` at 1fps
- **Batch analysis** — `cv-batch-analyze.py --exit-on-warnings`, CI gate PASS
- **Timeline merger** — `merge-timeline.py`, 42 sessions merged
- **Expected-state assertions** — `demo-expect.py`, PASS/FAIL/checkpoint
- **Evaluation dataset** — 49 frames, 100% element/OCR recall

### CV-Driven Control
- **`cv_wait "Notepad"`** — found in 1s (vs 3-6s sleep)
- **`cv_verify_text`** — OCR PASSING via Tesseract
- **`cv_click`** — YOLO-detected coordinates
- **7 demos** upgraded with `cv_wait` replacing hardcoded sleeps

### Architecture
- **Sidecar** — unified CV/OCR container, 4 build tiers
- **docker-compose.yml** — `winebot-cv` service on port 8001
- **`requirements-rel.txt`** — dropped opencv + pytesseract (~150MB pip savings)
- **25/25 diagnostic scripts** tagged with `EXECUTION:` + `STATUS:`
- **OS credential manager** — `winebot-credential.py`, keyring integration, `winebotctl credential`

### All 10 Demos — Live Verified (2026-06-22)

| Demo | Status | Output Size | Cache |
|:---|:---|:---|:---|
| `input-pipeline-demo` | PASS | 9.0KB | — |
| `demo-ci-pipeline` | PASS | 11.4KB | — |
| `demo-cv-control` | PASS | 8.5KB | — |
| `demo-7zip` | PASS | 8.7KB | cache hit |
| `demo-winebox` | PASS | 9.0KB | cache hit |
| `demo-installer-qa` | PASS | 8.7KB | cache hit |
| `hook-demo` | PASS | 9.3KB | — |
| `demo-notepadpp` | PASS | 10.0KB | downloaded |
| `demo-vlc` | PASS | 9.0KB | downloaded |
| `demo-supertux` | PASS | 8.8KB | downloaded |

## What Didn't Work / Needs Attention

| Issue | Impact | Mitigation |
|:---|:---|:---|
| **Supertux cv_wait times out** | Game needs GPU rendering for window detection | `cv_wait` falls back to `sleep 8` |
| **Notepad++ OCR poor** | Dark theme produces low-contrast text for Tesseract | Invert colors or use PaddleOCR |
| **Installer file checks** | Wine 10.0 installer paths don't match expected | Known Wine limitation, not our code |
| **YOLO in Docker** | `pip install ultralytics` fails on `--index-url` (fixed with `--extra-index-url`) | Builds with `WITH_YOLO=1` |
| **PaddleOCR not tested** | Not installed in container | `WITH_PADDLE=1` build arg available |
| **OmniParser Florence-2** | Needs GPU, adds 2GB | `WITH_OMNIPARSER=1` build arg available |
| **Sidecar `urllib` needs `host.docker.internal`** | Docker Desktop DNS quirk | `fresh_session` translates `localhost` to `host.docker.internal` |
| **CV watcher @ 1fps** | Misses fast dialog transitions | Acceptable — raise fps if needed |

## CI Gates

| Gate | Status |
|:---|:---|
| bash -n (all scripts) | 12/12 pass |
| py_compile (all tools) | 14/14 pass |
| cv-batch-analyze --exit-on-warnings | 10/10 clean, 98 frames, 0 warnings |
| eval dataset recall | 100% element, 100% OCR |
| conformance tests | 15/15 pass |
| security audit | CLEAN — no paths, no tokens, no credentials in source |

## GitHub Issues

| # | Title | Status |
|:---|:---|:---|
| 58 | CV watcher sidecar integration | ✅ Closed |
| 59 | /recording/health endpoint | ✅ Closed |
| 60 | E2E CV analysis CI gate | ✅ Closed |
| 61 | Diagnostic script cleanup | ✅ Closed |
| 62 | Main sidecar architecture | ✅ Closed |
| 54 | Input pipeline health endpoint | Open |
| 55 | Trace explorer dashboard | Open |
| 56 | Wine UIA support for pywinauto | Open |
| 57 | Add LICENSE file | Open |

## Memory Files Written

- `memory/demo-refactoring.md` — Shared library + 9 demos refactored
- `memory/cv-ocr-pipeline.md` — CV/OCR built and tested
- `memory/game-ui-automation.md` — Alpha Centauri strategy for reverse-smac
- `memory/security-credential-manager.md` — Security audit + OS credential store

## Sidecar Build Commands

```bash
# Baseline (OpenCV + Tesseract)
docker build -f docker/Dockerfile.cv-analyzer -t winebot-cv .

# Full (YOLOv8 + OmniParser)
docker build -f docker/Dockerfile.cv-analyzer -t winebot-cv --build-arg WITH_YOLO=1 .

# With PaddleOCR
docker build -f docker/Dockerfile.cv-analyzer -t winebot-cv --build-arg WITH_PADDLE=1 .

# Everything
docker build -f docker/Dockerfile.cv-analyzer -t winebot-cv --build-arg WITH_YOLO=1 --build-arg WITH_PADDLE=1 --build-arg WITH_OMNIPARSER=1 .
```

## Demo Quick Start

```bash
# Start WineBot + Sidecar
docker run -d --name winebot-interactive -p 8000:8000 \
  -e MODE=interactive -e ENABLE_API=1 -e API_TOKEN=xxx \
  -e WINEBOT_RECORD=1 \
  -v wineprefix:/wineprefix \
  winebot:local-rel

docker run -d --name winebot-cv -p 8001:8001 \
  -e UI_DETECTOR=yolo -e OCR_BACKEND=tesseract \
  -v ./models/yolo:/models:ro \
  -v ./artifacts:/artifacts \
  winebot-cv:latest

# Run all demos
export API_TOKEN=xxx WB_CONTAINER=winebot-interactive CV_SIDECAR_URL=http://localhost:8001
for d in demo/scripts/demo-*.sh demo/scripts/input-pipeline-demo.sh demo/scripts/hook-demo.sh; do bash "$d"; done

# Analyze results
python scripts/diagnostics/cv-batch-analyze.py --input demo/output/ --exit-on-warnings
python scripts/diagnostics/merge-timeline.py --session-dir artifacts/sessions/<latest>
python scripts/diagnostics/demo-expect.py --session-dir artifacts/sessions/<latest>
```

## Next Steps

1. **Open issues #54-57** — Pipeline health, trace dashboard, UIA support, license
2. **Reverse-smac project** — Apply WineBot CV infrastructure to Alpha Centauri automation
3. **PaddleOCR testing** — Build with `WITH_PADDLE=1`, compare OCR quality vs Tesseract
4. **OmniParser functional captions** — Build with `WITH_OMNIPARSER=1`, test Florence-2
5. **Transfer contracts repo** to SemperSupra org for shared ownership
6. **WinBot conformance** — Run contracts conformance tests against WinBot
7. **Session retention** — Clean old sessions from `artifacts/sessions/` (66 sessions)
