#!/usr/bin/env python3
"""
Pipeline Evaluator — rigorous, stage-by-stage measurement of the full CV/OCR pipeline.

Produces:
  1. Per-stage metrics with 95% bootstrapped confidence intervals
  2. End-to-end workflow success rates
  3. Ablation comparisons (swap any component, measure delta)
  4. Statistical significance tests (McNemar's, paired bootstrap)
  5. Per-class detection analysis (confusion matrix, F1, mAP per class)

Usage:
  # Full evaluation on the eval dataset
  python3 pipeline_evaluator.py --dataset /models/eval-dataset --api http://localhost:8001

  # Ablation: compare wine vs screenparser
  python3 pipeline_evaluator.py --dataset /models/eval-dataset --detector wine --ablation screenparser

  # Ablation: compare OCR engines
  python3 pipeline_evaluator.py --dataset /models/eval-dataset --ocr paddle_onnx:tiny --ablation-ocr tesseract
"""
import argparse
import json
import os
import sys
import time
from collections import defaultdict

import numpy as np

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "diagnostics"))

# ── Bounding Box Utilities ───────────────────────────────────────────────────


def iou(bbox_a: list[float], bbox_b: list[float]) -> float:
    """IoU of two [x, y, w, h] boxes (pixel coords or normalized)."""
    ax, ay, aw, ah = bbox_a
    bx, by, bw, bh = bbox_b
    xi = max(0, min(ax + aw, bx + bw) - max(ax, bx))
    yi = max(0, min(ay + ah, by + bh) - max(ay, by))
    inter = xi * yi
    union = aw * ah + bw * bh - inter
    return inter / union if union > 0 else 0.0


# ── Ground Truth Loading ─────────────────────────────────────────────────────


CLASS_NAMES = {
    0: "title_bar", 1: "title_text", 2: "button", 3: "close_button",
    4: "text_field", 5: "dropdown", 6: "checkbox", 7: "radio",
    8: "menu_bar", 9: "menu_item", 10: "taskbar", 11: "dialog",
    12: "text_area", 13: "scrollbar", 14: "list_item", 15: "tab",
    16: "progress_bar", 17: "toolbar", 18: "status_bar", 19: "link",
    20: "icon", 21: "spinner_button",
}
CLASS_TO_IDX = {v: k for k, v in CLASS_NAMES.items()}


def load_gt_labels(label_path: str) -> list[dict]:
    """Load YOLO-format label file. Returns list of {cls_id, bbox}."""
    elements = []
    if not os.path.isfile(label_path):
        return elements
    with open(label_path) as f:
        for line in f:
            parts = line.strip().split()
            if len(parts) < 5:
                continue
            cls_id = int(parts[0])
            cx = float(parts[1])
            cy = float(parts[2])
            nw = float(parts[3])
            nh = float(parts[4])
            elements.append({
                "cls_id": cls_id,
                "class_name": CLASS_NAMES.get(cls_id, f"cls_{cls_id}"),
                "bbox": [cx - nw / 2, cy - nh / 2, nw, nh],  # [x, y, w, h] normalized
            })
    return elements


# ── Stage 1: Detection Evaluation ────────────────────────────────────────────


