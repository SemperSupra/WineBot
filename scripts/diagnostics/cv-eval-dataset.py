#!/usr/bin/env python3
# EXECUTION: HOST — extracts annotated frames from demo output for model evaluation
# STATUS: ACTIVE — evaluation dataset builder for Wine screenshot models
"""
Build a Wine screenshot evaluation dataset from existing demo recordings.

Extracts representative frames from each demo, asks the sidecar to analyze them,
and saves the results as ground-truth annotations. This enables scoring new
model versions against known-good results.

Usage:
  python3 scripts/diagnostics/cv-eval-dataset.py --build   # extract frames + annotate
  python3 scripts/diagnostics/cv-eval-dataset.py --score    # compare current model vs ground truth
  python3 scripts/diagnostics/cv-eval-dataset.py --report   # print evaluation report
"""

import argparse
import glob
import json
import os
import subprocess
from datetime import UTC, datetime
from pathlib import Path

SIDECAR_URL = os.environ.get("CV_SIDECAR_URL", "http://localhost:8001")
# Derive project root from this script's location
_PROJECT_ROOT = str(Path(__file__).resolve().parent.parent.parent)
DEMO_DIR = os.path.join(_PROJECT_ROOT, "demo", "output")
EVAL_DIR = os.path.join(DEMO_DIR, "analysis", "eval")

# ── Frame Extraction ─────────────────────────────────────────────────────────

def extract_eval_frames(video_path: str, out_dir: str, max_frames: int = 10) -> list:
    """Extract evenly-spaced frames from a video for evaluation."""
    os.makedirs(out_dir, exist_ok=True)

    # Get video duration
    result = subprocess.run(
        ["ffprobe", "-v", "quiet", "-show_entries", "format=duration",
         "-of", "csv=p=0", video_path],
        capture_output=True, text=True
    )
    duration = float(result.stdout.strip() or 30)

    # Extract max_frames evenly-spaced frames
    interval = max(1.0, duration / max_frames)
    cmd = ["ffmpeg", "-y", "-v", "quiet", "-i", video_path,
           "-vf", f"fps=1/{interval}", "-q:v", "2", f"{out_dir}/eval_%04d.png"]
    subprocess.run(cmd, capture_output=True)

    frames = sorted(glob.glob(f"{out_dir}/eval_*.png"))
    if len(frames) > max_frames:
        # Keep only evenly-spaced subset
        step = len(frames) // max_frames
        frames = frames[::step][:max_frames]

    return frames


# ── Annotation ───────────────────────────────────────────────────────────────

def annotate_frame(frame_path: str) -> dict:
    """Annotate a single frame using the sidecar with current engines."""
    # frame_path is a host path like C:/Users/.../demo/output/analysis/eval/...
    # The sidecar sees the same path via /demo-output/analysis/eval/...
    container_path = frame_path.replace("\\", "/")
    # Convert host path to sidecar mount path
    if "/demo/output/" in container_path:
        container_path = "/demo-output/" + container_path.split("/demo/output/", 1)[1]
    elif "/artifacts/" in container_path:
        container_path = "/artifacts/" + container_path.split("/artifacts/", 1)[1]
    try:
        result = subprocess.run([
            "curl", "-s", "-X", "POST", f"{SIDECAR_URL}/analyze",
            "-H", "Content-Type: application/json",
            "-d", json.dumps({"image_path": container_path}),
        ], capture_output=True, text=True, timeout=15)
        if result.returncode == 0 and result.stdout:
            data = json.loads(result.stdout)
            data["annotated_at"] = datetime.now(UTC).isoformat()
            data["engines"] = {
                "detector": data.get("detector", "unknown"),
                "ocr": data.get("ocr_engine", "unknown"),
            }
            return data
    except Exception:
        pass
    return {"error": "annotation_failed", "frame": frame_path}


# ── Build Dataset ────────────────────────────────────────────────────────────

def build_dataset() -> dict:
    """Build evaluation dataset from all demo videos."""
    os.makedirs(EVAL_DIR, exist_ok=True)

    videos = sorted(glob.glob(f"{DEMO_DIR}/*.mkv"))
    if not videos:
        print("ERROR: No MKV files found in demo/output/")
        return {"error": "no_videos"}

    dataset = {
        "created_at": datetime.now(UTC).isoformat(),
        "engines": {},
        "frames": [],
    }

    for video in videos:
        name = Path(video).stem
        print(f"  {name}...", end=" ", flush=True)

        frame_dir = os.path.join(EVAL_DIR, name)
        frames = extract_eval_frames(video, frame_dir)
        print(f"{len(frames)} frames ", end="", flush=True)

        for frame_path in frames:
            annotation = annotate_frame(frame_path)
            annotation["video"] = name
            annotation["frame_file"] = os.path.basename(frame_path)
            dataset["frames"].append(annotation)

        print("done")

    # Record which engines were used
    try:
        health = subprocess.check_output(["curl", "-s", f"{SIDECAR_URL}/health"])
        h = json.loads(health)
        dataset["engines"] = {
            "detector": h["active"]["ui_detector"],
            "ocr": h["active"]["ocr_engine"],
            "available": h.get("available_detectors", {}),
        }
    except Exception:
        pass

    # Save
    dataset_path = os.path.join(EVAL_DIR, "ground_truth.json")
    with open(dataset_path, "w", encoding="utf-8") as f:
        json.dump(dataset, f, indent=2)

    total_frames = len(dataset["frames"])
    total_ocr = sum(f.get("ocr_regions", 0) for f in dataset["frames"])
    total_elements = sum(f.get("ui_elements", 0) for f in dataset["frames"])

    print(f"\nEvaluation dataset: {total_frames} frames")
    print(f"  OCR regions: {total_ocr}")
    print(f"  UI elements: {total_elements}")
    print(f"  Engines: {dataset['engines']}")
    print(f"  Saved: {dataset_path}")

    return dataset


