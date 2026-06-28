#!/usr/bin/env python3
"""Retrain YOLO26-S with proper augmentations for better generalization.

Key changes from previous run:
- mosaic=1.0 (was 0.0) — 4-image mosaic for occlusion robustness
- mixup=0.1 (was 0.0) — image blending regularization
- fliplr=0.5 (was 0.0) — horizontal flip (desktop elements symmetric)
- cos_lr=True (was False) — cosine annealing LR schedule
- scale=0.5 (was 0.2) — more aggressive scale variation
- dropout=0.05 (was 0.0) — feature dropout for regularization
"""
from ultralytics import YOLO

DATA = "/models/wine-dataset-10k/data.yaml"
MODEL = "yolo26s.pt"
OUTPUT = "/models/yolo/wine-yolo26s-v2"
EPOCHS = 50
BATCH = 4
IMSZ = 1280
LR0 = 0.001

print("=== YOLO26-S Retrain (Improved Augmentations) ===")
print(f"  Data: {DATA}")
print(f"  Model: {MODEL}")
print(f"  Epochs: {EPOCHS}")
print(f"  Batch: {BATCH}")
print(f"  Image: {IMSZ}")
print(f"  LR: {LR0}")
print()
print("  --- Augmentations (improved) ---")
print("  mosaic: 1.0   (was 0.0)")
print("  mixup: 0.1    (was 0.0)")
print("  fliplr: 0.5   (was 0.0)")
print("  cos_lr: True  (was False)")
print("  scale: 0.5    (was 0.2)")
print("  dropout: 0.05 (was 0.0)")
print()

model = YOLO(MODEL)

results = model.train(
    data=DATA,
    epochs=EPOCHS,
    imgsz=IMSZ,
    batch=BATCH,
    lr0=LR0,
    freeze=0,
    device=0,
    patience=10,
    pretrained=True,
    augment=True,
    # Improved augmentations
    mosaic=1.0,
    close_mosaic=10,
    mixup=0.1,
    fliplr=0.5,
    scale=0.5,
    dropout=0.05,
    cos_lr=True,
    # Keep reasonable defaults
    hsv_h=0.015,
    hsv_s=0.4,
    hsv_v=0.4,
    degrees=0.0,
    translate=0.1,
    shear=0.0,
    perspective=0.0,
    flipud=0.0,
    # Save config
    save=True,
    save_period=10,
    project="/models/yolo",
    name="wine-yolo26s-v2",
    exist_ok=True,
)

print("\nTraining complete!")
print(f"Results saved to {OUTPUT}")
