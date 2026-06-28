#!/usr/bin/env python3
"""Direct YOLO v2 vs v3 evaluation on held-out eval dataset.

Usage:
  docker exec winebot-cv python3 /tmp/eval_yolo_v3.py
  # or directly if ultralytics is installed:
  python3 eval_yolo_v3.py
"""
import glob
import json
import os
import sys
import time
from collections import defaultdict

import numpy as np

# ── Config ───────────────────────────────────────────────────────────────────

EVAL_DIR = "/models/eval-dataset"
MODEL_V2 = "/models/yolo/wine-yolo26s/weights/best.pt"
MODEL_V3 = "/models/yolo/wine-yolo26s-v3/weights/best.pt"

CLASS_NAMES = {
    0: "title_bar", 1: "title_text", 2: "button", 3: "close_button",
    4: "text_field", 5: "dropdown", 6: "checkbox", 7: "radio",
    8: "menu_bar", 9: "menu_item", 10: "taskbar", 11: "dialog",
    12: "text_area", 13: "scrollbar", 14: "list_item", 15: "tab",
    16: "progress_bar", 17: "toolbar", 18: "status_bar", 19: "link",
    20: "icon", 21: "spinner_button",
}
IDX_TO_NAME = CLASS_NAMES
NAME_TO_IDX = {v: k for k, v in CLASS_NAMES.items()}

IOU_THRESH = 0.5
CONF_THRESH = 0.25

NUM_BOOTSTRAP = 1000


def load_gt(label_path):
    """Load YOLO-format labels. Returns list of {cls_id, bbox} (normalized [x,y,w,h])."""
    elems = []
    if not os.path.isfile(label_path):
        return elems
    with open(label_path) as f:
        for line in f:
            parts = line.strip().split()
            if len(parts) < 5:
                continue
            cls_id = int(parts[0])
            cx, cy, nw, nh = map(float, parts[1:5])
            elems.append({
                "cls_id": cls_id,
                "bbox": [cx - nw / 2, cy - nh / 2, nw, nh],
            })
    return elems


def iou(a, b):
    ax, ay, aw, ah = a
    bx, by, bw, bh = b
    xi = max(0, min(ax + aw, bx + bw) - max(ax, bx))
    yi = max(0, min(ay + ah, by + bh) - max(ay, by))
    inter = xi * yi
    union = aw * ah + bw * bh - inter
    return inter / union if union > 0 else 0.0


