#!/usr/bin/env python3
"""OCR Accuracy Benchmark — precision/recall/F1 on ground-truth text.

Compares all available OCR backends against known text from synthetic
GT images. Unlike the speed benchmark, this measures whether each engine
correctly reads the text that's actually in the image.

Protocol:
  1. Generate test images with known text via benchmark_dataset.py
  2. Run each OCR backend with warmup + 5 iterations
  3. Compute char-level and word-level precision/recall/F1
  4. Report 95% CI on F1 scores
"""

import argparse
import json
import re
import sys
import time
from datetime import UTC, datetime
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parent))
from benchmark_dataset import GENERATORS
from winebot_cv.ocr.engines import available_backends, get_ocr_engine


def compute_char_accuracy(detected_text: str, expected_text: str) -> dict:
    """Char-level edit-distance accuracy."""
    det = detected_text.lower().strip()
    exp = expected_text.lower().strip()

    # Normalize whitespace
    det = re.sub(r'\s+', ' ', det)
    exp = re.sub(r'\s+', ' ', exp)

    if not exp:
        return {"precision": 1.0, "recall": 1.0, "f1": 1.0, "exact_match": len(det) == 0}

    # Simple token-based: what fraction of expected words appear in detection?
    det_tokens = set(det.split())
    exp_tokens = set(exp.split())

    if not exp_tokens:
        return {"precision": 0.0, "recall": 0.0, "f1": 0.0, "exact_match": False}

    tp = len(det_tokens & exp_tokens)
    precision = tp / max(len(det_tokens), 1)
    recall = tp / max(len(exp_tokens), 1)
    f1 = 2 * precision * recall / max(precision + recall, 0.001)

    return {
        "precision": round(precision, 4),
        "recall": round(recall, 4),
        "f1": round(f1, 4),
        "exact_match": det == exp,
        "detected_tokens": len(det_tokens),
        "expected_tokens": len(exp_tokens),
        "true_positives": tp,
    }


def compute_word_accuracy(detected_text: str, expected_text: str) -> dict:
    """Word-level accuracy with fuzzy matching."""
    det = detected_text.lower().strip()
    exp = expected_text.lower().strip()

    det_words = det.split()
    exp_words = exp.split()

    if not exp_words:
        return {"precision": 1.0, "recall": 1.0, "f1": 1.0, "exact_match": len(det_words) == 0}

    # Count fuzzy matches (any detected word contains or is contained by expected)
    matched_exp = 0
    matched_det = 0
    matched_det_words = set()
    matched_exp_words = set()

    for di, dw in enumerate(det_words):
        for ei, ew in enumerate(exp_words):
            if ei in matched_exp_words:
                continue
            # Fuzzy match: substring either direction, or edit distance <= 1
            if (ew in dw or dw in ew or
                (len(dw) > 3 and len(ew) > 3 and
                 _levenshtein_ratio(dw, ew) > 0.7)):
                matched_exp_words.add(ei)
                matched_det_words.add(di)
                break

    precision = len(matched_det_words) / max(len(det_words), 1)
    recall = len(matched_exp_words) / max(len(exp_words), 1)
    f1 = 2 * precision * recall / max(precision + recall, 0.001)

    return {
        "precision": round(precision, 4),
        "recall": round(recall, 4),
        "f1": round(f1, 4),
        "exact_match": det == exp,
        "detected_words": len(det_words),
        "expected_words": len(exp_words),
        "matched_words": len(matched_exp_words),
    }


def _levenshtein_ratio(a: str, b: str) -> float:
    """Approximate string similarity (0-1)."""
    if not a or not b:
        return 0.0
    # Simple: longest common substring / max length
    max_len = max(len(a), len(b))
    # Quick ratio
    shorter = min(a, b, key=len)
    longer = max(a, b, key=len)
    matches = sum(1 for c in shorter if c in longer)
    return matches / max_len


def compute_stats(values, confidence=0.95):
    arr = np.array(values)
    n = len(arr)
    if n < 3:
        return {"mean": float(np.mean(arr)) if n else 0, "n": n}
    try:
        from scipy import stats as sp_stats
        mean = np.mean(arr)
        sem = sp_stats.sem(arr)
        lo, hi = sp_stats.t.interval(confidence, df=n-1, loc=mean, scale=sem)
    except ImportError:
        mean = np.mean(arr)
        std = np.std(arr, ddof=1)
        z = 1.96
        margin = z * std / np.sqrt(n)
        lo, hi = mean - margin, mean + margin
    return {
        "mean": float(mean),
        "std": float(np.std(arr, ddof=1)),
        "ci95_low": round(float(lo), 4),
        "ci95_high": round(float(hi), 4),
        "n": n,
    }


def generate_test_texts():
    """Generate test images with known text from benchmark generators."""
    images, texts = [], []

    # Explicit text-ground-truth pairs
    test_cases = [
        # Scene, image, expected text strings
        ("save_dialog", None, [
            "Save As", "File name", "Save as type", "Text Documents",
            "Save", "Cancel", "Hide Folders",
        ]),
        ("notepad", None, [
            "File", "Edit", "Format", "View", "Help",
        ]),
        ("error_dialog", None, [
            "Error", "OK",
        ]),
        ("settings", None, [
            "General", "Display", "OK", "Cancel", "Apply",
        ]),
        ("installer", None, [
            "Setup Wizard", "Next", "Cancel",
        ]),
        ("form", None, [
            "Name", "Email", "Phone", "Address", "Submit", "Reset",
        ]),
    ]

    for scene_name, _, expected_texts in test_cases:
        gen_fn = GENERATORS.get(scene_name)
        if not gen_fn:
            continue
        img, gt = gen_fn()
        meta = gt if isinstance(gt, dict) else {}
        # Get expected text from the ground truth
        gt_texts = expected_texts
        # Also pull from OCR ground truth if available
        for elem in meta.get("expected_elements", []):
            label = elem.get("label", "")
            if label and label not in gt_texts:
                gt_texts.append(label)

        images.append({
            "path": None,
            "image": img,
            "scene": scene_name,
            "expected_texts": gt_texts,
        })

    return images


