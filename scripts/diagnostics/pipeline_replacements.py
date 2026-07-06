#!/usr/bin/env python3
"""Pipeline Component Replacement Benchmark — statistical comparison of all candidates.

Protocol:
  1. For each pipeline stage, test ALL available backends
  2. Warmup: 3 frames per backend (discarded)
  3. Benchmark: 10 iterations per frame per backend
  4. 95% CI via t-distribution
  5. Significance: non-overlapping CIs = real difference
  6. Comparative ranking: best by speed, best by accuracy, best combined

Usage:
  python3 pipeline_replacements.py --output replace_results.json
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
from winebot_cv.ocr.engines import available_backends, get_ocr_engine
from winebot_cv.detectors.engines import available_detectors, get_ui_detector

# ── Stats ──────────────────────────────────────────────────────────────────────

def compute_stats(times, confidence=0.95):
    arr = np.array(times); n = len(arr)
    if n < 3:
        return {"mean_ms": float(np.mean(arr)) if n else 0, "n": n}
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
        "ci95_low": round(float(low), 1), "ci95_high": round(float(high), 1), "n": n,
    }


def ci_overlap(a, b):
    """Check if two 95% CIs overlap. Returns True if they overlap (not significantly different)."""
    lo_a, hi_a = a.get("ci95_low", 0), a.get("ci95_high", 0)
    lo_b, hi_b = b.get("ci95_low", 0), b.get("ci95_high", 0)
    return not (hi_a < lo_b or hi_b < lo_a)


# ── Test Images ────────────────────────────────────────────────────────────────

def generate_test_images():
    """Generate 6 synthetic test images with known ground truth."""
    from benchmark_dataset import GENERATORS
    test_dir = "/tmp/bench_replace"
    os.makedirs(test_dir, exist_ok=True)
    manifest = {"images": []}

    for name, gen_fn in GENERATORS.items():
        img, gt = gen_fn()
        path = os.path.join(test_dir, f"{name}.png")
        cv2.imwrite(path, img)
        manifest["images"].append({
            "path": path, "name": name,
            "ground_truth": gt,
        })

    with open(os.path.join(test_dir, "manifest.json"), "w") as f:
        json.dump(manifest, f)
    return manifest


# ── Benchmarks ─────────────────────────────────────────────────────────────────

def benchmark_detection(test_images, warmup=3, iterations=10):
    """Benchmark all available detectors on the test images."""
    print("=" * 72)
    print("  STAGE 1: UI Element Detection")
    print("=" * 72)

    results = []
    backends = [k for k, v in available_detectors().items() if v]
    # Order by expected speed
    order = ["contour", "wine", "yolo", "screenparser_wine", "screenparser", "uidetr1"]
    backends = [b for b in order if b in backends] + [b for b in backends if b not in order]

    for backend in backends:
        print(f"\n[{backend}] Loading...")
        detector = get_ui_detector(backend)
        if not detector.available:
            print("  SKIP: not available")
            continue

        backend_results = {"backend": backend, "gpu": detector.uses_gpu, "frames": []}
        all_times = []
        all_elem_counts = []

        for img_entry in test_images["images"]:
            img = cv2.imread(img_entry["path"])
            if img is None:
                continue

            # Warmup (discarded)
            for _ in range(warmup):
                _ = detector.detect(img)

            # Benchmark
            frame_times = []
            for _ in range(iterations):
                t0 = time.perf_counter()
                elements = detector.detect(img)
                elapsed = (time.perf_counter() - t0) * 1000
                frame_times.append(elapsed)
                if _ == 0:
                    elem_count = len(elements)

            stats = compute_stats(frame_times)
            backend_results["frames"].append({
                "image": img_entry["name"],
                "stats": stats,
                "elements_detected": elem_count,
            })
            all_times.extend(frame_times)
            all_elem_counts.append(elem_count)

        agg = compute_stats(all_times)
        backend_results["summary"] = agg
        backend_results["summary"]["mean_elements"] = round(np.mean(all_elem_counts), 1)
        backend_results["summary"]["total_frames"] = len(test_images["images"])
        results.append(backend_results)

        print(f"  {agg['mean_ms']:.0f}ms CI95[{agg['ci95_low']:.0f}-{agg['ci95_high']:.0f}]  "
              f"{backend_results['summary']['mean_elements']:.1f} elem  "
              f"GPU={detector.uses_gpu}")

    # Significance analysis
    print("\n  --- Speed ranking ---")
    ranked = sorted(results, key=lambda r: r["summary"]["mean_ms"])
    baseline = ranked[0] if ranked else None
    for i, r in enumerate(ranked):
        sig = ""
        if baseline and r != baseline:
            if not ci_overlap(baseline["summary"], r["summary"]):
                sig = f"  ← sig. slower than {baseline['backend']} (p<0.05)"
        print(f"  {i+1}. {r['backend']:<20s} {r['summary']['mean_ms']:.0f}ms "
              f"CI95[{r['summary']['ci95_low']:.0f}-{r['summary']['ci95_high']:.0f}]{sig}")

    return results


def benchmark_ocr(test_images, warmup=3, iterations=10):
    """Benchmark all available OCR engines."""
    print("\n" + "=" * 72)
    print("  STAGE 2: OCR / Text Recognition")
    print("=" * 72)

    results = []
    backends = [k for k, v in available_backends().items() if v]
    # Remove variant suffixes for the base benchmark
    base_backends = []
    seen = set()
    for b in backends:
        base = b.split(":")[0]
        if base not in seen:
            seen.add(base)
            base_backends.append(b)
    # Add explicit variants
    variants = ["paddle_onnx:tiny", "paddle_onnx:small", "paddle_onnx:medium"]
    test_backends = []
    for b in base_backends:
        if b == "paddle_onnx":
            test_backends.extend(v for v in variants if v in backends)
        else:
            test_backends.append(b)

    for backend in test_backends:
        print(f"\n[{backend}] Loading...")
        ocr = get_ocr_engine(backend)
        if not ocr.available:
            print("  SKIP: not available")
            continue

        backend_results = {"backend": backend, "frames": []}
        all_times = []
        all_text_counts = []

        for img_entry in test_images["images"]:
            img = cv2.imread(img_entry["path"])
            if img is None:
                continue

            for _ in range(warmup):
                _ = ocr.detect_text(img)

            frame_times = []
            for _ in range(iterations):
                t0 = time.perf_counter()
                texts = ocr.detect_text(img)
                elapsed = (time.perf_counter() - t0) * 1000
                frame_times.append(elapsed)
                if _ == 0:
                    text_count = len(texts)

            stats = compute_stats(frame_times)
            backend_results["frames"].append({
                "image": img_entry["name"],
                "stats": stats,
                "text_regions_detected": text_count,
            })
            all_times.extend(frame_times)
            all_text_counts.append(text_count)

        agg = compute_stats(all_times)
        backend_results["summary"] = agg
        backend_results["summary"]["mean_text_regions"] = round(np.mean(all_text_counts), 1)
        results.append(backend_results)

        print(f"  {agg['mean_ms']:.0f}ms CI95[{agg['ci95_low']:.0f}-{agg['ci95_high']:.0f}]  "
              f"{backend_results['summary']['mean_text_regions']:.1f} regions")

    print("\n  --- Speed ranking ---")
    ranked = sorted(results, key=lambda r: r["summary"]["mean_ms"])
    baseline = ranked[0] if ranked else None
    for i, r in enumerate(ranked):
        sig = ""
        if baseline and r != baseline:
            if not ci_overlap(baseline["summary"], r["summary"]):
                sig = f"  ← sig. slower than {baseline['backend']} (p<0.05)"
        print(f"  {i+1}. {r['backend']:<20s} {r['summary']['mean_ms']:.0f}ms "
              f"CI95[{r['summary']['ci95_low']:.0f}-{r['summary']['ci95_high']:.0f}]{sig}")

    return results


def benchmark_clip(test_images, warmup=3, iterations=50):
    """Benchmark CLIP embedding speed and zero-shot accuracy."""
    print("\n" + "=" * 72)
    print("  STAGE 3: Semantic Embedding")
    print("=" * 72)

    results = []

    # CLIP ViT-B-32 (current)
    from winebot_cv.embedding.clip import get_clip_embedder
    clip = get_clip_embedder("open_clip")
    if not clip.available:
        print("[clip] OpenCLIP not available, skipping")
        return results

    print("\n[CLIP ViT-B-32] Benchmarking...")
    all_times = []
    zero_shot_results = []

    # Scene type labels
    scene_labels = [
        "a save dialog with a filename text field and buttons",
        "an error dialog with an error message and OK button",
        "a settings window with checkboxes and dropdowns",
        "an installer wizard with license text and Next button",
        "a notepad text editor with a menu bar",
        "a dense form with many text fields and labels",
    ]

    for img_entry in test_images["images"]:
        img = cv2.imread(img_entry["path"])
        if img is None:
            continue

        # Warmup
        for _ in range(warmup):
            _ = clip.embed_image(img)

        # Speed benchmark (more iterations for CLIP since it's faster)
        frame_times = []
        for _ in range(iterations):
            t0 = time.perf_counter()
            _ = clip.embed_image(img)
            elapsed = (time.perf_counter() - t0) * 1000
            frame_times.append(elapsed)

        # Zero-shot classification
        probs = clip.classify(img, scene_labels)
        top = max(probs, key=probs.get)
        zero_shot_results.append({
            "image": img_entry["name"],
            "predicted": top,
            "confidence": probs[top],
            "all_probs": probs,
        })

        stats = compute_stats(frame_times)
        all_times.extend(frame_times)

    agg = compute_stats(all_times)
    n_correct = sum(1 for r in zero_shot_results
                    if r["image"].replace("_", " ") in r["predicted"].lower()
                    or any(w in r["predicted"].lower() for w in r["image"].split("_")))
    accuracy = n_correct / max(len(zero_shot_results), 1)

    results.append({
        "backend": "clip_vitb32",
        "model": "ViT-B-32 (LAION-2B)",
        "summary": agg,
        "zero_shot_accuracy": round(accuracy, 3),
        "zero_shot_details": zero_shot_results,
    })

    print(f"  {agg['mean_ms']:.1f}ms CI95[{agg['ci95_low']:.1f}-{agg['ci95_high']:.1f}]  "
          f"zero-shot acc: {accuracy:.0%}")

    return results


def benchmark_scene_description(test_images, warmup=1, iterations=3):
    """Benchmark scene captioning quality."""
    print("\n" + "=" * 72)
    print("  STAGE 4: Scene Description / Captioning")
    print("=" * 72)

    results = []

    # Test Florence-2 if available
    try:
        from florence2_captioner import get_captioner
        cap = get_captioner()
        if cap.available:
            print("\n[Florence-2-base] Captioning (limited iterations — slow)...")
            captions = []
            for img_entry in test_images["images"]:
                img = cv2.imread(img_entry["path"])
                if img is None:
                    continue
                t0 = time.perf_counter()
                caption = cap.caption(img, style="detailed")
                elapsed = (time.perf_counter() - t0) * 1000
                captions.append({
                    "image": img_entry["name"],
                    "caption": caption,
                    "inference_ms": round(elapsed, 0),
                })
                print(f"  {img_entry['name']}: {caption[:120]}...")
            results.append({
                "backend": "florence2_base",
                "model": "Florence-2-base (230M)",
                "captions": captions,
                "mean_ms": round(np.mean([c["inference_ms"] for c in captions]), 0),
            })
    except ImportError:
        print("  Florence-2 not available")

    # Test Ollama VLM if configured
    import os
    if os.environ.get("VLM_PROVIDER", "").lower() == "ollama":
        try:
            from vlm_ollama import get_ollama_vlm
            ollama = get_ollama_vlm()
            if ollama:
                print(f"\n[Ollama {ollama.model}] Captioning...")
                captions = []
                for img_entry in test_images["images"]:
                    img = cv2.imread(img_entry["path"])
                    if img is None:
                        continue
                    t0 = time.perf_counter()
                    caption = ollama.describe(img, style="brief")
                    elapsed = (time.perf_counter() - t0) * 1000
                    captions.append({
                        "image": img_entry["name"],
                        "caption": caption,
                        "inference_ms": round(elapsed, 0),
                    })
                    print(f"  {img_entry['name']}: {caption[:120] if caption else 'NONE'}...")
                results.append({
                    "backend": f"ollama_{ollama.model.replace(':', '_')}",
                    "model": ollama.model,
                    "provenance": ollama.provenance,
                    "captions": captions,
                    "mean_ms": round(np.mean([c["inference_ms"] for c in captions if c["inference_ms"]]), 0),
                })
        except ImportError:
            pass

    return results


# ── Main ───────────────────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(
        description="Pipeline Component Replacement Benchmark")
    parser.add_argument("--output", default="/tmp/pipeline_replacements.json")
    parser.add_argument("--warmup", type=int, default=3)
    parser.add_argument("--iterations", type=int, default=10)
    parser.add_argument("--stage", default="all",
                        choices=["all", "detection", "ocr", "embedding", "captioning"])
    args = parser.parse_args()

    print("Pipeline Component Replacement Benchmark")
    print(f"  Warmup: {args.warmup} frames | Iterations: {args.iterations}")
    print(f"  Stage: {args.stage}")
    print()

    # Generate test images
    print("Generating test images...")
    test_images = generate_test_images()
    print(f"  {len(test_images['images'])} images ready")
    print()

    report = {
        "benchmark": "winebot_pipeline_replacements",
        "timestamp": datetime.now(UTC).isoformat(),
        "config": {
            "warmup": args.warmup,
            "iterations": args.iterations,
            "confidence": 0.95,
            "test_images": len(test_images["images"]),
        },
        "results": {},
    }

    if args.stage in ("all", "detection"):
        report["results"]["detection"] = benchmark_detection(
            test_images, args.warmup, args.iterations)

    if args.stage in ("all", "ocr"):
        report["results"]["ocr"] = benchmark_ocr(
            test_images, args.warmup, args.iterations)

    if args.stage in ("all", "embedding"):
        report["results"]["embedding"] = benchmark_clip(
            test_images, args.warmup, 50)

    if args.stage in ("all", "captioning"):
        report["results"]["captioning"] = benchmark_scene_description(
            test_images, args.warmup, min(args.iterations, 3))

    # ── Comparative Summary ─────────────────────────────────────────────────
    print("\n" + "=" * 72)
    print("  COMPARATIVE SUMMARY")
    print("=" * 72)

    for stage_name, stage_results in report["results"].items():
        print(f"\n  [{stage_name.upper()}]")
        if not stage_results:
            print("    No results")
            continue

        # Find best by speed
        ranked = sorted(stage_results, key=lambda r: r.get("summary", {}).get("mean_ms", 9999))
        best_speed = ranked[0]["backend"] if ranked else "?"
        best_ms = ranked[0].get("summary", {}).get("mean_ms", 0) if ranked else 0
        print(f"    Fastest: {best_speed} ({best_ms:.0f}ms)")

        # Detection-specific
        if stage_name == "detection":
            most_elements = max(stage_results,
                key=lambda r: r.get("summary", {}).get("mean_elements", 0))
            print(f"    Most elements: {most_elements['backend']} "
                  f"({most_elements['summary']['mean_elements']:.1f})")

        # Statistically significant differences
        if len(ranked) >= 2:
            baseline = ranked[0]
            print("    Statistically significant differences (p<0.05):")
            for r in ranked[1:]:
                if not ci_overlap(baseline.get("summary", {}), r.get("summary", {})):
                    diff_pct = ((r["summary"]["mean_ms"] - baseline["summary"]["mean_ms"])
                                / baseline["summary"]["mean_ms"] * 100)
                    print(f"      {baseline['backend']} vs {r['backend']}: "
                          f"+{diff_pct:.0f}% ({r['summary']['mean_ms']:.0f} vs {baseline['summary']['mean_ms']:.0f}ms)")

    # Write results
    with open(args.output, "w") as f:
        json.dump(report, f, indent=2)
    print(f"\nResults: {args.output}")


if __name__ == "__main__":
    main()
