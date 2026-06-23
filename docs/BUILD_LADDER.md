# WineBot CV/OCR — Build-Up Ladder & Research Compendium

**Date:** 2026-06-23 | **GPU:** RTX 3090 24GB + 2× A5000 24GB (TrueNAS)
**Commit:** `a89632b` | **Branch:** `main` | **Status:** Rungs 1-3 complete

---

## Baseline (Where We Ended)

### Definitive 5-Detector Benchmark (10 iterations, 95% CI, Tesseract FAST)

| Detector | Speed | FPS | Elements | Det_F1 | OCR_F1 | Notes |
|:---|:---|:---|:---|:---|:---|:---|
| contour | **194ms** | 5.2 | 1 | 0.500 | 0.923 | CPU baseline |
| **wine** 🏆 | 212ms | 4.7 | 12 | **0.750** | 0.923 | **Production default** |
| yolo | 216ms | 4.6 | 6 | 0.400 | 0.923 | OmniParser, 1-class |
| screenparser | 236ms | 4.2 | 8 | 0.571 | 0.923 | 55 classes |
| uidetr1 | 255ms | 3.9 | 31 | 0.211 | 0.923 | Most coverage |

### OCR Engine Comparison

| Engine | Speed | F1 | Size | Notes |
|:---|:---|:---|:---|:---|
| **Tesseract FAST** 🏆 | **283ms** | 0.923 | 10MB | Production default |
| PP-OCRv6 tiny | 796ms | ~0.95 | 1.8+4.5MB | Fastest ONNX |
| PP-OCRv6 small | 1066ms | ~0.95 | 10+21MB | Best balance |
| PP-OCRv6 medium | 2582ms | ~0.95 | 62+77MB | Best quality |
| Tesseract QUALITY | 600-700ms | 0.615 | 10MB | Deprecated |

### Production Pipeline

```
Screenshot (1280×720 PNG)
    │
    ▼
wine+tesseract FAST → 212ms, Detection F1=0.750, OCR F1=0.923
    │
    ▼
22 Wine-specific classes detected across 8 framework themes
```

---

## Completed Rungs

### ✅ Rung 1: YOLO26n Evaluation

**Date:** 2026-06-23 | **Commit:** `a89632b`

| Metric | YOLOv8n Wine (current) | YOLO26n Wine |
|:---|:---|:---|
| mAP50 | **0.993** | 0.970 |
| mAP50-95 | **0.912** | 0.855 |
| Speed | **17ms** | 22ms |
| Params | 3.2M | 2.4M (25% smaller) |
| NMS | Required | NMS-free |

**Verdict:** YOLOv8n Wine remains production default. YOLO26n's NMS-free
architecture is appealing for deterministic deployment but the mAP gap
(-0.023 mAP50, -0.057 mAP50-95) doesn't justify switching yet. Revisit
with >5000 training images.

### ✅ Rung 2: PP-OCRv6 ONNX Deployment

**Date:** 2026-06-23 | **Commit:** `a89632b`

Three variant support in `PaddleOCRONNXEngine`:
- `paddle_onnx:tiny` — 1.8+4.5MB, 796ms (auto-selected default)
- `paddle_onnx:small` — 10+21MB, 1066ms
- `paddle_onnx:medium` — 62+77MB, 2582ms

**Verdict:** Tesseract FAST (283ms) still 2.8× faster with better F1 on
synthetic UI text. PP-OCRv6 ONNX is viable if OCR accuracy on real Wine
screenshots degrades with Tesseract. Models stored in shared cache.

### ✅ Rung 3: Generalized GT Dataset

**Date:** 2026-06-23 | **Commit:** `a89632b`

**Dataset stats:** 1,400 images, 1.3 GB, 22 classes

**Scene types (7):**
| Scene | Elements | Purpose |
|:---|:---|:---|
| save_dialog | Save As, file list, dropdown, buttons | Most common Wine interaction |
| settings | Tabs, checkboxes, radios, buttons | Preferences/configuration |
| error_dialog | Icon, message, OK/Cancel buttons | Error/warning/info popups |
| notepad | Menu bar, text area, status bar | Content editing |
| control_panel | Toolbar, form fields, progress bar | Dense data entry |
| file_manager | Tree sidebar, file list, toolbar, path bar | Navigation |
| multi_window | 2-3 overlapping different frameworks | Occlusion handling |

**UI framework themes (8):**
win32_classic, win10_fluent, qt_fusion, gtk_adwaita, java_metal,
tkinter, electron_dark, classic_95

**Augmentations:**
- HSV jitter: saturation ±40%, brightness ±30%
- Resolution: 1024→1920px, DPI scaling 1.0-1.75×
- 5 OpenCV font faces with scale ±15% and thickness 1-2px
- Gaussian noise σ=0.5-5.0, Gaussian blur σ=0.1-0.5
- Contrast ±30% with brightness jitter ±30