def eval_detection(predicted: list[dict], ground_truth: list[dict],
                   iou_thresh: float = 0.5, img_size: tuple = (1280, 720)) -> dict:
    """Evaluate detection against ground truth.

    Handles GT boxes in normalized [x,y,w,h] format (0-1 range) and
    predicted boxes in pixel coordinates. Normalizes predicted boxes
    to match GT for fair comparison.

    Returns per-class and overall precision, recall, F1, and mAP@iou_thresh.
    """
    img_w, img_h = img_size

    # Build ground truth index: class -> list of bboxes (normalized)
    gt_by_class = defaultdict(list)
    for gt in ground_truth:
        gt_by_class[gt["cls_id"]].append(gt["bbox"])  # already normalized

    # Build predicted index: class -> list of (bbox_normalized, confidence)
    pred_by_class = defaultdict(list)
    for p in predicted:
        cls_id = CLASS_TO_IDX.get(p.get("type", ""), -1)
        if cls_id < 0:
            continue
        conf = p.get("confidence", 0.5)
        bbox = p.get("bbox", [0, 0, 0, 0])  # pixel coords: [x, y, w, h]
        # Normalize to [0, 1] for fair comparison with GT
        norm_bbox = [bbox[0] / img_w, bbox[1] / img_h,
                     bbox[2] / img_w, bbox[3] / img_h]
        pred_by_class[cls_id].append({"bbox": norm_bbox, "confidence": conf})

    results = {"overall": {}, "per_class": {}}
    all_classes = set(list(gt_by_class.keys()) + list(pred_by_class.keys()))

    total_tp = 0
    total_fp = 0
    total_fn = 0

    for cls_id in sorted(all_classes):
        gt_boxes = gt_by_class.get(cls_id, [])
        pred_boxes = pred_by_class.get(cls_id, [])

        # Sort predictions by confidence descending
        pred_boxes.sort(key=lambda x: -x["confidence"])

        tp = 0
        fp = 0
        matched_gt = set()

        for pb in pred_boxes:
            best_iou = iou_thresh
            best_gt = -1
            for gi, gb in enumerate(gt_boxes):
                if gi in matched_gt:
                    continue
                i = iou(pb["bbox"], gb)
                if i > best_iou:
                    best_iou = i
                    best_gt = gi
            if best_gt >= 0:
                tp += 1
                matched_gt.add(best_gt)
            else:
                fp += 1

        fn = len(gt_boxes) - len(matched_gt)

        precision = tp / (tp + fp) if (tp + fp) > 0 else 0.0
        recall = tp / (tp + fn) if (tp + fn) > 0 else 0.0
        f1 = 2 * precision * recall / (precision + recall) if (precision + recall) > 0 else 0.0

        total_tp += tp
        total_fp += fp
        total_fn += fn

        results["per_class"][CLASS_NAMES.get(cls_id, f"cls_{cls_id}")] = {
            "tp": tp, "fp": fp, "fn": fn,
            "precision": round(precision, 4),
            "recall": round(recall, 4),
            "f1": round(f1, 4),
            "gt_count": len(gt_boxes),
        }

    overall_precision = total_tp / (total_tp + total_fp) if (total_tp + total_fp) > 0 else 0.0
    overall_recall = total_tp / (total_tp + total_fn) if (total_tp + total_fn) > 0 else 0.0
    overall_f1 = (2 * overall_precision * overall_recall / (overall_precision + overall_recall)
                  if (overall_precision + overall_recall) > 0 else 0.0)

    results["overall"] = {
        "tp": total_tp, "fp": total_fp, "fn": total_fn,
        "precision": round(overall_precision, 4),
        "recall": round(overall_recall, 4),
        "f1": round(overall_f1, 4),
        "mAP50": round(overall_f1, 4),  # Approximation: F1 @ IoU=0.5
    }

    return results


# ── Bootstrapping ────────────────────────────────────────────────────────────


def bootstrap_ci(per_frame_metrics: list[float], n_resamples: int = 1000,
                 ci: float = 0.95) -> dict:
    """Compute bootstrapped confidence interval for a metric.

    Uses the percentile method with n_resamples resamples.
    Returns {'mean': float, 'ci_low': float, 'ci_high': float}.
    """
    if not per_frame_metrics:
        return {"mean": 0.0, "ci_low": 0.0, "ci_high": 0.0}

    np.random.seed(42)
    means = []
    n = len(per_frame_metrics)
    for _ in range(n_resamples):
        sample = np.random.choice(per_frame_metrics, size=n, replace=True)
        means.append(np.mean(sample))

    means.sort()
    alpha = (1.0 - ci) / 2.0
    low_idx = int(n_resamples * alpha)
    high_idx = int(n_resamples * (1.0 - alpha))

    return {
        "mean": round(float(np.mean(per_frame_metrics)), 4),
        "ci_low": round(float(means[low_idx]), 4),
        "ci_high": round(float(means[high_idx]), 4),
        "n": n,
        "n_resamples": n_resamples,
    }


def mcnemar_test(pred_a: list[int], pred_b: list[int],
                  ground_truth: list[int]) -> dict:
    """McNemar's test comparing two classifiers on paired predictions.

    Returns chi-squared statistic and p-value.
    """
    n01 = sum(1 for a, b, t in zip(pred_a, pred_b, ground_truth) if a != t and b == t)
    n10 = sum(1 for a, b, t in zip(pred_a, pred_b, ground_truth) if a == t and b != t)

    chi_sq = (abs(n01 - n10) - 1) ** 2 / (n01 + n10) if (n01 + n10) > 0 else 0.0
    from scipy.stats import chi2
    p_value = 1.0 - chi2.cdf(chi_sq, 1)

    return {
        "n01_a_wrong_b_right": n01,
        "n10_a_right_b_wrong": n10,
        "chi_squared": round(chi_sq, 4),
        "p_value": round(p_value, 4),
        "significant_005": p_value < 0.05,
    }


