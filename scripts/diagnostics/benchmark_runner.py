#!/usr/bin/env python3
"""Statistically rigorous benchmark harness for CV/OCR engine evaluation.

Runs multi-engine, multi-iteration benchmarks with warmup, confidence intervals,
and per-frame timing. Designed for reliable performance comparison.

Usage:
  python3 scripts/diagnostics/benchmark_runner.py \
    --frames /path/to/frames/ \
    --output /path/to/results.json \
    --warmup 3 --iterations 10 --confidence 0.95
"""

import argparse
import json
import os
import sys
import time
from datetime import UTC, datetime
from pathlib import Path

import cv2
import numpy as np

# Inject scripts dir for engine imports
sys.path.insert(0, str(Path(__file__).resolve().parent))
from winebot_cv.ocr.engines import available_backends, get_ocr_engine
from winebot_cv.detectors.engines import available_detectors, get_ui_detector


def compute_stats(times: list[float], confidence: float = 0.95) -> dict:
    """Compute statistical summary of timing data.

    Returns mean, stddev, min, max, median, p95, p99, and bootstrap CI.
    """
    arr = np.array(times)
    n = len(arr)

    if n < 3:
        return {
            "mean_ms": float(np.mean(arr)) if n else 0,
            "std_ms": float(np.std(arr)) if n > 1 else 0,
            "min_ms": float(np.min(arr)) if n else 0,
            "max_ms": float(np.max(arr)) if n else 0,
            "p50_ms": float(np.median(arr)) if n else 0,
            "p95_ms": 0, "p99_ms": 0,
            "ci95_low": 0, "ci95_high": 0,
            "n": n,
        }

    # Bootstrap confidence interval
    try:
        from scipy import stats as sp_stats
        # Use t-distribution CI (more accurate for small n)
        mean = np.mean(arr)
        sem = sp_stats.sem(arr)
        ci_low, ci_high = sp_stats.t.interval(confidence, df=n - 1, loc=mean, scale=sem)
    except ImportError:
        # Fallback: normal approximation
        mean = np.mean(arr)
        std = np.std(arr, ddof=1)
        z = 1.96  # for 95% CI
        margin = z * std / np.sqrt(n)
        ci_low, ci_high = mean - margin, mean + margin

    return {
        "mean_ms": float(np.mean(arr)),
        "std_ms": float(np.std(arr, ddof=1)),
        "min_ms": float(np.min(arr)),
        "max_ms": float(np.max(arr)),
        "p50_ms": float(np.median(arr)),
        "p95_ms": float(np.percentile(arr, 95)),
        "p99_ms": float(np.percentile(arr, 99)),
        "ci95_low": round(float(ci_low), 1),
        "ci95_high": round(float(ci_high), 1),
        "n": n,
    }


def compute_ocr_accuracy(detected_texts: list[str], expected_texts: list[str]) -> dict:
    """Compute OCR accuracy metrics against ground truth."""
    if not expected_texts:
        return {"precision": 0, "recall": 0, "f1": 0, "note": "no_ground_truth"}

    detected_lower = set(t.lower() for t in detected_texts)
    expected_lower = set(t.lower() for t in expected_texts)

    # Fuzzy match: also count partial matches
    partial_matches = 0
    for exp in expected_lower:
        for det in detected_lower:
            if exp in det or det in exp:
                partial_matches += 1
                break

    true_positives = len(detected_lower & expected_lower) + partial_matches
    precision = true_positives / max(len(detected_lower), 1)
    recall = true_positives / max(len(expected_lower), 1)
    f1 = 2 * precision * recall / max(precision + recall, 0.001)

    return {
        "precision": round(precision, 3),
        "recall": round(recall, 3),
        "f1": round(f1, 3),
        "detected_count": len(detected_texts),
        "expected_count": len(expected_texts),
        "true_positives": true_positives,
    }


