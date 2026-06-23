#!/usr/bin/env python3
"""Fine-tune UI element detectors on Wine desktop ground truth data.

Uses the winebot-gt-generator.py output (YOLO format) to fine-tune ScreenParser
on Wine-specific desktop elements. After training, the model recognizes tint2
taskbars, openbox window decorations, Wine-rendered dialogs, and Wine fonts.

Usage:
  # Generate training data
  python3 winebot-gt-generator.py --output /models/wine-dataset --count 500

  # Fine-tune ScreenParser
  python3 fine_tune_detector.py \
    --data /models/wine-dataset/data.yaml \
    --model /models/screenparser/best.pt \
    --epochs 50 --batch 4 --imgsz 1280 \
    --output /models/wine-screenparser.pt

  # Benchmark before/after
  python3 benchmark_runner.py \
    --frames /tmp/bench_dataset \
    --engine screenparser:tesseract \
    --engine 'wine-screenparser:tesseract' \
    --warmup 2 --iterations 10
"""

import argparse
import json
import os
import sys
import time
from pathlib import Path


def verify_dataset(data_yaml: str):
    """Verify YOLO dataset format."""
    if not os.path.exists(data_yaml):
        print(f"ERROR: data.yaml not found: {data_yaml}", file=sys.stderr)
        sys.exit(1)

    # Check images and labels exist
    base = os.path.dirname(data_yaml)
    img_dir = os.path.join(base, "images")
    lbl_dir = os.path.join(base, "labels")

    if not os.path.isdir(img_dir):
        print(f"ERROR: images directory not found: {img_dir}", file=sys.stderr)
        sys.exit(1)

    imgs = sorted([f for f in os.listdir(img_dir) if f.endswith(".png")])
    lbls = sorted([f for f in os.listdir(lbl_dir) if f.endswith(".txt")])

    if not imgs:
        print(f"ERROR: no images in {img_dir}", file=sys.stderr)
        sys.exit(1)

    print(f"Dataset: {len(imgs)} images, {len(lbls)} label files")

    # Count annotations
    total_boxes = 0
    for lbl in lbls[:100]:  # Check first 100
        with open(os.path.join(lbl_dir, lbl)) as f:
            total_boxes += len([l for l in f if l.strip()])

    print(f"  ~{total_boxes} bounding boxes (in first 100 files)")


def fine_tune(model_path: str, data_yaml: str, output_path: str,
              epochs: int = 50, batch: int = 4, imgsz: int = 1280,
              lr0: float = 0.001, freeze: int = 10, device: int = 0,
              patience: int = 10, pretrained: bool = True,
              resume: bool = False):
    """Fine-tune YOLO model on Wine desktop data.

    Args:
        model_path: Path to pretrained ScreenParser/YOLO weights.
        data_yaml: Path to dataset data.yaml.
        output_path: Where to save the fine-tuned model.
        epochs: Training epochs (50 for fine-tuning).
        batch: Batch size (4 for RTX 3090 at 1280px).
        imgsz: Image size (native desktop resolution).
        lr0: Initial learning rate (low for fine-tuning).
        freeze: Freeze first N layers (backbone frozen).
        device: GPU device index.
        patience: Early stopping patience.
        pretrained: Use pretrained weights as starting point.
        resume: Resume from interrupted training.
    """
    from ultralytics import YOLO

    print(f"Loading model: {model_path}")
    model = YOLO(model_path)

    print(f"Training configuration:")
    print(f"  Data:      {data_yaml}")
    print(f"  Model:     {model_path}")
    print(f"  Epochs:    {epochs}")
    print(f"  Batch:     {batch}")
    print(f"  Image sz:  {imgsz}")
    print(f"  LR:        {lr0}")
    print(f"  Freeze:    {freeze} layers")
    print(f"  Device:    GPU {device}")
    print(f"  Patience:  {patience}")
    print()

    t0 = time.time()

    results = model.train(
        data=data_yaml,
        epochs=epochs,
        imgsz=imgsz,
        batch=batch,
        lr0=lr0,
        freeze=freeze,
        device=device,
        patience=patience,
        pretrained=pretrained,
        resume=resume,
        # Wine-specific augmentations — minimal distortion
        # (desktop elements should stay upright, no shear)
        augment=True,
        hsv_h=0.01,   # Tiny hue shift
        hsv_s=0.3,    # Some saturation variation
        hsv_v=0.3,    # Some brightness variation
        degrees=0.0,  # No rotation
        translate=0.05,  # Slight translation
        scale=0.2,    # Moderate scale
        shear=0.0,    # No shear
        perspective=0.0,  # No perspective
        flipud=0.0,   # No vertical flip
        fliplr=0.0,   # No horizontal flip (desktop is directional)
        mosaic=0.0,   # No mosaic for fine-tuning
        mixup=0.0,    # No mixup
        # Save config
        save=True,
        save_period=10,
        project=os.path.dirname(output_path) or ".",
        name=os.path.splitext(os.path.basename(output_path))[0],
        exist_ok=True,
    )

    elapsed = time.time() - t0
    print(f"\nTraining complete in {elapsed/60:.1f} min")

    # Save best model to specified path
    best_path = os.path.join(
        os.path.dirname(output_path) or ".",
        os.path.splitext(os.path.basename(output_path))[0],
        "weights",
        "best.pt"
    )

    if os.path.exists(best_path):
        # Copy or symlink to the requested output path
        import shutil
        shutil.copy2(best_path, output_path)
        print(f"Best model saved: {output_path}")

    return results


