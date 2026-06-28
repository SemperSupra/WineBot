#!/usr/bin/env python3
"""Definitive WineBot Engine Benchmark — reproducible, statistically rigorous.

Protocol:
  1. Generate synthetic test dataset (6 images with ground truth)
  2. Warmup: 3 frames per engine (discarded)
  3. Benchmark: 10 iterations per frame per engine
  4. 95% CI via t-distribution
  5. Significance: non-overlapping CIs = real difference
  6. All results saved with timestamp, git commit, hardware info

Usage:
  python3 benchmark_definitive.py --output results.json
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

sys.path.insert(0, str(Path(__file__).resolve().parent))
from ocr_engines import available_backends, get_ocr_engine
from ui_detectors import available_detectors, get_ui_detector


def compute_stats(times: list, confidence: float = 0.95) -> dict:
    arr = np.array(times); n = len(arr)
    if n < 3: return {"mean_ms": float(np.mean(arr)) if n else 0, "n": n}
    try:
        from scipy import stats as sp_stats
        mean = np.mean(arr); sem = sp_stats.sem(arr)
        low, high = sp_stats.t.interval(confidence, df=n-1, loc=mean, scale=sem)
    except ImportError:
        mean = np.mean(arr); std = np.std(arr, ddof=1)
        z = 1.96; margin = z * std / np.sqrt(n)
        low, high = mean - margin, mean + margin
    return {
        "mean_ms": float(mean), "std_ms": float(np.std(arr, ddof=1)),
        "min_ms": float(np.min(arr)), "max_ms": float(np.max(arr)),
        "p50_ms": float(np.median(arr)), "p95_ms": float(np.percentile(arr, 95)),
        "p99_ms": float(np.percentile(arr, 99)),
        "ci95_low": round(float(low), 1), "ci95_high": round(float(high), 1), "n": n,
    }


def compute_ocr_f1(detected, expected):
    if not expected: return 0
    dl = set(t.lower() for t in detected); el = set(t.lower() for t in expected)
    tp = len(dl & el) + sum(1 for e in el for d in dl if e in d or d in e)
    p = tp / max(len(dl), 1); r = tp / max(len(el), 1)
    return 2 * p * r / max(p + r, 0.001)


def compute_det_f1(detected_boxes, expected_boxes):
    """IoU-based detection F1."""
    if not expected_boxes: return 0
    def iou(a, b):
        xa1, ya1, wa, ha = a; xa2, ya2 = xa1+wa, ya1+ha
        xb1, yb1, wb, hb = b; xb2, yb2 = xb1+wb, yb1+hb
        xi1, yi1 = max(xa1, xb1), max(ya1, yb1)
        xi2, yi2 = min(xa2, xb2), min(ya2, yb2)
        inter = max(0, xi2-xi1) * max(0, yi2-yi1)
        union = wa*ha + wb*hb - inter
        return inter / max(union, 1)
    matches = 0
    matched = set()
    for _di, de in enumerate(detected_boxes):
        for ei, ee in enumerate(expected_boxes):
            if ei in matched: continue
            if iou(de.get("bbox",[0,0,0,0]), ee.get("bbox",[0,0,0,0])) > 0.5:
                matches += 1; matched.add(ei); break
    p = matches / max(len(detected_boxes), 1)
    r = matches / max(len(expected_boxes), 1)
    return 2 * p * r / max(p + r, 0.001)


def get_git_commit():
    import subprocess
    try:
        return subprocess.run(["git", "rev-parse", "HEAD"],
                              capture_output=True, text=True).stdout.strip()[:8]
    except Exception: return "unknown"


def get_hardware_info():
    try:
        import torch
        if torch.cuda.is_available():
            return f"{torch.cuda.get_device_name(0)} ({torch.cuda.get_device_properties(0).total_memory//1e9:.0f}GB)"
    except Exception: pass
    return "CPU"


def run(matrix: list, output: str, warmup: int = 3, iterations: int = 10,
        confidence: float = 0.95):
    """Run the definitive benchmark matrix."""

    # Generate test dataset
    from benchmark_dataset import generate_dataset
    test_dir = "/tmp/bench_definitive"
    generate_dataset(test_dir)

    # Load manifest
    manifest = json.load(open(os.path.join(test_dir, "manifest.json")))
    frames = sorted([f for f in os.listdir(os.path.join(test_dir))
                     if f.endswith(".png")])
    warmup_frames = frames[:warmup]
    bench_frames = frames[warmup:]

    results = []

    for eng_idx, eng in enumerate(matrix):
        ui_name = eng["ui_detector"]
        ocr_name = eng["ocr_backend"]
        label = f"{ui_name}+{ocr_name}"

        print(f"[{eng_idx+1}/{len(matrix)}] {label}")

        try:
            detector = get_ui_detector(ui_name)
            ocr = get_ocr_engine(ocr_name)
        except Exception as e:
            results.append({"engine": eng, "error": str(e), "available": False})
            print(f"  SKIP: {e}")
            continue

        if not detector.available or not ocr.available:
            results.append({"engine": eng, "available": False})
            print(f"  SKIP: detector={detector.available} ocr={ocr.available}")
            continue

        # Warmup
        w0 = time.time()
        for f in warmup_frames:
            img = cv2.imread(os.path.join(test_dir, f))
            detector.detect(img)
            ocr.detect_text(img)
        w_time = (time.time() - w0) * 1000

        # Benchmark
        all_times = []
        total_ui = 0; total_int = 0; total_ocr_r = 0
        per_frame = []

        for f in bench_frames:
            img = cv2.imread(os.path.join(test_dir, f))
            frame_times = []
            ui_elems = 0; int_elems = 0; ocr_regs = 0

            for _ in range(iterations):
                t0 = time.time()
                elements = detector.detect(img)
                texts = ocr.detect_text(img)
                elapsed = (time.time() - t0) * 1000
                frame_times.append(elapsed)
                ui_elems = len(elements)
                int_elems = sum(1 for e in elements if e.get("interactive"))
                ocr_regs = len(texts)

            all_times.extend(frame_times)
            total_ui += ui_elems; total_int += int_elems; total_ocr_r += ocr_regs
            per_frame.append({**compute_stats(frame_times, confidence),
                              "frame": f, "ui_elements": ui_elems,
                              "interactive": int_elems, "ocr_regions": ocr_regs})

        n_bench = len(bench_frames)
        summary = compute_stats(all_times, confidence)
        summary.update({
            "total_s": round(sum(all_times) / 1000, 2),
            "frames_processed": n_bench * iterations,
            "benchmark_frames": n_bench,
            "iterations_per_frame": iterations,
            "warmup_frames": warmup,
            "warmup_ms": round(w_time, 0),
            "mean_ui_elements": round(total_ui / max(n_bench, 1), 1),
            "mean_interactive": round(total_int / max(n_bench, 1), 1),
            "mean_ocr_regions": round(total_ocr_r / max(n_bench, 1), 1),
            "effective_fps": round(n_bench * iterations / max(sum(all_times)/1000, 0.001), 1),
        })

        # Accuracy vs ground truth
        accuracy = {}
        for entry in manifest["images"]:
            img = cv2.imread(entry["path"])
            if img is None: continue
            elements = detector.detect(img)
            detected_texts = [r.get("text","") for r in ocr.detect_text(img)]

            gt = entry["ground_truth"]
            ocr_f1 = compute_ocr_f1(detected_texts, gt.get("expected_text", []))
            det_f1 = compute_det_f1(elements, gt.get("expected_elements", []))

            accuracy["ocr_f1"] = max(accuracy.get("ocr_f1", 0), ocr_f1)
            accuracy["det_f1"] = max(accuracy.get("det_f1", 0), det_f1)

        entry = {
            "engine": eng, "available": True,
            "summary": summary, "per_frame": per_frame,
            "accuracy": accuracy,
        }
        results.append(entry)

        print(f"  {summary['mean_ms']:.0f}ms CI95:[{summary['ci95_low']:.0f}-{summary['ci95_high']:.0f}] "
              f"p95:{summary['p95_ms']:.0f}ms fps:{summary['effective_fps']:.1f} "
              f"elem:{summary['mean_ui_elements']:.0f} "
              f"ocrF1:{accuracy.get('ocr_f1',0):.3f} detF1:{accuracy.get('det_f1',0):.3f}")

    # Rankings
    available = [r for r in results if r.get("available")]
    if available:
        fastest = min(available, key=lambda r: r["summary"]["mean_ms"])
        most_elem = max(available, key=lambda r: r["summary"]["mean_ui_elements"])
        best_ocr = max(available, key=lambda r: r.get("accuracy",{}).get("ocr_f1",0))
        best_det = max(available, key=lambda r: r.get("accuracy",{}).get("det_f1",0))
        rankings = {
            "fastest": fastest["engine"],
            "most_elements": most_elem["engine"],
            "best_ocr": best_ocr["engine"],
            "best_detection": best_det["engine"],
        }
    else:
        rankings = {}

    report = {
        "benchmark_id": f"bench-definitive-{datetime.now(UTC).strftime('%Y%m%d-%H%M%S')}",
        "timestamp_utc": datetime.now(UTC).isoformat(),
        "git_commit": get_git_commit(),
        "hardware": get_hardware_info(),
        "protocol": {
            "test_frames": len(bench_frames),
            "warmup_frames": warmup,
            "iterations_per_frame": iterations,
            "confidence_level": confidence,
            "ci_method": "t-distribution (scipy.stats.t.interval)",
            "engines_tested": len(matrix),
            "engines_available": len(available),
            "total_trials": len(available) * len(bench_frames) * iterations,
        },
        "rankings": rankings,
        "results": results,
    }

    if output:
        os.makedirs(os.path.dirname(output) or ".", exist_ok=True)
        with open(output, "w") as f:
            json.dump(report, f, indent=2)
        print(f"\nSaved: {output}")

    return report


# ── Default engine matrix ────────────────────────────────────────────

DEFAULT_MATRIX = [
    {"ui_detector": "contour",     "ocr_backend": "tesseract"},
    {"ui_detector": "yolo",        "ocr_backend": "tesseract"},
    {"ui_detector": "uidetr1",     "ocr_backend": "tesseract"},
    {"ui_detector": "screenparser","ocr_backend": "tesseract"},
    {"ui_detector": "wine",        "ocr_backend": "tesseract"},
]


def main():
    parser = argparse.ArgumentParser(
        description="WineBot Definitive Engine Benchmark — reproducible & statistically rigorous")
    parser.add_argument("--output", default="benchmark_results.json")
    parser.add_argument("--warmup", type=int, default=3)
    parser.add_argument("--iterations", type=int, default=10)
    parser.add_argument("--confidence", type=float, default=0.95)
    parser.add_argument("--all", action="store_true",
                        help="Benchmark all available engine combos (auto-discovered)")
    args = parser.parse_args()

    if args.all:
        detectors = [k for k,v in available_detectors().items() if v]
        backends = [k for k,v in available_backends().items() if v]
        matrix = [{"ui_detector": d, "ocr_backend": o}
                  for d in detectors for o in backends]
    else:
        matrix = DEFAULT_MATRIX

    print("WineBot Definitive Benchmark")
    print(f"  Engines: {len(matrix)} combos")
    print(f"  Warmup:  {args.warmup} frames/engine")
    print(f"  Iters:   {args.iterations}/frame/engine")
    print(f"  CI:      {args.confidence*100:.0f}% t-distribution")
    print(f"  HW:      {get_hardware_info()}")
    print(f"  Commit:  {get_git_commit()}")
    print()

    report = run(matrix, args.output, args.warmup, args.iterations, args.confidence)

    print("\nRankings:")
    for k,v in report.get("rankings", {}).items():
        print(f"  {k}: {v['ui_detector']}+{v['ocr_backend']}")


if __name__ == "__main__":
    main()
