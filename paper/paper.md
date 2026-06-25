---
title: 'WineGT: Programmatic Ground-Truth Generation for Desktop UI Detection and OCR'
tags:
  - Python
  - computer vision
  - UI detection
  - OCR
  - ground truth
  - benchmark
authors:
  - name: Mark E. DeYoung
    affiliation: 1
affiliations:
  - name: Independent Researcher
    index: 1
date: 25 June 2026
bibliography: paper.bib
---

# Summary

WineGT is a Python framework for generating synthetic but photorealistic ground-truth datasets for desktop user interface (UI) element detection and optical character recognition (OCR). It produces rendered screenshots of common desktop application windows — dialogs, editors, control panels, file managers, and more — with pixel-perfect bounding-box labels for 22 UI element classes (buttons, text fields, dropdowns, checkboxes, title bars, etc.). The rendered frames are paired with YOLO-format annotation files, making them directly usable for training and benchmarking object-detection models.

The framework addresses a fundamental bottleneck in desktop automation: the scarcity of labeled training data for native Windows/Linux desktop UI elements. Unlike web UI datasets (e.g., WebSRC, RICO) that can be scraped at scale, desktop UI data requires manual annotation of windowed applications with diverse themes, fonts, and rendering engines. WineGT eliminates this bottleneck by programmatically generating unlimited labeled frames with controlled variation across scene types, GUI frameworks, color themes, font sets, and screen resolutions.

# Statement of Need

Accurate UI element detection is critical for robotic process automation (RPA), accessibility tools, and automated software testing. While recent advances in object detection (YOLOv8, YOLO11) and OCR (PP-OCRv6) have made production-quality pipelines feasible, these models require large, diverse training datasets that are expensive to produce manually.

Existing synthetic data approaches fall into three categories: (1) web-only renderers that cannot produce native desktop widgets, (2) full-application screenshots requiring manual labeling, and (3) renderings from game engines that lack UI-specific semantics. WineGT occupies a unique niche: it uses OpenCV drawing primitives to render desktop UI elements with sub-pixel accuracy, then composites them into coherent application windows using configurable layout engines.

The 10K-image WineGT-10K dataset — generated with held-out scene types and GUI frameworks — provides a rigorous benchmark for measuring detector generalization, revealing that seemingly strong mAP50 scores (>0.90) on random splits collapse to 0.76 when evaluated on genuinely unseen scene templates.

# Key Features

- **Programmatic GT generation**: Renders 22 UI element classes with perfect bounding-box labels, eliminating annotation cost and human error.
- **Controlled variation**: 15 scene types (save dialogs, settings windows, error dialogs, etc.), 8 GUI framework themes (Win32 Classic, Win10 Fluent, Qt Fusion, GTK Adwaita, Electron Dark, etc.), multiple font families, and 5 screen resolutions.
- **Proper train/val/test splits**: Held-out scene types and framework themes ensure generalization metrics are honest — not inflated by template overlap.
- **YOLO-format output**: Directly compatible with Ultralytics YOLOv8/YOLO11/YOLO26 training pipelines without conversion.
- **CLIP-compatible indexing**: Output frames can be embedded with OpenCLIP ViT-B-32 for semantic search over the generated dataset.
- **Multi-engine benchmark harness**: Built-in support for comparing detectors (YOLO, ScreenParser, OmniParser, DETR) and OCR engines (Tesseract, PP-OCRv6) on generated test sets.

# Implementation

WineGT is implemented in pure Python (3.12+) using OpenCV for rasterization, NumPy for data handling, and the standard library for YOLO-format serialization. The renderer produces 1280×720 frames by compositing individually-drawn UI elements (windows, buttons, text fields, etc.) with configurable layout parameters.

Each generated scene is defined by a declarative template that specifies element types, positions, sizes, and text content. Templates support randomization of element positions within constraints, producing diverse layouts from a single scene definition.

The dataset generator supports three operation modes:

1. **Single scene**: Generate one frame for visual inspection or debug.
2. **Batch generation**: Produce N frames with random variation across scene types, themes, and resolutions.
3. **K-fold splits**: Generate training/validation/test sets with controllable overlap, enabling proper generalization measurement.

The current release includes the `winebot-gt-generator.py` script, along with companion tools for dataset verification (`validate_dataset.py`), model fine-tuning (`fine_tune_detector.py`), and multi-engine benchmarking (`benchmark_runner.py`).

# Evaluation

We generated a 10,000-image dataset (WineGT-10K) using 13 training scene types × 6 GUI frameworks, with 2 held-out scene types and 2 held-out frameworks for validation and testing. All frames are 1280×720 with 22 object classes.

Fine-tuning YOLOv8n on the training split yields:

| Model | Split | mAP50 | mAP50-95 | Notes |
|:---|:---:|:---:|:---:|:---|
| YOLOv8n | Random split | 0.918 | 0.689 | Inflated by template overlap |
| YOLOv8n | Proper held-out | 0.758 | 0.547 | Honest generalization metric |
| YOLO26s | Proper held-out | *training* | *training* | Larger model, NMS-free architecture |

The 0.16 mAP50 gap between random and proper splits demonstrates the importance of held-out evaluation — a finding directly applicable to any synthetic data pipeline.

# Acknowledgements

This work uses the OpenCV library (BSD license) for rendering, the Ultralytics library (AGPL-3.0) for YOLO model training, and OpenCLIP (MIT license) for CLIP-based semantic indexing.

# References
