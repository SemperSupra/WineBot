# Status — 2026-06-24 (session closeout ~07:00 UTC)

## Current State

- **Handoff Point:** `main` at `afaf5d2`, synced with `origin/main`.
- **Base Runtime:** `ghcr.io/sempersupra/winebot-base:base-2026-05-04`.
- **Container Image:** `winebot-cv:gpu` (14 GB) — nvidia/cuda 12.6.3 + RTX 3090.
- **Contracts Repo:** [winebot-contracts](https://github.com/mark-e-deyoung/winebot-contracts) — 15/15 conformance tests pass.
- **API Token:** Stored in OS credential manager (`WINEBOT_API_TOKEN`).

---

## Session Summary — 2026-06-23/24 (two-part session)

### What Shipped (12 commits across two sessions)

| Commit | What |
|:---|:---|
| `afaf5d2` | Fix: disabled button bounds guard (generator bugfix) |
| `8bc6c77` | Feat: 12 new GT scenes, customs form workflow demo, cross-res benchmark |
| `6981d2b` | Feat: Wine v2 + corrected training + definitive benchmark |
| `758df72` | Fix: regenerate corrected dataset + definitive benchmark script |
| `b16de39` | Fix: notepad content lines labeled correctly, OCR gaps, gitignore |
| `5c4b92b` | Docs: comprehensive BUILD_LADDER — VLM research, all results |
| `a89632b` | Feat: Rungs 1-3 — YOLO26n, PP-OCRv6, generalized GT dataset |
| `df55c83` | Feat: WineUIDetector — fine-tuned production detector |
| `5814262` | Fix: GPU acceleration for all detectors + shared model cache |
| `0c88207` | Feat: 3 new engine backends + /benchmark endpoint |
| `d7ff331` | Perf: Tesseract FAST mode — 2.4× OCR speedup |

---

## Definitive Results

### Training Progression

| Model | mAP50 | mAP50-95 | Images | Scenes | Size | Status |
|:---|:---|:---|:---|:---|:---|:---|
| YOLOv8n Wine v1 | 0.993 | 0.912 | 1805 | 5 | 6.0 MB | ⚠️ Inflated (content = list_item bug) |
| YOLOv8n Wine v2 | 0.871 | 0.646 | 2000 | 11 | 6.0 MB | ✅ Honest baseline |
| **YOLOv8n Wine v3** | **0.918** | **0.689** | 3587 | **18** | 6.0 MB | 🏆 Production |
| **ScreenParser Wine** | **0.951** | **0.794** | 3587 | 18 | 49 MB | Best mAP, 55 classes |

### 5-Engine Benchmark (10 iters, 95% CI, Tesseract FAST, RTX 3090)

| Detector | Speed | FPS | Elements | Det_F1 | Notes |
|:---|:---|:---|:---|:---|:---|
| contour (CPU) | 219ms | 4.6 | 1 | 0.000 | CPU baseline |
| **wine v3** 🏆 | **221ms** | 4.5 | 10 | **0.667** | Best overall |
| yolo | 266ms | 3.8 | 7 | 0.400 | OmniParser 1-class |
| uidetr1 | 289ms | 3.5 | 36 | 0.125 | Most elements |
| screenparser | 304ms | 3.3 | 10 | 0.429 | 55 classes, no Wine training |

### OCR Comparison

| Engine | Speed | F1 | Notes |
|:---|:---|:---|:---|
| **Tesseract FAST** 🏆 | **283ms** | 0.923 | Production default |
| PP-OCRv6 tiny ONNX | 796ms | ~0.95 | 1.8+4.5MB |
| PP-OCRv6 small ONNX | 1066ms | ~0.95 | 10+21MB |
| Tesseract QUALITY | 600-700ms | 0.615 | 3-PSM, deprecated |

### Cross-Resolution Robustness (v3)

| Resolution | Element Ratio vs 1280×720 | Mean Confidence |
|:---|:---|:---|
| 1024×768 | 0.97× | 0.745 |
| 1280×720 | baseline | 0.764 |
| 1366×768 | 1.29× | 0.751 |
| 1440×900 | 0.95× | 0.697 |
| 1920×1080 | 1.05× | 0.680 |

No resolution drops below 0.95× element ratio. Robust generalization confirmed.

---

## Ground Truth Dataset

**Location:** `models/wine-dataset-gen/` on host (3.2 GB, 3,587 images + labels)
**Not in container. Not in git.** Regenerate anytime:
```bash
python3 winebot-gt-generator.py --output models/wine-dataset-gen --count 3600
```

### Scene Types (18)

| # | Scene | Category | Framework Test |
|:---|:---|:---|:---|
| 1 | save_dialog | Core dialog | File save workflow |
| 2 | settings | Core dialog | Preferences UI |
| 3 | error_dialog | Core dialog | Error handling |
| 4 | notepad | Core editor | Document editing |
| 5 | control_panel | Core data entry | Form fields |
| 6 | file_manager | Infrastructure | Tree + list + toolbar |
| 7 | multi_window | Infrastructure | 2-3 overlapping different frameworks |
| 8 | browser | Infrastructure | Tabs, address bar, bookmarks |
| 9 | terminal | Infrastructure | CLI prompt, command output |
| 10 | context_menu | Infrastructure | Right-click popup |
| 11 | wizard | Infrastructure | Multi-step with Back/Next |
| 12 | find_replace | Workflow dialog | Search/replace |
| 13 | print_dialog | Workflow dialog | Printer, copies, collate |
| 14 | about_dialog | Workflow dialog | Version, copyright |
| 15 | file_properties | Workflow dialog | Multi-tab, attributes |
| 16 | system_tray | Workflow notification | Popup above taskbar |
| 17 | installer | Workflow wizard | License, directory, progress |
| 18 | form_fill | Workflow form | PS 2976, I-9, W-4 dense forms |

### Augmentation Dimensions

8 UI framework themes (win32, win10, Qt, Gtk, Java, Tk, Electron, Win95)
× 5 resolutions (1024→1920)
× DPI scaling (1.0×, 1.25×, 1.5×, 1.75×)
× 5 OpenCV font faces with scale/thickness jitter
× Interaction states: cursor, caret, focus, tooltip, notification, modal, selection, disabled, validation
× HSV jitter ±40%, contrast ±30%, Gaussian noise σ=0.5-5.0

---

## CV/OCR Engine Inventory

### Detectors (6 registered backends)

| Backend | Type | Size | GPU | License | Status |
|:---|:---|:---|:---|:---|:---|
| `wine` | YOLOv8n (our training) | 6.0 MB | ✅ | — | 🏆 Production |
| `contour` | OpenCV heuristics | 0 | ❌ | — | CPU baseline |
| `yolo` | YOLOv8n (OmniParser) | 6.0 MB | ✅ | AGPL-3.0 | — |
| `screenparser` | YOLOv11-L (55 classes) | 49 MB | ✅ | Apache 2.0 | Best mAP if trained |
| `uidetr1` | RF-DETR-M (DINOv2) | 535 MB | ✅ | MIT | Most elements |
| `omniparser` | YOLO + Florence-2 | ~200 MB | ✅ | AGPL+MIT | Captions |

### OCR Engines (4 registered backends)

| Backend | Type | Size | Notes |
|:---|:---|:---|:---|
| `tesseract` | Tesseract 5.3.4 + pytesseract | 10 MB | Default, FAST=1 for speed |
| `paddle_onnx:tiny` | PP-OCRv6 ONNX | 6.3 MB | Auto-loaded if models present |
| `paddle_onnx:small` | PP-OCRv6 ONNX | 31 MB | Medium quality/speed |
| `paddle_onnx:medium` | PP-OCRv6 ONNX | 139 MB | Best quality |
| `paddleocr` | PaddleOCR 3.7 (PaddleX) | — | ⚠️ Blocked by ONEDNN bug |

---

## Shared Model Cache

**Location:** `~/.cache/winebot-models/` (survives container rebuilds)

| Path | Size | Source | License |
|:---|:---|:---|:---|
| `yolo/omniparser_icon_detect.pt` | 39 MB | Microsoft | AGPL-3.0 |
| `yolo/yolov8n.pt` | 6 MB | Ultralytics | AGPL-3.0 |
| `yolo/yolo26n.pt` | 6 MB | Ultralytics | AGPL-3.0 |
| `yolo/wine-finetuned-v3.pt` | 6 MB | WineBot (ours) | — |
| `yolo/screenparser-wine.pt` | 49 MB | WineBot (ours) | — |
| `uidetr1/model.pth` | 535 MB | racineai/UI-DETR-1 | MIT |
| `screenparser/best.pt` | 153 MB | docling-project/ScreenParser | Apache 2.0 |
| `ocr/ppocr_v6_tiny_det.onnx` | 1.8 MB | PaddlePaddle | Apache 2.0 |
| `ocr/ppocr_v6_tiny_rec.onnx` | 4.5 MB | PaddlePaddle | Apache 2.0 |
| `ocr/ppocr_v6_small_det.onnx` | 10 MB | PaddlePaddle | Apache 2.0 |
| `ocr/ppocr_v6_small_rec.onnx` | 21 MB | PaddlePaddle | Apache 2.0 |
| `ocr/ppocr_v6_med_det.onnx` | 62 MB | PaddlePaddle | Apache 2.0 |
| `ocr/ppocr_v6_med_rec.onnx` | 77 MB | PaddlePaddle | Apache 2.0 |

---

## What Worked

- **Programmatic GT generator** — 18 scene types produce infinite perfectly labeled data
- **8-framework theme system** — v3 detects Wine UI elements across Win32, Qt, Gtk, Java, Electron, Tk
- **Tesseract FAST mode** (`OCR_FAST=1`) — 283ms, 2.4× faster than QUALITY, better F1 (0.923 vs 0.615)
- **Dual simultaneous training** — YOLOv8n + ScreenParser on RTX 3090, ~23 min each
- **Cross-resolution robustness** — v3 maintains ≥0.95× element ratio from 1024→1920
- **Statistical rigor** — every benchmark uses 3-frame warmup, 10 iterations, t-distribution 95% CI
- **PP-OCRv6 ONNX** — all 3 size variants working with HF-pulled models
- **Shared model cache** — host-mounted, survives container rebuilds, 13 models

## What Didn't Work / Limitations

| Issue | Status | Mitigation |
|:---|:---|:---|
| PaddleOCR ONEDNN bug | Blocked | PP-OCRv6 ONNX bypasses it |
| YOLO26n vs YOLOv8n | v8 wins on mAP | Revisit with >5000 images |
| UI-DETR-1 detection F1 | 0.125 (low precision) | Needs Wine-specific fine-tuning |
| Container shared memory crash | Workers=2 needs `--shm-size=4g` | Added to Dockerfile instructions |
| `host.docker.internal` routing | Unreliable | Using `172.17.0.1` bridge gateway |
| PP-OCRv6 ONNX speed | 796ms+ vs Tesseract 283ms | Tesseract wins for production |
| ScreenParser Wine size | 49 MB (8× larger than v3) | Use v3 for edge, SP for quality |
| Content lines as list_item (v1 bug) | Inflated mAP | Fixed in v2/v3 — content is OCR-only |
| cv_wait (xdotool) on Wine 10.0 | Empty X11 window names | Deferred: rewrite via CV sidecar |

---

## VLM Research (Deferred)

### Best Models for Local Hardware

| Hardware | Model | ScreenSpot Pro | VRAM (INT4) |
|:---|:---|:---|:---|
| RTX 3090 24GB | Qwen3.5-27B | 0.703 (#7 open) | ~18 GB |
| RTX 3090 24GB | Qwen3 VL 30B-A3B MoE | 0.605 (#13) | ~16 GB |
| RTX 3090 24GB | KV-Ground-8B (GUI specialist) | 73.2% v2 | ~6 GB |
| TrueNAS 2×A5000 48GB | Qwen3.5-122B-A10B MoE | 0.704 (#6) | ~48 GB |

### Publication Venues

| Venue | Deadline | Best For |
|:---|:---|:---|
| ICDAR 2026 | Feb 27, 2026 (passed) | OCR + document analysis |
| NeurIPS 2026 E&D | May 6, 2026 (passed) | Dataset + benchmark |
| JOSS / SoftwareX | Rolling | Generator + benchmark tools |
| CVPR 2027 | ~Nov 2026 | Full pipeline paper |
| ICLR 2027 | ~Sep 2026 | Synthetic data for detection |

All venues allow AI-assisted research with disclosure. None allow AI as co-author.

---

## Next Steps (Priority Order)

1. **Integrate ScreenParser Wine** as optional high-quality backend in ui_detectors.py
2. **Build workflow sequence evaluator** — track state transitions across video frames
3. **Test on real Wine desktop screenshots** — validate synthetic→real transfer
4. **VLM integration** — deploy KV-Ground-8B on RTX 3090 as complementary path
5. **Generate 10,000-image dataset** — scale up for publication-quality results
6. **Write JOSS/SoftwareX paper** — peer-review the generator + benchmark tools
7. **Prepare CVPR 2027 submission** — full pipeline with VLM comparison
8. **cv_wait rewrite** — CV sidecar-based window detection (replaces xdotool)

---

## Quick Start

```bash
# Rebuild GPU sidecar
docker build -f docker/Dockerfile.cv-analyzer-gpu -t winebot-cv:gpu .

# Start with shared model cache
docker run -d --gpus all --shm-size=4g --name winebot-cv -p 8001:8001 \
  -e UI_DETECTOR=wine -e OCR_BACKEND=tesseract -e OCR_FAST=1 \
  -v ~/.cache/winebot-models:/models \
  -v ./models/wine-dataset-gen:/models/wine-dataset-gen \
  winebot-cv:gpu

# Run benchmark
docker exec winebot-cv sh -c "
  python3 /scripts/benchmark_dataset.py --output /tmp/bench_dataset > /dev/null
  python3 /scripts/benchmark_runner.py \
    --frames /tmp/bench_dataset \
    --engine 'wine:tesseract' \
    --warmup 3 --iterations 10 --output /tmp/results.json
"

# Train new model
docker exec winebot-cv python3 /scripts/winebot-gt-generator.py \
  --output /models/wine-dataset-gen --count 5000
docker exec winebot-cv python3 /scripts/fine_tune_detector.py \
  --data /models/wine-dataset-gen/data.yaml \
  --model /models/yolo/yolov8n.pt --epochs 30

# Run customs form workflow demo
export WB_CONTAINER=winebot-interactive CV_SIDECAR_URL=http://localhost:8001
export API_TOKEN=$(python scripts/bin/winebot-credential.py get WINEBOT_API_TOKEN)
bash demo/scripts/demo-customs-form.sh
```
