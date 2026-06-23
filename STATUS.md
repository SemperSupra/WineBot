# Status — 2026-06-23 (session closeout ~17:00 UTC)

## Current State

- **Version:** v0.9.7a release containers published on GHCR.
- **Handoff Point:** `main` at `a567399`, synced with `origin/main`.
- **Base Runtime:** `ghcr.io/sempersupra/winebot-base:base-2026-05-04`.
- **Contracts Repo:** [winebot-contracts](https://github.com/mark-e-deyoung/winebot-contracts) — 15/15 conformance tests pass.
- **API Token:** Stored in OS credential manager (`WINEBOT_API_TOKEN`).

## Session Summary — 2026-06-23 (afternoon)

### What Shipped

| Commit | What |
|:---|:---|
| `d145c64` | Bridge routing fix, per-request engine overrides, PaddleOCR v3 compat |
| `9b61d9f` | Session closeout docs |
| `e456acb` | GPU Dockerfile (`winebot-cv:gpu`) — nvidia/cuda 12.6.3 + RTX 3090 |
| `a567399` | Benchmark harness (dataset generator, runner, report) |

### CV/OCR Sidecar Images

| Image | Size | Base | Key Software | Status |
|:---|:---|:---|:---|:---|
| `winebot-cv:gpu` | 14 GB | nvidia/cuda:12.6.3 | PyTorch 2.12.1+cu130, YOLO 8.4.75, Transformers 5.12.1, Tesseract 5.3.4 | ✅ GPU verified |
| `winebot-cv:all` | 11.8 GB | python:3.12-slim | Same + PaddleOCR 3.7 (CPU, ONEDNN bugged) | ⚠️ Paddle blocked |
| `winebot-cv:full` | 10.1 GB | python:3.12-slim | YOLO + OmniParser (no Paddle) | ✅ |
| `winebot-cv:paddle` | 2.99 GB | python:3.12-slim | PaddleOCR only | ⚠️ ONEDNN bug |
| `winebot-cv:local` | 1.28 GB | python:3.12-slim | Tesseract baseline | ✅ |

### GPU Acceleration (RTX 3090)

- **Verified:** `torch.cuda.is_available() == True`, cuDNN enabled, 24 GB VRAM
- **YOLO GPU:** 450ms avg (2.3x faster than CPU 1045ms)
- **Contour CPU:** 394ms avg (unchanged)
- **Start command:** `docker run -d --gpus all --name winebot-cv -p 8001:8001 -e UI_DETECTOR=yolo -v ./models/yolo:/models:ro winebot-cv:gpu`

### Critical Fixes

1. **Bridge routing** — `_demo_common.sh` uses `172.17.0.1` (Docker bridge gateway) instead of `host.docker.internal` which routes through Docker Desktop VM proxy
2. **Per-request engine overrides** — `POST /analyze` accepts `ui_detector` and `ocr_backend` keys for comparative benchmarking without container restart
3. **PaddleOCR v3 API compat** — `use_gpu` removed, `cls=True` fallback, ONEDNN env vars set
4. **API token** — regenerated and stored in OS credential manager

### New Files This Session

| File | Lines | Purpose |
|:---|:---|:---|
| `docker/Dockerfile.cv-analyzer-gpu` | 87 | GPU sidecar (nvidia/cuda base) |
| `scripts/diagnostics/benchmark_dataset.py` | 380 | 6 synthetic UI images with ground truth |
| `scripts/diagnostics/benchmark_runner.py` | 384 | Multi-engine statistical harness (warmup, CI95, accuracy) |
| `scripts/diagnostics/benchmark_report.py` | 231 | Markdown report generator |

### Modified Files

| File | Change |
|:---|:---|
| `demo/scripts/_demo_common.sh` | Bridge routing fix |
| `scripts/diagnostics/cv-sidecar-server.py` | Per-request engine overrides |
| `scripts/diagnostics/ocr_engines.py` | PaddleOCR v3 compat |
| `docker/Dockerfile.cv-analyzer` | ONEDNN env vars |

## Deep Research Results

Researched 40+ models across 6 categories. Key recommendations:

### UI Detection — Top Candidates
1. **ScreenParser** (IBM/ETH, Apache 2.0) — YOLOv11-L, 55 widget classes, 1.45M screenshots
2. **UI-DETR-1** (racineai, MIT) — RF-DETR-M, class-agnostic, +20% WebClick vs OmniParser
3. **TinyClick** (Samsung, MIT) — 0.27B, 250ms, screenshot+instruction→click coordinates

### OCR — Top Candidates
1. **PaddleOCR ONNX** — export→ONNX bypasses ONEDNN bug, 30-50ms GPU
2. **Chandra OCR** (Datalab) — #1 speed (120ms/page), #1 accuracy (97.1%)
3. **Tesseract 5.5.2** — keep as CPU fallback

### Grounding — Top Candidates
1. **UI-TARS-1.5-7B** (ByteDance, Apache 2.0) — 94.2% ScreenSpot-v2, ~14GB
2. **GUI-Actor-7B** (Microsoft, MIT) — 92.5% ScreenSpot-v2, coordinate-free
3. **Moondream 2** (Apache 2.0) — 1.86B, <4GB, ONNX/C++

## What Worked

- Docker VM restart + all containers/images survived the crash
- GPU passthrough to Docker confirmed (RTX 3090 visible via `--gpus all`)
- All 4 sidecar image tiers built and verified
- Bridge routing fixed — sidecar captures 27-68 frames per demo session
- Per-request engine overrides allow swaps without restart
- Benchmark harness compiled and ready
- 3 demos verified end-to-end with MKV/GIF/VTT output

## What Didn't Work / Limitations

| Issue | Status | Fix Path |
|:---|:---|:---|
| **PaddleOCR ONEDNN bug** | Blocked | PaddlePaddle 3.4+ or ONNX export route |
| **PaddlePaddle GPU wheels** | Not on PyPI | Private Baidu index or self-build |
| **cv_wait on Wine 10.0** | xdotool window names empty | Rewrite via CV sidecar API |
| **Wine 10.0 installer failures** | Installers exit silently | Debug Wine paths/dependencies |
| **YOLO limited detection** | Only finds close button on Wine | Fine-tune on Wine screenshots |
| **OmniParser Florence-2** | Not yet GPU-tested | `.to("cuda")` in OmniParserDetector |

## CI Gates (All Pass)

| Gate | Result |
|:---|:---|
| bash -n (13 scripts) | 13/13 pass |
| py_compile (20 tools) | 20/20 pass |
| Docker GPU passthrough | Verified |
| Demo output | MKV/GIF/VTT on disk |

## Engine Backends — Not Yet Implemented (Deferred)

| Engine | Type | License | Effort | Priority |
|:---|:---|:---|:---|:---|
| `PaddleOCRONNXEngine` | OCR | Apache 2.0 | Add to ocr_engines.py + export models | 1 |
| `UIDETR1Detector` | UI Detection | MIT | Add to ui_detectors.py + rfdetr pip | 2 |
| `ScreenParserDetector` | UI Detection | Apache 2.0 | Add to ui_detectors.py (ultralytics native) | 3 |
| `/benchmark` endpoint | API | — | Add to cv-sidecar-server.py | 4 |

## Next Steps (Priority Order)

1. **Reboot host** — restart Docker Desktop
2. **Rebuild winebot-cv:gpu** with new packages (`rfdetr`, `onnxruntime-gpu`) — `docker build -f docker/Dockerfile.cv-analyzer-gpu -t winebot-cv:gpu .`
3. **Start containers** — WineBot interactive + CV sidecar GPU
4. **Implement engine backends** — PaddleOCRONNX, UIDETR1, ScreenParser
5. **Build /benchmark endpoint** — wire up the harness to the sidecar API
6. **Run full benchmark matrix** — 6 engine combos, 25 frames, 10 iterations
7. **Generate report** — commit results with statistical analysis
8. **cv_wait rewrite** — replace xdotool with CV sidecar API
9. **YOLO fine-tuning** on Wine desktop screenshots
10. **Open issues #54-57** — pipeline health, trace dashboard, UIA, license

## Quick Start (After Reboot)

```bash
# 1. Rebuild GPU sidecar with new engines
docker build -f docker/Dockerfile.cv-analyzer-gpu -t winebot-cv:gpu .

# 2. Start WineBot
$env:API_TOKEN = (python scripts/bin/winebot-credential.py get WINEBOT_API_TOKEN)
docker run -d --name winebot-interactive -p 8000:8000 \
  -e MODE=interactive -e ENABLE_API=1 -e API_TOKEN=$env:API_TOKEN \
  -v wineprefix:/wineprefix winebot:local-rel

# 3. Start CV Sidecar (GPU)
docker run -d --gpus all --name winebot-cv -p 8001:8001 \
  -e UI_DETECTOR=yolo -e OCR_BACKEND=tesseract \
  -v ./models/yolo:/models:ro winebot-cv:gpu

# 4. Generate benchmark dataset
python scripts/diagnostics/benchmark_dataset.py --output /tmp/bench_dataset

# 5. Run benchmarks (requires benchmark endpoint — see task 4 above)
# curl -X POST http://localhost:8001/benchmark -H "Content-Type: application/json" \
#   -d '{"frames_dir":"/bench_frames","engines":[...],"warmup_frames":3,"iterations":10}'

# 6. Run a demo
export API_TOKEN=$env:API_TOKEN WB_CONTAINER=winebot-interactive CV_SIDECAR_URL=http://localhost:8001
bash demo/scripts/demo-winebox.sh
```

## Docker Images on Disk

| Repository | Tag | Size | Keep? |
|:---|:---|:---|:---|
| `winebot-cv` | `gpu` | 14 GB | ✅ Primary GPU image |
| `winebot-cv` | `all` | 11.8 GB | ⚠️ CPU-only, superseded by gpu |
| `winebot-cv` | `full` | 10.1 GB | ❌ Remove |
| `winebot-cv` | `paddle` | 2.99 GB | ❌ Remove (blocked) |
| `winebot-cv` | `local` | 1.28 GB | ⚠️ Keep as minimal baseline |
| `winebot-cv` | `latest` | 9.91 GB | ❌ Remove |
| `winebot` | `local-rel` | 5.9 GB | ✅ Primary WineBot image |
