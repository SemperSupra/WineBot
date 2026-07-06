#!/usr/bin/env python3
# EXECUTION: HOST — runs full best-quality CV analysis on all demo videos
# STATUS: ACTIVE — unified analysis: sidecar OCR + host YOLO/OmniParser
"""
Run full-quality analysis on all demo videos using:
  - Sidecar (Docker): Tesseract OCR with CLAHE preprocessing + multi-PSM
  - Host (Python):    OmniParser YOLOv8 icon_detect for UI elements
  - Merged:           Combined per-frame JSONL with both sources

Usage:
  python3 scripts/diagnostics/cv-analyze-demos.py
"""

import glob
import json
import os
import subprocess
import sys
from pathlib import Path

# Add scripts to path so we can import engines
sys.path.insert(0, str(Path(__file__).resolve().parent))
import cv2
from winebot_cv.detectors.engines import YOLOUIDetector

SIDECAR_URL = os.environ.get("CV_SIDECAR_URL", "http://localhost:8001")
# Derive project root from this script's location: scripts/diagnostics/ → ../../ → project root
_PROJECT_ROOT = str(Path(__file__).resolve().parent.parent.parent)
DEMO_DIR = os.path.join(_PROJECT_ROOT, "demo", "output")
OUTPUT_DIR = os.path.join(DEMO_DIR, "analysis")

VIDEOS = ["7zip", "ci-pipeline", "core-pipeline", "installer-qa",
          "notepadpp", "re-sandbox", "supertux", "vlc"]


def extract_frames(video_path: str, out_dir: str, fps: float = 1.0) -> list:
    """Extract frames from video using ffmpeg."""
    os.makedirs(out_dir, exist_ok=True)
    cmd = ["ffmpeg", "-y", "-v", "quiet", "-i", video_path,
           "-vf", f"fps={fps}", "-q:v", "2", f"{out_dir}/frame_%04d.png"]
    subprocess.run(cmd, capture_output=True)
    return sorted(glob.glob(f"{out_dir}/frame_*.png"))


def analyze_ocr_sidecar(frame_path: str) -> dict:
    """Call sidecar /analyze for OCR text. Translates host paths to container paths."""
    # Container mount: ../demo/output:/demo-output:ro
    # Path: <project>/demo/output/analysis/... → /demo-output/analysis/...
    norm = frame_path.replace("\\", "/")
    if "demo/output/" in norm:
        container_path = "/demo-output/" + norm.split("demo/output/", 1)[1]
    elif "/artifacts/" in norm:
        container_path = "/artifacts/" + norm.split("/artifacts/", 1)[1]
    else:
        container_path = norm

    try:
        result = subprocess.run([
            "curl", "-s", "-X", "POST", f"{SIDECAR_URL}/analyze",
            "-H", "Content-Type: application/json",
            "-d", json.dumps({"image_path": container_path}),
        ], capture_output=True, text=True, timeout=10)
        if result.returncode == 0 and result.stdout:
            data = json.loads(result.stdout)
            return data
    except Exception:
        pass
    return {"ocr_regions": 0, "key_text": [], "error": "sidecar_unavailable"}


def analyze_yolo_host(img_path: str, detector: YOLOUIDetector) -> list:
    """Run YOLO/OmniParser detection on a frame from the host."""
    img = cv2.imread(img_path)
    if img is None:
        return []
    return detector.detect(img)


def run():
    print("=" * 70)
    print("  WINEBOT BEST-QUALITY CV ANALYSIS")
    print("  OCR:   Tesseract + CLAHE + multi-PSM (sidecar)")
    print("  YOLO:  OmniParser v2 icon_detect (host)")
    print("=" * 70)
    print()

    # Check sidecar
    try:
        health = subprocess.check_output(["curl", "-s", f"{SIDECAR_URL}/health"])
        h = json.loads(health)
        print(f"Sidecar: {h['status']} | OCR: {h['active']['ocr_engine']} | "
              f"tesseract={h['available_ocr_backends'].get('tesseract')}")
    except Exception:
        print("Sidecar: NOT REACHABLE — OCR will be unavailable")
    print()

    # Load YOLO detector
    print("Loading OmniParser YOLO...")
    yolo = YOLOUIDetector()
    print(f"YOLO:  available={yolo.available} | GPU={yolo.uses_gpu}")
    print()

    all_results = {}
    total_frames = 0
    total_ocr = 0
    total_yolo = 0

    for video_name in VIDEOS:
        video_path = os.path.join(DEMO_DIR, f"{video_name}.mkv")
        if not os.path.exists(video_path):
            print(f"  {video_name}: SKIP (no video)")
            continue

        frames_dir = os.path.join(OUTPUT_DIR, video_name, "frames")
        frames = extract_frames(video_path, frames_dir)
        if not frames:
            print(f"  {video_name}: NO FRAMES")
            continue

        print(f"  {video_name}: {len(frames)} frames ", end="", flush=True)

        per_video = []
        vid_ocr = 0
        vid_yolo = 0

        for frame_path in frames:
            t_s = float(Path(frame_path).stem.split("_")[1]) - 1  # frame_0001 = 0s

            # OCR via sidecar
            ocr = analyze_ocr_sidecar(frame_path)
            ocr_count = ocr.get("ocr_regions", 0)

            # YOLO via host
            yolo_elements = analyze_yolo_host(frame_path, yolo)
            yolo_count = len(yolo_elements)

            entry = {
                "t_s": t_s,
                "ocr_regions": ocr_count,
                "key_text": ocr.get("key_text", [])[:15],
                "yolo_elements": yolo_count,
                "yolo_detail": yolo_elements[:15],
            }
            per_video.append(entry)
            vid_ocr += ocr_count
            vid_yolo += yolo_count

        all_results[video_name] = per_video
        total_frames += len(frames)
        total_ocr += vid_ocr
        total_yolo += vid_yolo

        print(f"→ {vid_ocr} OCR regions, {vid_yolo} YOLO elements")

    # Save unified results
    unified_path = os.path.join(OUTPUT_DIR, "best_quality_analysis.jsonl")
    with open(unified_path, "w", encoding="utf-8") as f:
        for video_name, frames in all_results.items():
            for frame in frames:
                frame["video"] = video_name
                f.write(json.dumps(frame) + "\n")

    # Summary report
    print()
    print("=" * 70)
    print("  ANALYSIS COMPLETE")
    print(f"  Videos: {len(all_results)}/{len(VIDEOS)}")
    print(f"  Total frames: {total_frames}")
    print(f"  Total OCR regions: {total_ocr}")
    print(f"  Total YOLO UI elements: {total_yolo}")
    print(f"  Avg OCR/frame: {total_ocr / max(total_frames, 1):.1f}")
    print(f"  Avg YOLO/frame: {total_yolo / max(total_frames, 1):.1f}")
    print(f"  Output: {unified_path}")
    print("=" * 70)


if __name__ == "__main__":
    run()