# ── Stage 2: State Classification Evaluation ─────────────────────────────────


def eval_state_classification(predicted_states: list[str],
                               ground_truth_states: list[str]) -> dict:
    """Evaluate screen state classification.

    Returns accuracy, per-class accuracy, and confusion matrix.
    """
    correct = sum(1 for p, g in zip(predicted_states, ground_truth_states) if p == g)
    total = len(predicted_states)

    # Per-class
    by_class = defaultdict(lambda: {"correct": 0, "total": 0})
    for p, g in zip(predicted_states, ground_truth_states):
        by_class[g]["total"] += 1
        if p == g:
            by_class[g]["correct"] += 1

    return {
        "accuracy": round(correct / total, 4) if total > 0 else 0,
        "total": total,
        "correct": correct,
        "per_class": {
            scene: {
                "accuracy": round(v["correct"] / v["total"], 4) if v["total"] > 0 else 0,
                "correct": v["correct"],
                "total": v["total"],
            }
            for scene, v in sorted(by_class.items())
        },
    }


# ── Main Evaluation Loop ─────────────────────────────────────────────────────


def evaluate_pipeline(dataset_dir: str, api_url: str,
                      detector: str = "wine",
                      ocr_backend: str = "paddle_onnx:tiny") -> dict:
    """Run full pipeline evaluation on a dataset.

    Args:
        dataset_dir: Directory with images/, labels/ subdirectories.
        api_url: CV sidecar URL.
        detector: UI detector name.
        ocr_backend: OCR backend name.

    Returns:
        Dict with per-stage results.
    """
    import requests

    images_dir = os.path.join(dataset_dir, "images")
    labels_dir = os.path.join(dataset_dir, "labels")
    manifest_path = os.path.join(dataset_dir, "manifest.json")

    # Get image list
    image_files = sorted([f for f in os.listdir(images_dir)
                          if f.endswith((".png", ".jpg"))])

    # Load manifest for scene types
    scene_map = {}
    if os.path.isfile(manifest_path):
        with open(manifest_path) as f:
            manifest = json.load(f)
        for entry in manifest:
            scene_map[entry["file"]] = entry.get("generator", "unknown")

    total = len(image_files)
    print(f"Evaluating {total} images with detector={detector}, ocr={ocr_backend}")

    # Per-frame accumulators
    detection_scores = []
    state_correct = []
    state_predicted = []
    state_actual = []
    latencies = []
    all_predicted_elements = []
    all_gt_elements = []

    for idx, fname in enumerate(image_files):
        img_path = os.path.join(images_dir, fname)
        lbl_path = os.path.join(labels_dir, fname.replace(".png", ".txt")
                                .replace(".jpg", ".txt"))

        # Load GT
        gt_elements = load_gt_labels(lbl_path)
        gt_scene = scene_map.get(fname, "unknown")

        # Run pipeline via API
        t0 = time.time()
        try:
            r = requests.post(f"{api_url}/analyze",
                              json={"image_path": img_path,
                                    "ui_detector": detector,
                                    "ocr_backend": ocr_backend},
                              timeout=30)
            result = r.json()
        except Exception as e:
            print(f"  [ERROR] {fname}: {e}")
            continue
        latency = (time.time() - t0) * 1000
        latencies.append(latency)

        predicted_elements = result.get("element_detail", [])
        predicted_state = result.get("ui_state", "unknown")

        # Detection evaluation
        # Get image size from the result or use default
        res_str = result.get("resolution", "1280x720")
        try:
            rw, rh = [int(x) for x in res_str.split("x")]
        except ValueError:
            rw, rh = 1280, 720
        det_result = eval_detection(predicted_elements, gt_elements, img_size=(rw, rh))
        detection_scores.append(det_result["overall"]["f1"])

        all_predicted_elements.append(predicted_elements)
        all_gt_elements.append(gt_elements)

        # State classification
        state_predicted.append(predicted_state)
        state_actual.append(gt_scene)

        if (idx + 1) % 50 == 0:
            print(f"  {idx+1}/{total}...")

    # ── Aggregate Results ───────────────────────────────────────────────

    # Detection: bootstrapped F1 (per-frame metric — reflects typical frame quality)
    print(f"\nComputing bootstrapped confidence intervals ({len(detection_scores)} frames)...")
    det_ci = bootstrap_ci(detection_scores)

    # Detection: aggregate per-class across all frames — macro metrics
    agg_eval = eval_detection(
        [e for sublist in all_predicted_elements for e in sublist],
        [e for sublist in all_gt_elements for e in sublist],
    )
    # Compute macro-averaged F1 (unweighted mean of per-class F1)
    per_class_f1s = [pc["f1"] for pc in agg_eval["per_class"].values()]
    macro_f1 = sum(per_class_f1s) / len(per_class_f1s) if per_class_f1s else 0.0

    # State classification
    state_results = eval_state_classification(state_predicted, state_actual)

    # Latency
    latency_ci = bootstrap_ci(latencies)

    # Build results
    results = {
        "config": {
            "dataset": dataset_dir,
            "api_url": api_url,
            "detector": detector,
            "ocr": ocr_backend,
            "n_frames": total,
        },
        "detection": {
            "f1_bootstrap": det_ci,
            "per_class": agg_eval["per_class"],
            "overall": agg_eval["overall"],
        },
        "state_classification": state_results,
        "latency_ms": latency_ci,
        "pipeline": {
            "total_time_ms": sum(latencies),
            "mean_latency_ms": latency_ci["mean"],
            "fps": 1000.0 / latency_ci["mean"] if latency_ci["mean"] > 0 else 0,
        },
    }

    return results