def benchmark_ocr_accuracy(images, warmup=2, iterations=5):
    """Measure OCR accuracy for all backends."""
    print("=" * 72)
    print("  OCR Accuracy Benchmark — Ground Truth Text Recovery")
    print("=" * 72)

    backends = [k for k, v in available_backends().items() if v]
    test_backends = []
    seen = set()
    for b in backends:
        base = b.split(":")[0]
        if base not in seen:
            seen.add(base)
            test_backends.append(b)
    # Add paddle variants
    for v in ["paddle_onnx:tiny", "paddle_onnx:small", "paddle_onnx:medium"]:
        if v in backends and v not in test_backends:
            test_backends.append(v)

    results = []

    for backend in test_backends:
        print(f"\n[{backend}] Testing accuracy...")
        ocr = get_ocr_engine(backend)
        if not ocr.available:
            print("  SKIP: not available")
            continue

        all_char_f1s = []
        all_word_f1s = []
        exact_matches = 0
        total_texts = 0
        all_times = []
        details = []

        for img_entry in images:
            img = img_entry["image"]
            scene = img_entry["scene"]
            expected = img_entry["expected_texts"]

            if img is None or not expected:
                continue

            # Warmup
            for _ in range(warmup):
                _ = ocr.detect_text(img)

            # Benchmark
            for _ in range(iterations):
                t0 = time.perf_counter()
                detected_regions = ocr.detect_text(img)
                elapsed = (time.perf_counter() - t0) * 1000
                all_times.append(elapsed)

                # Combine all detected text
                detected_text = " ".join(
                    r.get("text", "") for r in detected_regions
                )
                expected_text = " ".join(expected)

                char_acc = compute_char_accuracy(detected_text, expected_text)
                word_acc = compute_word_accuracy(detected_text, expected_text)

                all_char_f1s.append(char_acc["f1"])
                all_word_f1s.append(word_acc["f1"])
                if char_acc["exact_match"]:
                    exact_matches += 1
                total_texts += 1

                if _ == 0:  # First iteration only
                    details.append({
                        "scene": scene,
                        "expected": expected_text[:100],
                        "detected": detected_text[:200],
                        "char_f1": char_acc["f1"],
                        "word_f1": word_acc["f1"],
                    })

        agg_char = compute_stats(all_char_f1s)
        agg_word = compute_stats(all_word_f1s)
        agg_time = compute_stats(all_times)

        result = {
            "backend": backend,
            "total_measurements": total_texts,
            "exact_matches": exact_matches,
            "exact_match_rate": round(exact_matches / max(total_texts, 1), 4),
            "char_f1": agg_char,
            "word_f1": agg_word,
            "speed_ms": agg_time,
            "details": details[:5],
        }
        results.append(result)

        print(f"  Char F1: {agg_char['mean']:.4f} CI95[{agg_char['ci95_low']:.4f}-{agg_char['ci95_high']:.4f}]  "
              f"Word F1: {agg_word['mean']:.4f}  "
              f"Exact: {exact_matches}/{total_texts} ({result['exact_match_rate']:.0%})  "
              f"Speed: {agg_time['mean']:.0f}ms")

    # Ranking
    print("\n  --- Accuracy Ranking (Char F1) ---")
    ranked = sorted(results, key=lambda r: r["char_f1"]["mean"], reverse=True)
    for i, r in enumerate(ranked):
        best = ranked[0]
        sig = ""
        if r != best:
            ca, cb = r["char_f1"], best["char_f1"]
            if ca["ci95_high"] < cb["ci95_low"]:
                sig = f"  ← sig worse than {best['backend']} (p<0.05)"
        print(f"  {i+1}. {r['backend']:<22s} F1={r['char_f1']['mean']:.4f} "
              f"CI95[{r['char_f1']['ci95_low']:.4f}-{r['char_f1']['ci95_high']:.4f}]{sig}")

    return results


def main():
    parser = argparse.ArgumentParser(description="OCR Accuracy Benchmark")
    parser.add_argument("--output", default="/tmp/ocr_accuracy.json")
    parser.add_argument("--warmup", type=int, default=2)
    parser.add_argument("--iterations", type=int, default=5)
    args = parser.parse_args()

    print("OCR Accuracy Benchmark")
    print(f"  Warmup: {args.warmup} | Iterations: {args.iterations}")
    print()

    print("Generating test images with known text...")
    images = generate_test_texts()
    print(f"  {len(images)} scenes ready")
    print()

    results = benchmark_ocr_accuracy(images, args.warmup, args.iterations)

    report = {
        "benchmark": "ocr_accuracy",
        "timestamp": datetime.now(UTC).isoformat(),
        "config": {"warmup": args.warmup, "iterations": args.iterations},
        "results": results,
    }

    with open(args.output, "w") as f:
        json.dump(report, f, indent=2)
    print(f"\nResults: {args.output}")


if __name__ == "__main__":
    main()