def evaluate(model_path: str, data_yaml: str, imgsz: int = 1280):
    """Evaluate fine-tuned model on validation data."""
    from ultralytics import YOLO

    model = YOLO(model_path)
    metrics = model.val(data=data_yaml, imgsz=imgsz)

    return {
        "mAP50": float(metrics.box.map50),
        "mAP50-95": float(metrics.box.map),
        "precision": float(metrics.box.mp),
        "recall": float(metrics.box.mr),
    }


def main():
    parser = argparse.ArgumentParser(
        description="Fine-tune UI detector on Wine desktop data"
    )
    parser.add_argument("--data", required=True,
                        help="Path to data.yaml")
    parser.add_argument("--model", default="/models/screenparser/best.pt",
                        help="Pretrained model weights")
    parser.add_argument("--output", default="/models/wine-screenparser.pt",
                        help="Output path for fine-tuned model")
    parser.add_argument("--epochs", type=int, default=50,
                        help="Training epochs")
    parser.add_argument("--batch", type=int, default=4,
                        help="Batch size (4 for RTX 3090 at 1280)")
    parser.add_argument("--imgsz", type=int, default=1280,
                        help="Input image size")
    parser.add_argument("--lr", type=float, default=0.001, dest="lr0",
                        help="Learning rate")
    parser.add_argument("--freeze", type=int, default=10,
                        help="Freeze first N backbone layers")
    parser.add_argument("--device", type=int, default=0,
                        help="GPU device index")
    parser.add_argument("--patience", type=int, default=10,
                        help="Early stopping patience")
    parser.add_argument("--resume", action="store_true",
                        help="Resume from interrupted training")
    parser.add_argument("--verify", action="store_true",
                        help="Only verify dataset, don't train")
    parser.add_argument("--eval-only", action="store_true",
                        help="Only evaluate, don't train")

    args = parser.parse_args()

    verify_dataset(args.data)

    if args.verify:
        print("Dataset verified — ready for training.")
        return

    if args.eval_only:
        metrics = evaluate(args.model, args.data, args.imgsz)
        print(f"Evaluation:")
        for k, v in metrics.items():
            print(f"  {k}: {v:.4f}")
        return

    results = fine_tune(
        model_path=args.model,
        data_yaml=args.data,
        output_path=args.output,
        epochs=args.epochs,
        batch=args.batch,
        imgsz=args.imgsz,
        lr0=args.lr0,
        freeze=args.freeze,
        device=args.device,
        patience=args.patience,
        resume=args.resume,
    )

    # Quick evaluation
    if os.path.exists(args.output):
        print("\nEvaluating fine-tuned model...")
        metrics = evaluate(args.output, args.data, args.imgsz)
        print(f"  mAP50:  {metrics['mAP50']:.4f}")
        print(f"  mAP50-95: {metrics['mAP50-95']:.4f}")
        print(f"  Precision: {metrics['precision']:.4f}")
        print(f"  Recall: {metrics['recall']:.4f}")


if __name__ == "__main__":
    main()