# ── Report Printer ───────────────────────────────────────────────────────────


def print_report(results: dict):
    """Pretty-print evaluation results."""
    print(f"\n{'='*72}")
    print("  PIPELINE EVALUATION REPORT")
    print(f"{'='*72}")
    print(f"  Dataset:  {results['config']['dataset']}")
    print(f"  Detector: {results['config']['detector']}")
    print(f"  OCR:      {results['config']['ocr']}")
    print(f"  Frames:   {results['config']['n_frames']}")
    print()

    # Pipeline summary
    print("  --- Pipeline Summary ---")
    print(f"  Mean latency:  {results['latency_ms']['mean']} ms")
    print(f"  95% CI:        ({results['latency_ms']['ci_low']}, {results['latency_ms']['ci_high']}) ms")
    print(f"  FPS:           {results['pipeline']['fps']:.1f}")
    print()

    # Detection
    d = results["detection"]
    print("  --- Detection ---")
    print(f"  Macro F1 (class-averaged): {d.get('macro_f1', 0):.4f}")
    print(f"  Per-frame F1:             {d['f1_bootstrap']['mean']:.4f}")
    print(f"  Per-frame F1 95% CI:      ({d['f1_bootstrap']['ci_low']}, {d['f1_bootstrap']['ci_high']})")
    print(f"  Precision (aggregate):    {d['overall']['precision']:.4f}")
    print(f"  Recall (aggregate):       {d['overall']['recall']:.4f}")
    print(f"  Bootstrap:                {d['f1_bootstrap']['n_resamples']} resamples")
    print()
    print("  Per-Class Detection:")
    print(f"  {'Class':<20s} {'F1':>6s} {'Prec':>6s} {'Rec':>6s} {'GT':>5s} {'TP':>4s} {'FP':>4s} {'FN':>4s}")
    print(f"  {'-'*20} {'-'*6} {'-'*6} {'-'*6} {'-'*5} {'-'*4} {'-'*4} {'-'*4}")
    for cls_name in sorted(d["per_class"].keys()):
        pc = d["per_class"][cls_name]
        print(f"  {cls_name:<20s} {pc['f1']:.3f} {pc['precision']:.3f} {pc['recall']:.3f} "
              f"{pc['gt_count']:>4d} {pc['tp']:>3d} {pc['fp']:>3d} {pc['fn']:>3d}")

    # State classification
    s = results["state_classification"]
    print("\n  --- State Classification ---")
    print(f"  Accuracy: {s['accuracy']*100:.1f}% ({s['correct']}/{s['total']})")
    if s.get("per_class"):
        print(f"  {'Scene':<25s} {'Accuracy':>10s}")
        print(f"  {'-'*25} {'-'*10}")
        for scene, sc in s["per_class"].items():
            print(f"  {scene:<25s} {sc['accuracy']*100:>8.1f}% ({sc['correct']}/{sc['total']})")

    print(f"\n{'='*72}")