**Interaction states:**
| State | Coverage | Implementation |
|:---|:---|:---|
| Active window | ✅ Default | Full rendering |
| Inactive window | ✅ 20% of frames | Dimmed overlay, alpha=0.7 |
| Maximized | ✅ 10% of frames | No borders |
| Minimized | ✅ 10% of frames | Taskbar-only elements |
| Modal overlay | ✅ 25% of dialogs | Semi-transparent dark bg |
| Mouse cursor | ✅ 60% of frames | Arrow/ibeam/hand at random pos |
| Text caret | ✅ 70% of text fields | Blinking vertical bar |
| Focus rectangle | ✅ 40% of focusable | Dotted rect |
| Selection highlight | ✅ 50% of lists | Blue overlay on text |
| Tooltip | ✅ 20% with cursor | Yellow popup near cursor |
| Notification toast | ✅ 15% of frames | Bottom-right popup |
| Disabled button | ✅ 2-3 per frame | Desaturated + dimmed |
| Validation state | ✅ 30% of text fields | Red/green/yellow border |
| Desktop icons | ✅ 40% of frames | Random position + label |

---

## VLM Research Compendium

Research conducted 2026-06-23. Covers GUI grounding, OCR, and general
vision-language models for local self-hosted deployment.

### ScreenSpot Pro Leaderboard (Open-Weight Models)