def compute_detection_metrics(detected_elements: list[dict],
                               expected_elements: list[dict]) -> dict:
    """Compute UI element detection accuracy using IoU matching."""
    if not expected_elements:
        return {"precision": 0, "recall": 0, "f1": 0, "note": "no_ground_truth"}

    def iou(box_a, box_b):
        """Intersection over Union of two bounding boxes."""
        xa1, ya1, wa, ha = box_a
        xa2, ya2 = xa1 + wa, ya1 + ha
        xb1, yb1, wb, hb = box_b
        xb2, yb2 = xb1 + wb, yb1 + hb

        xi1 = max(xa1, xb1)
        yi1 = max(ya1, yb1)
        xi2 = min(xa2, xb2)
        yi2 = min(ya2, yb2)

        inter = max(0, xi2 - xi1) * max(0, yi2 - yi1)
        area_a = wa * ha
        area_b = wb * hb
        union = area_a + area_b - inter

        return inter / max(union, 1)

    matches = 0
    matched_det = set()
    matched_exp = set()

    for di, det in enumerate(detected_elements):
        for ei, exp in enumerate(expected_elements):
            if ei in matched_exp:
                continue
            if iou(det.get("bbox", [0, 0, 0, 0]), exp.get("bbox", [0, 0, 0, 0])) > 0.5:
                matches += 1
                matched_det.add(di)
                matched_exp.add(ei)
                break

    precision = matches / max(len(detected_elements), 1)
    recall = matches / max(len(expected_elements), 1)
    f1 = 2 * precision * recall / max(precision + recall, 0.001)

    return {
        "precision": round(precision, 3),
        "recall": round(recall, 3),
        "f1": round(f1, 3),
        "iou_matches": matches,
        "detected_count": len(detected_elements),
        "expected_count": len(expected_elements),
    }


def load_manifest(frames_dir: str) -> dict | None:
    """Load ground truth manifest if present."""
    manifest_path = os.path.join(frames_dir, "manifest.json")
    if os.path.exists(manifest_path):
        with open(manifest_path, encoding="utf-8") as f:
            return json.load(f)
    return None