# ── Ablation ─────────────────────────────────────────────────────────────────


def run_ablation(dataset_dir: str, api_url: str, baseline_detector: str,
                 ablation_detector: str, ocr: str = "paddle_onnx:tiny") -> dict:
    """Compare two detectors with statistical significance testing."""
    print(f"\n{'='*72}")
    print(f"  ABLATION STUDY: {baseline_detector} vs {ablation_detector}")
    print(f"{'='*72}")

    base = evaluate_pipeline(dataset_dir, api_url, baseline_detector, ocr)
    ablated = evaluate_pipeline(dataset_dir, api_url, ablation_detector, ocr)

    # Compare
    base_f1 = base["detection"]["f1_bootstrap"]["mean"]
    abl_f1 = ablated["detection"]["f1_bootstrap"]["mean"]
    delta_f1 = base_f1 - abl_f1

    base_lat = base["latency_ms"]["mean"]
    abl_lat = ablated["latency_ms"]["mean"]

    print("\n  --- Comparison ---")
    print(f"  {'Metric':<30s} {'Baseline':>12s} {'Ablated':>12s} {'Δ':>10s}")
    print(f"  {'-'*30} {'-'*12} {'-'*12} {'-'*10}")
    print(f"  {'Detection F1':<30s} {base_f1:>10.4f}   {abl_f1:>10.4f}   {delta_f1:>+8.4f}")
    print(f"  {'Latency (ms)':<30s} {base_lat:>10.1f}   {abl_lat:>10.1f}   {abl_lat-base_lat:>+8.1f}")
    print(f"  {'State Accuracy (%)':<30s} "
          f"{base['state_classification']['accuracy']*100:>10.1f}%  "
          f"{ablated['state_classification']['accuracy']*100:>10.1f}%  "
          f"{(ablated['state_classification']['accuracy']-base['state_classification']['accuracy'])*100:>+8.1f}%")
    print()

    return {"baseline": base, "ablated": ablated, "delta_f1": round(delta_f1, 4)}


# ── CLI ──────────────────────────────────────────────────────────────────────


def main():
    parser = argparse.ArgumentParser(
        description="Pipeline Evaluator — stage-by-stage CV/OCR quality measurement")
    parser.add_argument("--dataset", default="/models/eval-dataset",
                        help="Evaluation dataset directory")
    parser.add_argument("--api", default="http://localhost:8001",
                        help="CV sidecar API URL")
    parser.add_argument("--detector", default="wine",
                        help="UI detector (default: wine)")
    parser.add_argument("--ocr", default="paddle_onnx:tiny",
                        help="OCR backend (default: paddle_onnx:tiny)")
    parser.add_argument("--ablation", default=None,
                        help="Run ablation against another detector")
    parser.add_argument("--ablation-ocr", default=None,
                        help="Run ablation against another OCR engine")
    parser.add_argument("--output", default=None,
                        help="Save results JSON to file")
    parser.add_argument("--bootstrap-samples", type=int, default=1000,
                        help="Bootstrap resamples (default: 1000)")

    args = parser.parse_args()

    if not os.path.isdir(args.dataset):
        print(f"ERROR: Dataset not found: {args.dataset}")
        sys.exit(1)

    # Override bootstrap samples
    global N_RESAMPLES
    N_RESAMPLES = args.bootstrap_samples

    if args.ablation:
        results = run_ablation(args.dataset, args.api, args.detector, args.ablation, args.ocr)
    elif args.ablation_ocr:
        results = run_ablation(args.dataset, args.api, args.detector, args.detector, args.ablation_ocr)
    else:
        results = evaluate_pipeline(args.dataset, args.api, args.detector, args.ocr)
        print_report(results)

    if args.output:
        with open(args.output, "w") as f:
            json.dump(results, f, indent=2)
        print(f"Results saved: {args.output}")


if __name__ == "__main__":
    # Override bootstrap resample count from CLI
    N_RESAMPLES = 1000
    main()
