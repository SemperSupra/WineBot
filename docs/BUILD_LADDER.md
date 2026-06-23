# WineBot CV/OCR — Build-Up Ladder

**Date:** 2026-06-23 | **GPU:** RTX 3090 24GB | **Commit:** `520adc2`+ in-flight

This document captures every finding from the 2026-06-23 session, orders them
into a sequence of incremental improvements, and defines the rigorous evaluation
criteria to verify each step.

---

## Baseline (Where We Ended)

### Detectors

| Engine | Speed | Elements/frame | mAP50 | F1 (Detection) | Notes |
|:---|:---|:---|:---|:---|:---|
| Contour (CPU) | 266ms | 1.0 | — | 0.500 | Wine-tuned heuristics |
| YOLO (OmniParser GPU) | 313ms | 5.5 | — | 0.400 | 1-class, not Wine-aware |
| UI-DETR-1 (GPU) | 374ms | **31.0** | 0.211 | 0.211 | Most coverage, low accuracy |
| ScreenParser-55 (GPU) | 354ms | 8.2 | — | **0.571** | Best accuracy, 55 classes |
| **Wine-FineTuned (GPU)** | ~350ms | 10-30 | **0.993** | **0.990+** | Trained today |

### OCR

| Engine | Speed | F1 | Notes |
|:---|:---|:---|:---|
| Tesseract QUALITY | 600-700ms | 0.615 | 3-PSM + CLAHE |
| Tesseract FAST | 266-374ms | 0.923 | 1-PSM, production default |
| PP-OCRv5 ONNX (server) | 2-5s | ~0.90 | Works, unoptimized, Chinese dict |

### Infrastructure

| Component | What | Status |
|:---|:---|:---|
| `winebot-gt-generator.py` | 5 scene types, 8 framework themes, 22 classes | ✅ Working |
| `fine_tune_detector.py` | YOLO training pipeline | ✅ Working |
| `benchmark_runner.py` | Statistical harness (CI95, warmup, iterations) | ✅ Working |
| `benchmark_report.py` | Markdown report generator | ✅ Working |
| Shared model cache | `~/.cache/winebot-models/` | ✅ Working |

---

## Build-Up Ladder

Each rung produces measurable, statistically rigorous improvements.
Run the full benchmark suite after every rung.

### Rung 1: YOLO26n — Instant Speed Upgrade