def run_benchmark(frames_dir: str,
                  engines: list[dict[str, str]],
                  warmup_frames: int = 3,
                  iterations: int = 10,
                  confidence: float = 0.95,
                  max_frames: int | None = None) -> dict:
    """Run full benchmark matrix.

    Args:
        frames_dir: Directory containing PNG frame files.
        engines: List of {"ui_detector": str, "ocr_backend": str} dicts.
        warmup_frames: Number of frames to discard per engine combo (CUDA warmup).
        iterations: Number of runs per frame per engine combo.
        confidence: Confidence level for CI computation (0.0-1.0).
        max_frames: Limit number of frames (None = all).

    Returns:
        Dict with benchmark_id, config, results per engine, and comparison summary.
    """
    # Load ground truth
    manifest = load_manifest(frames_dir)

    # Discover frames
    all_frames = sorted([
        f for f in os.listdir(frames_dir)
        if f.lower().endswith(('.png', '.jpg', '.jpeg'))
        and os.path.isfile(os.path.join(frames_dir, f))
    ])
    if max_frames:
        all_frames = all_frames[:max_frames]

    if not all_frames:
        print("ERROR: No frame files found", file=sys.stderr)
        sys.exit(1)

    # Separate warmup frames
    warmup_list = all_frames[:warmup_frames]
    bench_frames = all_frames[warmup_frames:]
    total_warmup = len(warmup_list)
    total_bench = len(bench_frames)

    print(f"Frames found: {len(all_frames)} total")
    print(f"  Warmup: {total_warmup} frames (discarded)")
    print(f"  Bench:  {total_bench} frames x {iterations} iterations")
    print(f"  Engines: {len(engines)} combos")
    print(f"  Total runs: {len(engines) * total_warmup + len(engines) * total_bench * iterations}")
    print()

    benchmark_id = f"bench-{datetime.now(UTC).strftime('%Y%m%d-%H%M%S')}"
    results = []

    for engine_idx, engine_def in enumerate(engines):
        ui_name = engine_def.get("ui_detector", "contour")
        ocr_name = engine_def.get("ocr_backend", "tesseract")
        engine_label = f"{ui_name}+{ocr_name}"

        print(f"[{engine_idx + 1}/{len(engines)}] {engine_label} ...")

        # Initialize engines once
        try:
            detector = get_ui_detector(ui_name)
            ocr = get_ocr_engine(ocr_name)
        except Exception as e:
            print(f"  SKIP: Engine init failed: {e}")
            results.append({
                "engine": engine_def,
                "error": str(e),
                "available": False,
            })
            continue

        engine_available = detector.available and ocr.available
        if not engine_available:
            print(f"  SKIP: detector available={detector.available}, ocr available={ocr.available}")

        # ── Warmup phase ────────────────────────────────────────────────
        warmup_start = time.time()
        for frame_file in warmup_list:
            frame_path = os.path.join(frames_dir, frame_file)
            img = cv2.imread(frame_path)
            if img is None:
                continue
            if engine_available:
                detector.detect(img)
                ocr.detect_text(img)
        warmup_elapsed = (time.time() - warmup_start) * 1000
        print(f"  Warmup: {total_warmup} frames in {warmup_elapsed:.0f}ms")

        # ── Benchmark phase ─────────────────────────────────────────────
        per_frame_data = []
        all_times = []
        total_ui = 0
        total_ocr_regions = 0
        total_interactive = 0

        for frame_file in bench_frames:
            frame_path = os.path.join(frames_dir, frame_file)
            img = cv2.imread(frame_path)
            if img is None:
                continue

            frame_times = []
            ui_elements = 0
            ocr_regions = 0
            interactive = 0

            for _run_i in range(iterations):
                t0 = time.time()

                if engine_available:
                    elements = detector.detect(img)
                    ocr_texts = ocr.detect_text(img)
                    ui_elements = len(elements)
                    interactive = sum(1 for e in elements if e.get("interactive"))
                    ocr_regions = len(ocr_texts)
                else:
                    elements = []
                    ocr_texts = []

                elapsed = (time.time() - t0) * 1000
                frame_times.append(elapsed)

            # Stats for this frame
            frame_stats = compute_stats(frame_times, confidence)
            frame_stats["frame"] = frame_file
            frame_stats["ui_elements"] = ui_elements
            frame_stats["interactive_elements"] = interactive
            frame_stats["ocr_regions"] = ocr_regions
            per_frame_data.append(frame_stats)

            all_times.extend(frame_times)
            total_ui += ui_elements
            total_ocr_regions += ocr_regions
            total_interactive += interactive

        # ── Aggregate statistics ─────────────────────────────────────────
        agg_stats = compute_stats(all_times, confidence)
        n_bench_frames = len(bench_frames)
        total_time_s = sum(all_times) / 1000

        engine_result = {
            "engine": engine_def,
            "available": engine_available,
            "summary": {
                **agg_stats,
                "total_s": round(total_time_s, 2),
                "frames_processed": n_bench_frames * iterations,
                "benchmark_frames": n_bench_frames,
                "iterations_per_frame": iterations,
                "warmup_frames": total_warmup,
                "mean_ui_elements": round(total_ui / max(n_bench_frames, 1), 1),
                "mean_interactive": round(total_interactive / max(n_bench_frames, 1), 1),
                "mean_ocr_regions": round(total_ocr_regions / max(n_bench_frames, 1), 1),
                "effective_fps": round(n_bench_frames * iterations / max(total_time_s, 0.001), 1),
            },
            "per_frame": per_frame_data,
        }

        # ── Accuracy vs ground truth (if manifest available) ─────────────
        if manifest and engine_available:
            # Compute accuracy on first frame only (all synthetic images share manifest)
            # For the manifest-based dataset, each image has its own ground truth
            acc_frame = bench_frames[0] if bench_frames else None
            if acc_frame:
                frame_path = os.path.join(frames_dir, acc_frame)
                img = cv2.imread(frame_path)
                if img is not None:
                    elements = detector.detect(img)
                    texts = ocr.detect_text(img)

                    # Find ground truth for this frame
                    image_name = os.path.splitext(acc_frame)[0]
                    gt_entry = None
                    for entry in manifest.get("images", []):
                        if entry["name"] == image_name:
                            gt_entry = entry
                            break

                    if gt_entry:
                        gt = gt_entry["ground_truth"]
                        detected_texts = [r.get("text", "") for r in texts]
                        engine_result["accuracy"] = {
                            "ocr": compute_ocr_accuracy(
                                detected_texts, gt.get("expected_text", [])
                            ),
                            "detection": compute_detection_metrics(
                                elements, gt.get("expected_elements", [])
                            ),
                        }

        results.append(engine_result)

        print(f"  Result: {agg_stats['mean_ms']:.0f}ms avg "
              f"(CI95: {agg_stats['ci95_low']:.0f}–{agg_stats['ci95_high']:.0f}ms), "
              f"{agg_stats['p95_ms']:.0f}ms p95, "
              f"{engine_result['summary']['effective_fps']:.1f} fps")

    # ── Comparative summary ────────────────────────────────────────────
    available_results = [r for r in results if r.get("available")]
    if len(available_results) >= 2:
        # Find fastest
        fastest = min(available_results, key=lambda r: r["summary"]["mean_ms"])
        print(f"\n  Fastest: {fastest['engine']['ui_detector']}+{fastest['engine']['ocr_backend']} "
              f"({fastest['summary']['mean_ms']:.0f}ms)")

        # Find most elements detected
        if available_results:
            most_elements = max(available_results, key=lambda r: r["summary"]["mean_ui_elements"])
            print(f"  Most elements: {most_elements['engine']['ui_detector']}+"
                  f"{most_elements['engine']['ocr_backend']} "
                  f"({most_elements['summary']['mean_ui_elements']:.1f} elem/frame)")

        # Find most accurate
        acc_results = [r for r in available_results if "accuracy" in r]
        if acc_results:
            best_ocr = max(acc_results, key=lambda r: r["accuracy"]["ocr"]["f1"])
            best_det = max(acc_results, key=lambda r: r["accuracy"]["detection"]["f1"])
            print(f"  Best OCR: {best_ocr['engine']['ui_detector']}+"
                  f"{best_ocr['engine']['ocr_backend']} "
                  f"(F1={best_ocr['accuracy']['ocr']['f1']:.3f})")
            print(f"  Best Detection: {best_det['engine']['ui_detector']}+"
                  f"{best_det['engine']['ocr_backend']} "
                  f"(F1={best_det['accuracy']['detection']['f1']:.3f})")

    return {
        "benchmark_id": benchmark_id,
        "timestamp_utc": datetime.now(UTC).isoformat(),
        "config": {
            "frames_dir": frames_dir,
            "total_frames": len(all_frames),
            "warmup_frames": warmup_frames,
            "benchmark_frames": total_bench,
            "iterations": iterations,
            "confidence": confidence,
        },
        "engines_tested": len(engines),
        "engines_available": len(available_results),
        "results": results,
    }


