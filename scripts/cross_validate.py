#!/usr/bin/env python3
"""K-fold cross-validation for the WineBot CV pipeline.

Generates K independent train/val splits using the GT generator,
trains a YOLO model on each, and reports mean ± std metrics across folds.

This is the gold standard for scientific rigor — it measures how stable
our results are across different data splits, not just one held-out set.

Usage:
  docker exec winebot-cv python3 /tmp/cross_validate.py --folds 5
"""
import argparse
import json
import os
import random
import sys

sys.path.insert(0, "/scripts")
import cv2
import numpy as np


def main():
    parser = argparse.ArgumentParser(
        description="K-fold cross-validation for WineBot pipeline")
    parser.add_argument("--folds", type=int, default=5,
                        help="Number of folds (default: 5)")
    parser.add_argument("--images-per-fold", type=int, default=200,
                        help="Images per fold per scene (default: 200)")
    parser.add_argument("--epochs", type=int, default=30,
                        help="Training epochs per fold (default: 30)")
    parser.add_argument("--output", default="/models/cross-validation",
                        help="Output directory")
    args = parser.parse_args()

    os.makedirs(args.output, exist_ok=True)

    print(f"\n{'='*60}")
    print("  K-FOLD CROSS-VALIDATION")
    print(f"  Folds: {args.folds}   Images/fold/scene: {args.images_per_fold}")
    print(f"  Epochs: {args.epochs}")
    print(f"{'='*60}\n")

    # Import GT generator
    import importlib.util
    spec = importlib.util.spec_from_file_location(
        "winebot_gt", "/scripts/winebot-gt-generator.py")
    gen = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(gen)

    # All scene types
    SCENES = [n for n, _ in gen.GENERATORS]
    print(f"Scenes: {len(SCENES)} — {SCENES}")

    RESOLUTIONS = [(1280, 720), (1366, 768)]

    # Generate fold datasets
    fold_results = []

    for fold in range(args.folds):
        print(f"\n{'='*60}")
        print(f"  FOLD {fold + 1}/{args.folds}")
        print(f"{'='*60}")

        fold_dir = os.path.join(args.output, f"fold-{fold}")
        train_dir = os.path.join(fold_dir, "train")
        val_dir = os.path.join(fold_dir, "val")

        for d in [f"{train_dir}/images", f"{train_dir}/labels",
                  f"{val_dir}/images", f"{val_dir}/labels"]:
            os.makedirs(d, exist_ok=True)

        # Assign each scene to train or val for this fold
        # Each fold holds out a different subset of scenes
        n_val = max(1, len(SCENES) // args.folds)
        val_scenes = set(SCENES[fold * n_val:(fold + 1) * n_val])
        train_scenes = [s for s in SCENES if s not in val_scenes]

        print(f"  Train: {len(train_scenes)} scenes — {train_scenes}")
        print(f"  Val:   {len(val_scenes)} scenes — {val_scenes}")

        gen.set_split("all")
        gen.DESKTOP_SIZE = (1280, 720)
        total = 0

        for scene_name, scene_fn in gen.GENERATORS:
            is_val = scene_name in val_scenes
            target_dir = val_dir if is_val else train_dir
            count = args.images_per_fold

            for i in range(count):
                gen.DESKTOP_SIZE = random.choice(RESOLUTIONS)
                page = scene_fn()
                img = page.image
                if img is None:
                    continue

                fname = f"{scene_name}_{total:06d}.png"
                cv2.imwrite(os.path.join(target_dir, "images", fname), img)

                h, w = img.shape[:2]
                with open(os.path.join(target_dir, "labels",
                                       fname.replace(".png", ".txt")), "w") as lf:
                    for elem in page.elements:
                        lf.write(gen.yolo_label(elem, w, h) + "\n")
                total += 1

        print(f"  Generated: {total} images")

        # Create data.yaml
        with open(os.path.join(fold_dir, "data.yaml"), "w") as f:
            f.write(f"path: {fold_dir}\n")
            f.write("train: train/images\n")
            f.write("val: val/images\n")
            f.write("nc: 22\n")
            f.write("names:\n")
            for i, name in enumerate(gen.WINE_CLASSES):
                f.write(f"  {i}: {name}\n")

        # Train
        from ultralytics import YOLO
        model = YOLO("yolo26s.pt")
        results = model.train(
            data=f"{fold_dir}/data.yaml",
            epochs=args.epochs, imgsz=1280, batch=4,
            lr0=0.001, freeze=0, device=0, patience=5,
            pretrained=True, augment=True,
            mosaic=1.0, close_mosaic=10, mixup=0.1,
            fliplr=0.5, scale=0.5, dropout=0.05, cos_lr=True,
            hsv_h=0.015, hsv_s=0.4, hsv_v=0.4,
            translate=0.1, save=True, save_period=30,
            project=f"{fold_dir}/yolo", name="train", exist_ok=True,
        )

        # Extract best mAP50
        import csv
        best_map50 = 0
        csv_path = f"{fold_dir}/yolo/train/results.csv"
        if os.path.isfile(csv_path):
            with open(csv_path) as f:
                reader = csv.DictReader(f)
                for row in reader:
                    m50 = float(row.get("metrics/mAP50(B)", 0))
                    best_map50 = max(best_map50, m50)

        fold_results.append({
            "fold": fold,
            "val_scenes": list(val_scenes),
            "train_scenes": train_scenes,
            "best_mAP50": best_map50,
            "model_path": f"{fold_dir}/yolo/train/weights/best.pt",
        })

        print(f"  Fold {fold + 1} best mAP50: {best_map50:.4f}")

    # Summary
    print(f"\n{'='*60}")
    print("  CROSS-VALIDATION RESULTS")
    print(f"{'='*60}")
    map50s = [r["best_mAP50"] for r in fold_results]
    print(f"  Mean mAP50: {np.mean(map50s):.4f} ± {np.std(map50s):.4f}")
    print("  Per fold:")
    for r in fold_results:
        print(f"    Fold {r['fold']}: mAP50={r['best_mAP50']:.4f} "
              f"(val: {r['val_scenes']})")

    # Save results
    with open(os.path.join(args.output, "results.json"), "w") as f:
        json.dump({
            "n_folds": args.folds,
            "images_per_fold": args.images_per_fold,
            "mean_mAP50": round(float(np.mean(map50s)), 4),
            "std_mAP50": round(float(np.std(map50s)), 4),
            "per_fold": fold_results,
        }, f, indent=2)

    print(f"\nResults saved: {os.path.join(args.output, 'results.json')}")


if __name__ == "__main__":
    main()