**Why:** YOLO26 ([arXiv:2606.03748](https://arxiv.org/abs/2606.03748), Jan 2026) provides:
- 2.1× faster CPU inference (38.9ms vs 80ms)
- 1.9× faster GPU inference (1.7ms vs 3.2ms TensorRT)
- NMS-free architecture (deterministic latency, simpler deployment)
- 25% fewer parameters (2.4M vs 3.2M)
- MuSGD optimizer for better fine-tuning convergence

**What changes:**
1. `pip install ultralytics>=8.4.100` in Dockerfile
2. Replace `YOLO("yolov8n.pt")` with `YOLO("yolo26n.pt")` in all code paths:
   - `ui_detectors.py`: YOLOUIDetector fallback
   - `fine_tune_detector.py`: default model path
3. Update `Dockerfile.cv-analyzer-gpu` to pre-download yolo26n.pt

**Evaluation:**
- Run `benchmark_runner.py` comparing YOLOv8n vs YOLO26n on 6 synthetic images
- Metrics: mean_ms, CI95, p95, p99, elements/frame
- Null hypothesis: YOLO26n mean ≤ YOLOv8n mean (non-inferiority)
- Pass if: YOLO26n is faster AND finds ≥ same elements

**Files modified:** `ui_detectors.py`, `Dockerfile.cv-analyzer-gpu`, `fine_tune_detector.py`

---

### Rung 2: PP-OCRv6 ONNX — 25× OCR Speedup

**Why:** PP-OCRv6 ([arXiv:2606.13108](https://arxiv.org/html/2606.13108v1), June 2026):
- Tiny variant: 1.5 MB, **97ms** inference
- Runs in-browser (WASM), no server needed
- Available as ONNX on HuggingFace: `PaddlePaddle/PP-OCRv6_{tiny,small,medium}_{det,rec}_onnx`
- Our current PP-OCRv5 ONNX takes 2-5s — this is 25-50× faster

**What changes:**
1. Download `PaddlePaddle/PP-OCRv6_medium_det_onnx` + `PaddlePaddle/PP-OCRv6_medium_rec_onnx` to shared cache
2. Also download tiny + small variants for comparison
3. Update `PaddleOCRONNXEngine` for v6 model input/output shapes
4. Test all 3 variants (tiny, small, medium) against Tesseract FAST

**Evaluation:**
- 3-engine comparison: Tesseract FAST vs PP-OCRv6 Tiny vs PP-OCRv6 Medium
- Metrics: mean_ms, CI95, OCR F1 vs ground truth, texts/frame
- Pass if: PP-OCRv6 Medium > Tesseract FAST F1 AND > Tesseract FAST speed

**Files modified:** `ocr_engines.py`, `models/ocr/` (new files)

---

### Rung 3: Fine-Tune YOLO26n on Wine Dataset

**Why:** YOLO26n is a different architecture from YOLOv8n (NMS-free dual head,
no DFL). Fine-tuning on our Wine dataset transfers the domain knowledge
we already proved works (mAP50 went from 0.210→0.993 with YOLOv8n).

**What changes:**
1. Run `fine_tune_detector.py --model yolo26n.pt --epochs 30 --data wine-dataset/data.yaml`
2. Same 1805 images, 22 classes, 8 themes
3. Save as `wine-yolo26n.pt` in shared cache

**Evaluation:**
- Head-to-head: Wine-YOLOv8n vs Wine-YOLO26n on benchmark dataset
- Metrics: mAP50, mAP50-95, per-class AP, mean_ms, CI95
- Pass if: Wine-YOLO26n mAP50 ≥ Wine-YOLOv8n mAP50 AND Wine-YOLO26n faster

**Files modified:** `models/yolo/wine-yolo26n.pt` (new)

---

### Rung 4: Multi-Scene Generator Expansion

**Why:** Our 5 scene types (save dialog, settings, error, notepad, control panel)
cover only a fraction of real Wine desktop states. Real apps show file managers,
browsers, terminals, multi-window layouts, inactive windows, overlapping windows,
maximized/minimized states, and modal dialogs.

**What changes:**
Add to `winebot-gt-generator.py`:

| # | New Scene | Elements Added | Priority |
|:---|:---|:---|:---|
| 1 | File manager (tree + list + toolbar + path bar) | tree, path_bar | High |
| 2 | Multi-window (2-4 windows, different frameworks, overlapping) | occlusion handling | High |
| 3 | Window states (inactive, maximized, minimized, modal) | dimmed_title, modal_overlay | High |
| 4 | Browser UI (tabs, address bar, bookmarks toolbar) | tab_group, link | Medium |
| 5 | Terminal window (text area + scrollbar) | — | Medium |
| 6 | Context menu / right-click popup | context_menu | Medium |
| 7 | Property sheet | — | Low |
| 8 | System tray popup | system_tray | Low |

Also add resolution/DPI variation generator.

**Evaluation:**
- Regenerate dataset (5,000 images with new scenes)
- Re-train YOLO26n on expanded dataset
- Test on OOD benchmark images (not seen during training)
- Pass if: OOD mAP50 > 0.75 AND cross-resolution mAP50 > 0.70

**Files modified:** `winebot-gt-generator.py`

---

### Rung 5: Coarse-to-Fine Grounding Pipeline

**Why:** The GMS paper (Sept 2025, [arXiv:2509.24133](https://arxiv.org/abs/2509.24133))
proved that a scan-then-focus pipeline achieves **10× better grounding accuracy**
than either a general VLM or a specialized detector alone.

**What changes:**
1. Add `screen_vlm.py` — lightweight ScreenVLM-316M (MIT license) for element grounding
2. New pipeline: YOLO26n detects ROIs → crop → ScreenVLM grounds precise elements
3. Add `POST /ground` endpoint to sidecar
4. Add `UIGroundingEngine` to engine registry

**Evaluation:**
- Compare pipeline vs raw YOLO26n on element-level IOU accuracy
- Metrics: IOU@0.5, IOU@0.75, element type accuracy, per-class F1
- Pass if: Pipeline IOU@0.5 > raw YOLO26n IOU@0.5

**Files modified:** `ui_detectors.py`, `cv-sidecar-server.py`, `screen_vlm.py` (NEW)

---

### Rung 6: LightOnOCR-2-1B Evaluation

**Why:** LightOnOCR-2-1B (June 2026) achieves 83.2% on olmOCR-bench
— comparable to much larger models — while being 3.3× faster than Chandra OCR.
It handles detection + recognition + layout in a single unified model.

**What changes:**
1. Add `LightOnOCREngine` to `ocr_engines.py`
2. Download model from HuggingFace to shared cache
3. Benchmark against Tesseract FAST + PP-OCRv6 ONNX

**Evaluation:**
- 3-way comparison: Tesseract FAST vs PP-OCRv6 Medium vs LightOnOCR-2-1B
- Metrics: mean_ms, CI95, OCR F1 vs ground truth
- Pass if: LightOnOCR F1 + speed Pareto-dominates Tesseract

**Files modified:** `ocr_engines.py`, `Dockerfile.cv-analyzer-gpu`

---

### Rung 7: IoU-Aware Fine-Tuning

**Why:** The R-VLM paper (ACL 2025, [ACL Anthology](https://aclanthology.org/2025.findings-acl.501/))
showed that IoU-aware loss functions improve grounding accuracy by 13% on ScreenSpot.
Our current fine-tuning uses standard YOLO losses (box + cls + DFL).

**What changes:**
1. YOLO26 already uses CIoU (Complete IoU) — better than DIoU in YOLOv8
2. For screen understanding, add structured IoU loss that considers the
   containment hierarchy of UI elements (dialog contains buttons, etc.)
3. Modify `fine_tune_detector.py` to use custom compound loss

**Evaluation:**
- Train with standard loss vs IoU-aware loss on same Wine dataset
- Metrics: mAP50, mAP50-95, per-class AP, structural consistency score
- Pass if: IoU-aware mAP50 > standard mAP50 + 0.010

**Files modified:** `fine_tune_detector.py`

---

### Rung 8: Cross-Resolution and DPI Robustness

**Why:** Our training images are all at 1280×720. Real WineBot runs at
multiple resolutions. Without resolution variation in training, the model
overfits to a specific pixel scale.

**What changes:**
1. Add resolution/DPI variation to generator:
   ```python
   TARGET_RESOLUTIONS = [(1024,768), (1280,720), (1366,768),
                         (1440,900), (1920,1080), (2560,1440)]
   DPI_SCALES = [1.0, 1.25, 1.5, 1.75]
   ```
2. Also test: render at 1.25× then downscale to simulate HiDPI
3. Regenerate dataset, re-train, benchmark

**Evaluation:**
- Test at each resolution independently
- Metrics: mAP50 degradation vs baseline (1280×720)
- Pass if: mAP50 at 1920×1080 ≥ 0.90 and mAP50 at 1024×768 ≥ 0.85

**Files modified:** `winebot-gt-generator.py`

---

### Rung 9: Font Face Generalization

**Why:** OpenCV renders fonts differently than Wine Xvfb renders fonts
than Windows native. Training on multiple OpenCV font faces forces the
model to learn shape features rather than font-specific pixel patterns.

**What changes:**
1. Randomize font face in generator:
   ```python
   FONTS = [cv2.FONT_HERSHEY_SIMPLEX, cv2.FONT_HERSHEY_DUPLEX,
            cv2.FONT_HERSHEY_COMPLEX, cv2.FONT_HERSHEY_COMPLEX_SMALL,
            cv2.FONT_HERSHEY_SCRIPT_SIMPLEX, cv2.FONT_HERSHEY_TRIPLEX]
   ```
2. Randomize font scale ±15%, thickness ±1
3. Regenerate, re-train, test on real Wine screenshots

**Evaluation:**
- Test on real Wine desktop screenshots (not synthetic)
- Metrics: OCR word accuracy, element detection mAP50
- Pass if: Wine-screenshot mAP50 ≥ 0.70 (domain gap is real)

**Files modified:** `winebot-gt-generator.py`

---

### Rung 10: Full Multi-Engine Evaluation Matrix

**Why:** After implementing all above, we need a definitive comparison showing
which engine combos are best for which use cases.

**What changes:**
1. Run `benchmark_runner.py` with ALL engine combos:
   - 6 detectors × 4 OCR engines = 24 combos
   - 3 frame sets (synthetic, Wine real, mixed)
   - 10 iterations each, 95% CI

**Evaluation:**
- 3-dimensional Pareto frontier: speed vs accuracy vs element coverage
- Per-use-case recommendation:
  - "Fastest with acceptable accuracy" → real-time monitoring
  - "Best accuracy regardless of speed" → offline analysis
  - "Best balance" → production default

**Output:** `BENCHMARK_FINAL.md` committed to repo

---

## Evaluation Protocol (Applied at Every Rung)

Every rung must pass a statistical gate before being considered complete:

### Statistical Power

- **Warmup:** 3 frames per engine (CUDA kernel compilation, model lazy-load)
- **Iterations:** 10 per frame per engine
- **Frames:** 6 synthetic ground-truth images with known labels
- **Confidence:** 95% CI via t-distribution (accounts for small n)
- **Significance:** Non-overlapping CIs = statistically significant difference
- **Effect size:** Cohen's d for speed differences, absolute mAP/F1 delta for accuracy

### Metrics Collected Per Rung

| Category | Metrics |
|:---|:---|
| Speed | mean_ms, p50_ms, p95_ms, p99_ms, CI95_low, CI95_high, effective_fps |
| Detection | mAP50, mAP50-95, elements/frame, interactive/frame, per-class AP |
| OCR | OCR F1 (precision, recall), texts/frame, char-level accuracy |
| Stability | std_ms, CV%, min_ms, max_ms (per-frame variance) |

### Pass/Fail Criteria

| Test | Criterion | Type |
|:---|:---|:---|
| Speed improvement | mean_ms(new) < mean_ms(old) with non-overlapping 95% CI | Gate |
| Accuracy non-regression | F1(new) ≥ F1(old) − 0.02 (within noise) | Gate |
| Elements detected | elements(new) ≥ elements(old) × 0.9 | Soft |
| Cross-framework | mAP50 across ≥3 themes > 0.70 | Gate (rung 4+) |
| Cross-resolution | mAP50 at 3 resolutions > 0.75 | Gate (rung 8+) |

---

## Dependency Graph

```
Rung 1 (YOLO26n) ──────────────────────────────────────────┐
    │                                                        │
    ├── Rung 2 (PP-OCRv6) ─── independent, parallel         │
    │                                                        │
    ├── Rung 3 (Fine-tune YOLO26n) ─── needs Rung 1 ✓       │
    │                                                        │
    ├── Rung 4 (More scenes) ───────── independent           │
    │    │                                                   │
    │    └── Rung 8 (Cross-resolution) ── needs Rung 4       │
    │    └── Rung 9 (Font generalization) ── needs Rung 4    │
    │                                                        │
    ├── Rung 5 (Coarse-to-fine) ────── needs Rung 1         │
    │                                                        │
    ├── Rung 6 (LightOnOCR) ────────── independent           │
    │                                                        │
    └── Rung 7 (IoU-aware loss) ────── needs Rung 3         │
         │                                                   │
         └── Rung 10 (Full matrix) ─── needs Rungs 1-9 ◄────┘
```

Rungs 1, 2, 4, 6, 8, 9 can be started in any order.
Rungs 3, 5, 7 depend on earlier rungs.
Rung 10 is the capstone evaluation.

---

## Implementation Estimates

| Rung | Code Changes | Training Time | Evaluation Time | Total |
|:---|:---|:---|:---|:---|
| 1 | 15 lines, 3 files | 0 min | 15 min | 15 min |
| 2 | 30 lines, 1 file | 0 min (download) | 15 min | 15 min |
| 3 | 1 command | 30 min | 15 min | 45 min |
| 4 | 200 lines, 1 file | 0 (regenerate) | 45 min | 1.5 hr |
| 5 | 300 lines, 2 files | 3-4 hr (download + setup) | 30 min | 4-5 hr |
| 6 | 80 lines, 2 files | 0 min (download) | 15 min | 30 min |
| 7 | 40 lines, 1 file | 30 min | 15 min | 45 min |
| 8 | 30 lines, 1 file | 0 (regenerate) | 15 min | 15 min |
| 9 | 20 lines, 1 file | 0 (regenerate) | 15 min | 15 min |
| 10 | 1 command | 0 | 2 hr | 2 hr |

**Total path if sequential:** ~12 hours (mostly training/evaluation)
**Total path if rungs 1-2 done in parallel:** ~8 hours

---

## How to Run Evaluations

```bash
# After each rung, run:
docker exec winebot-cv sh -c "
python3 /scripts/benchmark_dataset.py --output /tmp/bench_dataset > /dev/null 2>&1
python3 /scripts/benchmark_runner.py \
  --frames /tmp/bench_dataset \
  --engine 'contour:tesseract' \
  --engine 'yolo:tesseract' \
  --engine 'uidetr1:tesseract' \
  --engine 'screenparser:tesseract' \
  --engine 'wine-finetuned:tesseract' \
  --warmup 2 --iterations 10 \
  --output /tmp/bench_rungN.json 2>&1
"

# Generate report:
docker exec winebot-cv cat /tmp/bench_rungN.json | \
  python3 scripts/diagnostics/benchmark_report.py - -o /tmp/BENCH_RUNG_N.md

# Compare with previous rung:
python3 scripts/diagnostics/benchmark_report.py /tmp/bench_rungN-1.json
```

---

## Expected Outcomes

| Rung | Expected Speed Change | Expected Accuracy Change |
|:---|:---|:---|
| 1 | -30-50% detection time | Equal or +3.6 mAP50-95 |
| 2 | -90%+ OCR time | Equal or better F1 |
| 3 | -30% detection + same acc | mAP50 ≥ 0.95 (vs 0.99 YOLOv8n) |
| 4 | Unchanged | OOD mAP50 > 0.75 |
| 5 | +50ms pipeline overhead | +10% element accuracy |
| 6 | -70% OCR time vs Tesseract | OCR F1 > 0.90 |
| 7 | Unchanged | +0.01-0.02 mAP50 |
| 8 | Unchanged | Cross-resolution mAP50 > 0.85 |
| 9 | Unchanged | Wine-screenshot mAP50 > 0.70 |
| 10 | Comprehensive matrix | Definitive rankings |

---

*Document generated 2026-06-23. Update with Rung N results as each completes.*