# ── Score Against Ground Truth ───────────────────────────────────────────────

def score_against_ground_truth(dataset_path: str | None = None) -> dict:
    """Re-analyze all frames with current engines and compare to ground truth."""
    if dataset_path is None:
        dataset_path = os.path.join(EVAL_DIR, "ground_truth.json")

    if not os.path.exists(dataset_path):
        print("ERROR: No ground truth dataset. Run --build first.")
        return {"error": "no_dataset"}

    with open(dataset_path, encoding="utf-8") as f:
        ground_truth = json.load(f)

    frames = ground_truth.get("frames", [])
    if not frames:
        return {"error": "empty_dataset"}

    # Get current engines
    try:
        health = subprocess.check_output(["curl", "-s", f"{SIDECAR_URL}/health"])
        h = json.loads(health)
        current_engines = {
            "detector": h["active"]["ui_detector"],
            "ocr": h["active"]["ocr_engine"],
        }
    except Exception:
        current_engines = {"detector": "unknown", "ocr": "unknown"}

    gt_engines = ground_truth.get("engines", {}).get("detector", "unknown")

    scores = []
    total_gt_elements = 0
    total_gt_ocr = 0

    for _i, gt_frame in enumerate(frames):
        frame_path = gt_frame.get("frame_file", "")
        video = gt_frame.get("video", "")
        if video and frame_path:
            full_path = os.path.join(EVAL_DIR, video, frame_path)
            full_path = full_path.replace("\\", "/")
        else:
            continue

        # Re-analyze
        current = annotate_frame(full_path)

        gt_elements = gt_frame.get("ui_elements", 0)
        gt_ocr = gt_frame.get("ocr_regions", 0)
        cur_elements = current.get("ui_elements", 0)
        cur_ocr = current.get("ocr_regions", 0)

        total_gt_elements += gt_elements
        total_gt_ocr += gt_ocr

        scores.append({
            "video": video,
            "frame": frame_path,
            "ground_truth": {"elements": gt_elements, "ocr": gt_ocr},
            "current": {"elements": cur_elements, "ocr": cur_ocr},
        })

    # Summary metrics
    total_cur_elements = sum(s["current"]["elements"] for s in scores)
    total_cur_ocr = sum(s["current"]["ocr"] for s in scores)

    report = {
        "evaluated_at": datetime.now(UTC).isoformat(),
        "ground_truth_engines": {"detector": gt_engines},
        "current_engines": current_engines,
        "frames_evaluated": len(scores),
        "ground_truth": {
            "total_elements": total_gt_elements,
            "total_ocr_regions": total_gt_ocr,
        },
        "current": {
            "total_elements": total_cur_elements,
            "total_ocr_regions": total_cur_ocr,
        },
        "element_recall": round(total_cur_elements / max(total_gt_elements, 1), 3),
        "ocr_recall": round(total_cur_ocr / max(total_gt_ocr, 1), 3),
        "per_frame": scores,
    }

    # Save report
    report_path = os.path.join(EVAL_DIR, "score_report.json")
    with open(report_path, "w", encoding="utf-8") as f:
        json.dump(report, f, indent=2)

    return report


# ── Print Report ─────────────────────────────────────────────────────────────

def print_report(report: dict):
    print("=" * 60)
    print("  WINE SCREENSHOT EVALUATION REPORT")
    print("=" * 60)
    print(f"  Ground truth engines: {report.get('ground_truth_engines', {})}")
    print(f"  Current engines:      {report.get('current_engines', {})}")
    print(f"  Frames evaluated:     {report.get('frames_evaluated', 0)}")
    print()
    print(f"  Element recall:       {report.get('element_recall', 0):.1%}")
    print(f"  OCR text recall:      {report.get('ocr_recall', 0):.1%}")
    print()
    print("=" * 60)


# ── Main ─────────────────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(description="Wine screenshot evaluation dataset")
    parser.add_argument("--build", action="store_true", help="Build evaluation dataset")
    parser.add_argument("--score", action="store_true", help="Score current models vs ground truth")
    parser.add_argument("--report", action="store_true", help="Print last evaluation report")
    args = parser.parse_args()

    if args.build:
        dataset = build_dataset()
        report = score_against_ground_truth()
        print_report(report)
    elif args.score:
        report = score_against_ground_truth()
        print_report(report)
    elif args.report:
        report_path = os.path.join(EVAL_DIR, "score_report.json")
        if os.path.exists(report_path):
            with open(report_path) as f:
                print_report(json.load(f))
        else:
            print("No report found. Run --build first.")
    else:
        parser.print_help()


if __name__ == "__main__":
    main()