def evaluate_model(model, name, image_dir, label_dir):
    """Run full evaluation of a YOLO model on the dataset."""
    image_files = sorted(glob.glob(os.path.join(image_dir, "*.png")) +
                         glob.glob(os.path.join(image_dir, "*.jpg")))

    print(f"\n{'='*60}")
    print(f"  Evaluating {name}")
    print(f"  {len(image_files)} images")
    print(f"{'='*60}")

    # Per-class accumulators
    by_class = defaultdict(lambda: {"tp": 0, "fp": 0, "fn": 0, "gt_count": 0, "pred_count": 0})
    total_gt = 0
    total_pred = 0
    total_tp = 0
    times = []

    for fname in image_files:
        basename = os.path.basename(fname)
        lbl_name = basename.replace(".png", ".txt").replace(".jpg", ".txt")
        lbl_path = os.path.join(label_dir, lbl_name)

        gt = load_gt(lbl_path)

        # Run inference
        t0 = time.time()
        results = model(fname, conf=CONF_THRESH, iou=IOU_THRESH, verbose=False)
        elapsed = time.time() - t0
        times.append(elapsed)

        # Parse predictions
        preds = []
        if len(results) > 0:
            boxes = results[0].boxes
            if boxes is not None:
                for i in range(len(boxes.cls)):
                    cls_id = int(boxes.cls[i].item())
                    conf = boxes.conf[i].item()
                    xyxy = boxes.xyxy[i].tolist()
                    # Convert [x1,y1,x2,y2] → [x,y,w,h] normalized
                    img_h, img_w = results[0].orig_shape
                    x1, y1, x2, y2 = xyxy
                    cx = (x1 + x2) / 2 / img_w
                    cy = (y1 + y2) / 2 / img_h
                    w = (x2 - x1) / img_w
                    h = (y2 - y1) / img_h
                    preds.append({"cls_id": cls_id, "bbox": [cx - w/2, cy - h/2, w, h], "conf": conf})

        # Match predictions to ground truth
        matched_gt = set()
        matched_pred = set()

        for pi, pred in enumerate(preds):
            for gi, g in enumerate(gt):
                if gi in matched_gt:
                    continue
                if pred["cls_id"] == g["cls_id"] and iou(pred["bbox"], g["bbox"]) >= IOU_THRESH:
                    matched_gt.add(gi)
                    matched_pred.add(pi)
                    break

        # Count per class
        for g in gt:
            by_class[g["cls_id"]]["gt_count"] += 1
        for p in preds:
            by_class[p["cls_id"]]["pred_count"] += 1

        for gi in matched_gt:
            by_class[gt[gi]["cls_id"]]["tp"] += 1
        for gi in range(len(gt)):
            if gi not in matched_gt:
                by_class[gt[gi]["cls_id"]]["fn"] += 1
        for pi in range(len(preds)):
            if pi not in matched_pred:
                by_class[preds[pi]["cls_id"]]["fp"] += 1

        total_gt += len(gt)
        total_pred += len(preds)
        total_tp += len(matched_gt)

    # Compute per-class metrics
    results_dict = {}
    all_f1s = []
    for cls_id in sorted(CLASS_NAMES.keys()):
        stats = by_class[cls_id]
        p = stats["tp"] / stats["pred_count"] if stats["pred_count"] > 0 else 0.0
        r = stats["tp"] / stats["gt_count"] if stats["gt_count"] > 0 else 0.0
        f1 = 2 * p * r / (p + r) if (p + r) > 0 else 0.0
        results_dict[CLASS_NAMES[cls_id]] = {
            "gt": stats["gt_count"],
            "pred": stats["pred_count"],
            "tp": stats["tp"],
            "fp": stats["fp"],
            "fn": stats["fn"],
            "precision": round(p, 4),
            "recall": round(r, 4),
            "f1": round(f1, 4),
        }
        all_f1s.append(f1)

    # Overall
    overall_p = total_tp / total_pred if total_pred > 0 else 0.0
    overall_r = total_tp / total_gt if total_gt > 0 else 0.0
    overall_f1 = 2 * overall_p * overall_r / (overall_p + overall_r) if (overall_p + overall_r) > 0 else 0.0

    mean_f1 = float(np.mean(all_f1s)) if all_f1s else 0.0
    median_f1 = float(np.median(all_f1s)) if all_f1s else 0.0
    min_f1 = float(np.min(all_f1s)) if all_f1s else 0.0
    max_f1 = float(np.max(all_f1s)) if all_f1s else 0.0

    # Latency
    avg_time = float(np.mean(times)) if times else 0.0

    return {
        "name": name,
        "total_gt": total_gt,
        "total_pred": total_pred,
        "total_tp": total_tp,
        "precision": round(overall_p, 4),
        "recall": round(overall_r, 4),
        "f1": round(overall_f1, 4),
        "mean_per_class_f1": round(mean_f1, 4),
        "median_per_class_f1": round(median_f1, 4),
        "min_per_class_f1": round(min_f1, 4),
        "max_per_class_f1": round(max_f1, 4),
        "avg_inference_time_ms": round(avg_time * 1000, 1),
        "per_class": results_dict,
    }


def bootstrap_ci(detection_list, n_resamples=1000, ci=0.95):
    """Bootstrap F1 scores across per-class results for CI."""
    f1s = np.array(detection_list)
    means = []
    n = len(f1s)
    for _ in range(n_resamples):
        sample = np.random.choice(f1s, size=n, replace=True)
        means.append(np.mean(sample))
    means.sort()
    alpha = (1.0 - ci) / 2.0
    return {
        "mean": float(np.mean(f1s)),
        "ci_low": float(means[int(n_resamples * alpha)]),
        "ci_high": float(means[int(n_resamples * (1.0 - alpha))]),
        "n": n,
    }