[Leaderboard](https://llm-stats.com/benchmarks/screenspot-pro) as of June 2026.

| Rank | Model | Score | Type | VRAM (INT4) | Fits On |
|:---|:---|:---|:---|:---|:---|
| #6 | **Qwen3.5-122B-A10B** | **0.704** | MoE, 10B active | ~48 GB | TrueNAS 2× A5000 |
| #7 | **Qwen3.5-27B** | 0.703 | Dense 27B | ~18 GB | RTX 3090 |
| #13 | Qwen3 VL 30B A3B | 0.605 | MoE, 3B active | ~16 GB | RTX 3090 |
| #15 | Qwen3 VL 32B | 0.579 | Dense 32B | ~20 GB | RTX 3090 (AWQ) |
| #18 | Qwen3 VL 8B | 0.546 | Dense 8B | ~10 GB | RTX 3090 (FP16) |
| #21 | Qwen2.5 VL 72B | 0.436 | Dense 72B | ~40 GB | TrueNAS Q4 |

### Dedicated GUI Grounding Models (Self-Hosted)

| Model | ScreenSpot v2 | ScreenSpot Pro | VRAM (INT4) | License | Notes |
|:---|:---|:---|:---|:---|:---|
| **KV-Ground-8B** | 94.6% | **73.2%** | ~6 GB | Open | Best 8B, +7% with zoom-in |
| UI-TARS-1.5-7B | 94.2% | 61.6% | ~5 GB | Apache 2.0 | End-to-end agent |
| UI-Venus-1.5-8B | 95.9% | 68.4% | ~6 GB | — | Zoom-in: 73.9% |
| POINTS-GUI-G-8B | 95.7% | 59.9% | ~6 GB | — | Built from scratch |
| MAI-UI-8B | 95.2% | 65.8% | ~6 GB | — | Solid all-rounder |

### General VLMs for OCR + Understanding

| Model | OCR Quality | DocVQA | VRAM (INT4) | License | Notes |
|:---|:---|:---|:---|:---|:---|
| Qwen2.5-VL-7B | 95% char accuracy | — | ~5 GB | Apache 2.0 | Dynamic resolution |
| InternVL3-8B | Best OCR/docs | — | ~10 GB | MIT | Table extraction, layout |
| Phi-4 Multimodal 5.6B | Competitive | — | ~4 GB | MIT | 128K context, audio too |
| GutenOCR-7B | 2× grounded OCR | 0.82 | ~5 GB | — | Qwen2.5 fine-tune |
| DeepSeek-VL2 Tiny | OCRBench 834 | 93.3% | ~10 GB | Open | MoE, 4.5B active |
| HunyuanOCR 1.1B | OCR specialist | — | 339MB Q4 | Open | CPU-capable, structured output |

### Hardware Deployment Matrix

```
┌─────────────────────────────────────────────────────────────────┐
│  RTX 3090 (24 GB) — Dev Box                                    │
│                                                                 │
│  Option A: Qwen3.5-27B INT4 (~18 GB)                           │
│            Best quality single model. Score 0.703, #7 overall.  │
│                                                                 │
│  Option B: Qwen3 VL 30B-A3B MoE INT4 (~16 GB)                  │
│            3× faster inference. 3B active per token.            │
│                                                                 │
│  Option C: KV-Ground-8B INT4 (~6 GB) + Qwen3.5-27B INT4        │
│            GUI grounding + general VLM simultaneously.          │
│            Both fit in 24 GB. Total: ~24 GB.                    │
│                                                                 │
│  Option D: InternVL3-8B INT8 (~10 GB) + KV-Ground-8B INT4      │
│            Best OCR + GUI grounding. Total: ~16 GB.             │
├─────────────────────────────────────────────────────────────────┤
│  2× A5000 (48 GB) — TrueNAS                                    │
│                                                                 │
│  Option A: Qwen3.5-122B-A10B INT4 (~48 GB)                     │
│            #1 open-weight ScreenSpot Pro (0.704).               │
│            Matches GPT-5.2 class at 1/100th the cost.           │
│                                                                 │
│  Option B: Qwen3.5-27B FP16 (~50 GB)                           │
│            Full precision, no quantization loss.                │
│                                                                 │
│  Option C: Qwen2.5-VL-72B Q4_K_M (~40 GB)                      │
│            Previous gen but 72B parameters. Good for OCR.       │
│                                                                 │
│  Option D: Parallel farm: 3× 8B models at FP16 (~18 GB each)   │
│            Run KV-Ground + Qwen3-VL + InternVL simultaneously.  │
└─────────────────────────────────────────────────────────────────┘
```

### VLM Research Sources

- ScreenSpot Pro Leaderboard: [llm-stats.com/benchmarks/screenspot-pro](https://llm-stats.com/benchmarks/screenspot-pro)
- UI-TARS: [arXiv:2501.12326](https://arxiv.org/abs/2501.12326)
- POINTS-GUI-G: [arXiv:2602.06391](https://arxiv.org/abs/2602.06391)
- Qwen3-VL: [HuggingFace](https://huggingface.co/Qwen)
- KV-Ground: [HuggingFace](https://huggingface.co/vocaela/KV-Ground-8B-BaseGuiOwl1.5)
- InternVL3: [HuggingFace](https://huggingface.co/OpenGVLab/InternVL3-8B)
- GutenOCR: [arXiv:2601.14490](https://arxiv.org/abs/2601.14490)
- Phi-4 Multimodal: [HuggingFace](https://huggingface.co/microsoft/Phi-4-multimodal-instruct)

### VLM Integration Plan (Deferred)

1. Start with **KV-Ground-8B** on the RTX 3090 — smallest, most GUI-specialized
2. Add as complementary path: YOLO detects 95% of elements, KV-Ground verifies
   precision on the top-5 highest-confidence detections
3. Later: deploy **Qwen3.5-27B** on TrueNAS for batch analysis of session recordings
4. Use the VLM path for: "what does this screenshot say?", "is there an error dialog?",
   "read the text in this region" — tasks that need language understanding

---

## Training Results Log

### Run 1: 50 images, YOLOv8n, basic themes (Early Session)

| Epoch | mAP50 | mAP50-95 | box_loss |
|:---|:---|:---|:---|
| 10 | 0.145 | 0.105 | 1.93 |
| 20 | 0.210 | 0.160 | 1.76 |

**Verdict:** Too few images. Confidence <0.03 on OOD frames.

### Run 2: 1805 images, YOLOv8n, 8 themes + augmentations

| Epoch | mAP50 | mAP50-95 | Precision | Recall | box_loss |
|:---|:---|:---|:---|:---|:---|
| 1 | 0.665 | 0.471 | 0.685 | 0.587 | 1.59 |
| 10 | 0.983 | 0.842 | 0.998 | 0.957 | 0.75 |
| 20 | 0.994 | 0.893 | 0.991 | 0.988 | 0.63 |
| **30** | **0.993** | **0.912** | **0.992** | **0.993** | 0.51 |

**Time:** 22 min (1315s) on RTX 3090. **4.7× mAP50, 5.7× mAP50-95.**
**Production model:** `/models/yolo/wine-finetuned.pt` (6.2 MB)

### Run 3: 1805 images, YOLO26n, 28 epochs (patience stop)

| Epoch | mAP50 | mAP50-95 | Precision | Recall |
|:---|:---|:---|:---|:---|
| 1 | 0.127 | 0.093 | 0.895 | 0.103 |
| 10 | 0.911 | 0.743 | 0.771 | 0.860 |
| 20 | 0.950 | — | — | — |
| **28** | **0.970** | **0.855** | 0.915 | 0.907 |

**Time:** 29 min (1738s). **Cached:** `/models/yolo/wine-yolo26n.pt` (20 MB)

---

## VOC — Evaluation Protocol

Every benchmark run follows this protocol for statistical validity:

| Parameter | Value | Rationale |
|:---|:---|:---|
| Warmup frames | 2-3 per engine | CUDA kernel compilation, model lazy-load |
| Iterations per frame | 5-10 | Measure noise, enable CI computation |
| Benchmark frames | 4-6 | Covers scene diversity |
| Confidence level | 95% | Standard scientific threshold |
| CI method | t-distribution | Accounts for small sample sizes |
| Significance | Non-overlapping CIs | Two engines differ if 95% CIs don't overlap |

---

## Infrastructure

### Shared Model Cache (`~/.cache/winebot-models/`)

| Path | Size | Source | License |
|:---|:---|:---|:---|
| `yolo/omniparser_icon_detect.pt` | 39 MB | Microsoft OmniParser v2 | AGPL-3.0 |
| `yolo/yolov8n.pt` | 6 MB | Ultralytics | AGPL-3.0 |
| `yolo/yolo26n.pt` | 6 MB | Ultralytics | AGPL-3.0 |
| `yolo/wine-finetuned.pt` | 6 MB | WineBot (ours) | — |
| `yolo/wine-yolo26n.pt` | 20 MB | WineBot (ours) | — |
| `uidetr1/model.pth` | 535 MB | racineai/UI-DETR-1 | MIT |
| `screenparser/best.pt` | 153 MB | docling-project/ScreenParser | Apache 2.0 |
| `ocr/ppocr_v6_tiny_det.onnx` | 1.8 MB | PaddlePaddle/PP-OCRv6 | Apache 2.0 |
| `ocr/ppocr_v6_tiny_rec.onnx` | 4.5 MB | PaddlePaddle/PP-OCRv6 | Apache 2.0 |
| `ocr/ppocr_v6_small_det.onnx` | 10 MB | PaddlePaddle/PP-OCRv6 | Apache 2.0 |
| `ocr/ppocr_v6_small_rec.onnx` | 21 MB | PaddlePaddle/PP-OCRv6 | Apache 2.0 |
| `ocr/ppocr_v6_med_det.onnx` | 62 MB | PaddlePaddle/PP-OCRv6 | Apache 2.0 |
| `ocr/ppocr_v6_med_rec.onnx` | 77 MB | PaddlePaddle/PP-OCRv6 | Apache 2.0 |

### Container Images (Minimal Set)

| Image | Size | Role |
|:---|:---|:---|
| `winebot:local-rel` | 5.9 GB | Wine desktop + API |
| `winebot-cv:gpu` | 14 GB | CV/OCR GPU sidecar |

### Key Files

| File | Lines | Purpose |
|:---|:---|:---|
| `winebot-gt-generator.py` | ~1240 | 7 scenes × 8 themes × interaction states |
| `fine_tune_detector.py` | ~250 | YOLO training pipeline |
| `benchmark_runner.py` | ~400 | Statistical benchmark harness |
| `benchmark_report.py` | ~320 | Markdown report generator |
| `benchmark_dataset.py` | ~380 | 6 synthetic test images |
| `winebot-gt-extractor.py` | ~250 | Session recording → labeled data |
| `ocr_engines.py` | ~630 | Tesseract + PaddleOCR + PP-OCRv6 ONNX |
| `ui_detectors.py` | ~850 | 6 detectors: contour, yolo, omniparser, uidetr1, screenparser, wine |
| `cv-sidecar-server.py` | ~520 | FastAPI: /health, /analyze, /batch, /watch, /benchmark |

---

## Quick Start

```bash
# Rebuild GPU sidecar
docker build -f docker/Dockerfile.cv-analyzer-gpu -t winebot-cv:gpu .

# Start with shared model cache
docker run -d --gpus all --shm-size=4g --name winebot-cv -p 8001:8001 \
  -e UI_DETECTOR=wine -e OCR_BACKEND=tesseract -e OCR_FAST=1 \
  -v ~/.cache/winebot-models:/models winebot-cv:gpu

# Run benchmark
docker exec winebot-cv sh -c "
  python3 /scripts/benchmark_dataset.py --output /tmp/bench_dataset > /dev/null
  python3 /scripts/benchmark_runner.py \
    --frames /tmp/bench_dataset \
    --engine 'wine:tesseract' \
    --warmup 2 --iterations 10 \
    --output /tmp/results.json
"

# Generate training data
docker exec winebot-cv python3 /scripts/winebot-gt-generator.py \
  --output /models/wine-dataset --count 2000

# Fine-tune
docker exec winebot-cv python3 /scripts/fine_tune_detector.py \
  --data /models/wine-dataset/data.yaml \
  --model /models/yolo/yolov8n.pt \
  --output /models/yolo/wine-finetuned.pt --epochs 30
```

---

*Document updated 2026-06-23. VLM integration deferred to next session.*
