# Status — 2026-06-23

## Current State

- **Version:** v0.9.7a release containers published on GHCR.
- **Status:** Demo infrastructure complete, CV/OCR sidecar operational, contracts repo live. PaddleOCR and OmniParser builds pending.
- **Handoff Point:** `main` at `37b6095`, synced with `origin/main`.
- **Base Runtime:** `ghcr.io/sempersupra/winebot-base:base-2026-05-04`.
- **Sidecar:** `winebot-cv:latest` (1.28GB baseline Tesseract) — YOLOv8 + PaddleOCR + OmniParser builds in progress.
- **Contracts Repo:** [winebot-contracts](https://github.com/mark-e-deyoung/winebot-contracts) — 15/15 conformance tests pass.

## Completed (Since Last Handoff)

### Session Closeout
- **STATUS.md** — full handoff with build commands, quick start, next steps
- **Archive** — `archive/status/STATUS-2026-06-22.md`
- **Memory** — `session-closeout-2026-06-22.md`
- Both repos synced and pushed

### 3D Rendering Divergence — Documented
- **`docs/known-limitations.md`** — Xvfb constraints expanded (60 lines), game compatibility matrix, SuperTux failure analysis, Alpha Centauri workaround (`DirectDraw=0`), LLVMpipe/virgl/GPU-passthrough options
- **`contracts/docs/architecture.md`** — 14-row platform differences table, rendering divergence section
- **`contracts/tests/conformance/`** — `gpu_available` field check
- **`STATUS.md`** — WineBot vs WinBot rendering section with compatibility matrix
- Both repos committed and pushed

### PaddleOCR + OmniParser Builds — Initiated
- Both Docker builds started as background processes
- Need Docker Desktop running to complete
- Expected artifacts: `winebot-cv:paddle` and `winebot-cv:full` images

## What Still Needs Running

### 1. Verify Docker Desktop is Running
```bash
docker info 2>&1 | head -3
```
If it failed overnight, restart and verify containers:
```bash
docker ps --filter "name=winebot"
```

### 2. Complete PaddleOCR Build
```bash
docker build -f docker/Dockerfile.cv-analyzer -t winebot-cv:paddle \
  --build-arg WITH_PADDLE=1 .
```
~500MB download, 10-20 minutes. Check with `docker images winebot-cv:paddle`.

### 3. Complete OmniParser Build
```bash
docker build -f docker/Dockerfile.cv-analyzer -t winebot-cv:full \
  --build-arg WITH_YOLO=1 --build-arg WITH_OMNIPARSER=1 .
```
~2GB download, 20-40 minutes. Check with `docker images winebot-cv:full`.

### 4. Run Comparative Benchmarks (Task #81)
Once both images exist:
```bash
# Start sidecar with PaddleOCR
docker rm -f winebot-cv 2>/dev/null
docker run -d --name winebot-cv -p 8001:8001 \
  -e OCR_BACKEND=paddle \
  -v ./artifacts:/artifacts -v ./demo/output:/demo-output:ro \
  winebot-cv:paddle

# Test both OCR backends on same frame
FRAME="/demo-output/analysis/core-pipeline/frames/frame_0040.png"
curl -s -X POST http://localhost:8001/analyze -d "{\"image_path\":\"$FRAME\"}" | \
  python3 -c "import sys,json; d=json.load(sys.stdin); print(f'OCR: {d[\"ocr_regions\"]} regions')"

# Record results, then restart with full image for OmniParser test
# Compare: Tesseract vs PaddleOCR (OCR quality, regions found, text accuracy)
# Compare: Contour vs YOLO vs OmniParser (UI elements detected, types, confidence)
```

### 5. Run SuperTux with Direct3D GDI Renderer (Task #78 follow-up)
```bash
docker exec winebot-interactive sh -c "
  wine reg add 'HKCU\\Software\\Wine\\Direct3D' /v renderer /t REG_SZ /d gdi /f
"
```
Then re-run `demo-supertux.sh` and check if `cv_wait` succeeds.

### 6. Test Game Compatibility
- **Alpha Centauri:** Expected to work with `DirectDraw=0` in `.ini`. Download SMAC, configure, launch via `/apps/run`, test `cv_wait` for menu screens.
- **Document results** in `docs/known-limitations.md` §22 game table.

## All CI Gates

| Gate | Status |
|:---|:---|
| bash -n (all scripts) | 12/12 pass |
| py_compile (all tools) | 14/14 pass |
| cv-batch-analyze --exit-on-warnings | 10/10 clean |
| conformance tests | 15/15 pass |
| security audit | CLEAN |

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