def main():
    parser = argparse.ArgumentParser(
        description="WineBot CV/OCR Benchmark Runner — statistically rigorous engine comparison"
    )
    parser.add_argument("--frames", required=True,
                        help="Directory containing benchmark PNG frames")
    parser.add_argument("--output", default="",
                        help="Output JSON file (default: prints to stdout)")
    parser.add_argument("--warmup", type=int, default=3,
                        help="Warmup frames to discard per engine (default: 3)")
    parser.add_argument("--iterations", type=int, default=10,
                        help="Runs per frame per engine (default: 10)")
    parser.add_argument("--confidence", type=float, default=0.95,
                        help="Confidence level for CI (default: 0.95)")
    parser.add_argument("--max-frames", type=int, default=0,
                        help="Max benchmark frames (0=all)")
    parser.add_argument("--engine", action="append",
                        help="Engine combo: ui_detector:ocr_backend (repeatable)")
    parser.add_argument("--all-engines", action="store_true",
                        help="Benchmark all available engine combos")

    args = parser.parse_args()

    if not os.path.isdir(args.frames):
        print(f"ERROR: frames directory not found: {args.frames}", file=sys.stderr)
        sys.exit(1)

    # Build engine list
    if args.all_engines:
        detectors = [k for k, v in available_detectors().items() if v]
        ocr_backends = [k for k, v in available_backends().items() if v]
        engines = [
            {"ui_detector": d, "ocr_backend": o}
            for d in detectors for o in ocr_backends
        ]
    elif args.engine:
        engines = []
        for e in args.engine:
            parts = e.split(":", 1)
            engines.append({
                "ui_detector": parts[0] if len(parts) > 0 else "contour",
                "ocr_backend": parts[1] if len(parts) > 1 else "tesseract",
            })
    else:
        # Default: baseline combos
        engines = [
            {"ui_detector": "contour", "ocr_backend": "tesseract"},
            {"ui_detector": "yolo", "ocr_backend": "tesseract"},
        ]

    max_frames = args.max_frames if args.max_frames > 0 else None

    print("=" * 70)
    print("  WineBot CV/OCR Benchmark Runner")
    print("=" * 70)
    print(f"  Frames dir:  {args.frames}")
    print(f"  Warmup:      {args.warmup} frames/engine")
    print(f"  Iterations:  {args.iterations}/frame/engine")
    print(f"  Confidence:  {args.confidence * 100:.0f}%")
    print()

    result = run_benchmark(
        frames_dir=args.frames,
        engines=engines,
        warmup_frames=args.warmup,
        iterations=args.iterations,
        confidence=args.confidence,
        max_frames=max_frames,
    )

    # Output
    if args.output:
        os.makedirs(os.path.dirname(args.output) or ".", exist_ok=True)
        with open(args.output, "w", encoding="utf-8") as f:
            json.dump(result, f, indent=2)
        print(f"\nResults saved to: {args.output}")
    else:
        print("\n" + json.dumps(result, indent=2))

    # Exit non-zero if any engine unavailable
    if result["engines_available"] == 0:
        print("\nERROR: No engines available", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()