def main():
    image_dir = os.path.join(EVAL_DIR, "images")
    label_dir = os.path.join(EVAL_DIR, "labels")

    if not os.path.isdir(image_dir) or not os.path.isdir(label_dir):
        print(f"ERROR: eval dataset not found at {EVAL_DIR}")
        sys.exit(1)

    from ultralytics import YOLO

    # Load models
    results = []
    model_configs = [
        (MODEL_V2, "YOLO26-S v2 (production)"),
        (MODEL_V3, "YOLO26-S v3 (oversampled)"),
    ]

    for model_path, model_name in model_configs:
        if not os.path.isfile(model_path):
            print(f"  WARNING: model not found: {model_path}")
            continue

        print(f"\nLoading {model_name} from {model_path}")
        model = YOLO(model_path)
        result = evaluate_model(model, model_name, image_dir, label_dir)
        results.append(result)

        # Print summary
        print(f"\n  {'─'*50}")
        print(f"  {model_name}")
        print(f"  {'─'*50}")
        print(f"  Precision:   {result['precision']:.4f}")
        print(f"  Recall:      {result['recall']:.4f}")
        print(f"  F1:          {result['f1']:.4f}")
        print(f"  Mean class F1: {result['mean_per_class_f1']:.4f}")
        print(f"  Median class F1: {result['median_per_class_f1']:.4f}")
        print(f"  Min class F1: {result['min_per_class_f1']:.4f}  "
              f"Max class F1: {result['max_per_class_f1']:.4f}")
        print(f"  Avg inference: {result['avg_inference_time_ms']:.1f}ms")
        print(f"  Total GT: {result['total_gt']}  Pred: {result['total_pred']}  "
              f"TP: {result['total_tp']}")
        print("\n  Per-class F1 (worst→best):")
        sorted_classes = sorted(result["per_class"].items(), key=lambda x: x[1]["f1"])
        for cls_name, stats in sorted_classes:
            bar = "█" * max(1, int(stats["f1"] * 40))
            print(f"    {cls_name:20s}  F1={stats['f1']:.4f}  "
                  f"P={stats['precision']:.3f}  R={stats['recall']:.3f}  "
                  f"GT={stats['gt']:4d}  Pred={stats['pred']:4d}  "
                  f"TP={stats['tp']:3d}  FP={stats['fp']:3d}  FN={stats['fn']:3d}")

    # Comparison
    if len(results) >= 2:
        print(f"\n{'='*60}")
        print("  MODEL COMPARISON: v2 vs v3")
        print(f"{'='*60}")
        r2, r3 = results[0], results[1]
        print("\n  Metric            v2        v3        Δ")
        print(f"  {'─'*50}")
        for metric in ["f1", "precision", "recall", "mean_per_class_f1", "min_per_class_f1"]:
            v2_val = r2[metric]
            v3_val = r3[metric]
            delta = v3_val - v2_val
            arrow = "↑" if delta > 0 else ("↓" if delta < 0 else "→")
            print(f"  {metric:20s}  {v2_val:.4f}   {v3_val:.4f}   {arrow}{delta:+.4f}")

        # Per-class comparison
        print("\n  Per-class F1 comparison (classes where F1 changed most):")
        deltas = []
        for cls_name in sorted(CLASS_NAMES.values()):
            v2_f1 = r2["per_class"].get(cls_name, {}).get("f1", 0)
            v3_f1 = r3["per_class"].get(cls_name, {}).get("f1", 0)
            deltas.append((cls_name, v2_f1, v3_f1, v3_f1 - v2_f1))

        deltas.sort(key=lambda x: abs(x[3]), reverse=True)
        print(f"  {'Class':20s}  v2 F1    v3 F1    Δ")
        print(f"  {'─'*50}")
        for cls_name, v2_f1, v3_f1, d in deltas:
            arrow = "↑" if d > 0 else ("↓" if d < 0 else "→")
            print(f"  {cls_name:20s}  {v2_f1:.4f}  {v3_f1:.4f}  {arrow}{d:+.4f}")

    # Save results
    output = {
        "dataset": EVAL_DIR,
        "iou_threshold": IOU_THRESH,
        "conf_threshold": CONF_THRESH,
        "results": results,
        "num_bootstrap_resamples": NUM_BOOTSTRAP,
    }
    output_path = "/models/eval-yolo-v2-v3-comparison.json"
    with open(output_path, "w") as f:
        json.dump(output, f, indent=2)
    print(f"\nResults saved: {output_path}")


if __name__ == "__main__":
    main()
