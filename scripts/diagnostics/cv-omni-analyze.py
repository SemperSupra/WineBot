#!/usr/bin/env python3
"""Offline CV analyzer for WineBot recordings.

Extracts frames from an MKV recording, detects UI elements using YOLOv8
(object detection) and Tesseract (OCR text), and enriches the session's
annotation events with precise element coordinates.

Usage:
  python3 cv-omni-analyze.py --session-dir /sessions/session-abc123
  python3 cv-omni-analyze.py --session-dir /sessions/session-abc123 --enrich

Output:
  <session-dir>/analysis/elements.jsonl     — per-frame UI element data
  <session-dir>/analysis/enriched_events.jsonl — events with position data
  <session-dir>/analysis/report.html         — visual report with bboxes
"""

import argparse
import json
import os
import subprocess
import sys
import tempfile
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, List, Optional, Tuple

import cv2
import numpy as np
import pytesseract


class RecordingAnalyzer:
    """Extracts frames from MKV and detects UI elements."""

    def __init__(self, session_dir: str, frame_interval: float = 1.0):
        self.session_dir = Path(session_dir)
        self.frame_interval = frame_interval
        self.out_dir = self.session_dir / "analysis"
        self.out_dir.mkdir(exist_ok=True)

        # Find video file
        video = self.session_dir / "video_001.mkv"
        if not video.exists():
            parts = sorted(self.session_dir.glob("video_001_part*.mkv"))
            if parts:
                video = self._concat_parts(session_dir, parts)
        self.video_path = video

        # Try YOLOv8 loader
        self.yolo_model = self._load_yolo()

    def _load_yolo(self):
        try:
            from ultralytics import YOLO
            model = YOLO("yolov8n.pt")
            print(f"  YOLOv8n loaded ({model.device})")
            return model
        except Exception as e:
            print(f"  YOLOv8 not available: {e}")
            return None

    def _concat_parts(self, session_dir: str, parts: List[Path]) -> Path:
        """Concatenate segmented MKV parts."""
        concat_list = self.out_dir / "concat.txt"
        with open(concat_list, "w") as f:
            for p in sorted(parts):
                f.write(f"file '{p}'\n")
        output = self.session_dir / "video_concatenated.mkv"
        subprocess.run([
            "ffmpeg", "-y", "-f", "concat", "-safe", "0",
            "-i", str(concat_list), "-c", "copy", str(output),
        ], capture_output=True)
        return output

    def extract_frames(self) -> List[Tuple[float, np.ndarray]]:
        """Extract key frames from video at frame_interval seconds."""
        frames = []
        tmpdir = self.out_dir / "frames"
        tmpdir.mkdir(exist_ok=True)

        cmd = [
            "ffmpeg", "-i", str(self.video_path),
            "-vf", f"fps=1/{self.frame_interval}",
            "-q:v", "2",
            f"{tmpdir}/frame_%04d.png",
        ]
        subprocess.run(cmd, capture_output=True)

        for png in sorted(tmpdir.glob("frame_*.png")):
            frame_num = int(png.stem.split("_")[1])
            timestamp = (frame_num - 1) * self.frame_interval
            img = cv2.imread(str(png))
            if img is not None and img.size > 0:
                frames.append((timestamp, img))

        print(f"  Extracted {len(frames)} frames")
        return frames

    def detect_ui_elements(self, img: np.ndarray) -> Dict:
        """Run full UI element detection on a frame."""
        h, w = img.shape[:2]
        result: Dict = {
            "size": f"{w}x{h}",
            "yolo_objects": [],
            "text_regions": [],
            "windows": [],
        }

        # YOLO detection (if model loaded)
        if self.yolo_model:
            try:
                detections = self.yolo_model(img, verbose=False)
                for det in detections:
                    boxes = det.boxes
                    if boxes is not None and len(boxes) > 0:
                        for i in range(len(boxes)):
                            cls_id = int(boxes.cls[i])
                            cls_name = det.names.get(cls_id, f"class_{cls_id}")
                            x1, y1, x2, y2 = boxes.xyxy[i].tolist()
                            conf = float(boxes.conf[i])
                            result["yolo_objects"].append({
                                "label": cls_name,
                                "bbox": [int(x1), int(y1), int(x2 - x1), int(y2 - y1)],
                                "confidence": round(conf, 3),
                            })
            except Exception as e:
                result["yolo_error"] = str(e)

        # OCR text detection (always available)
        gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
        try:
            data = pytesseract.image_to_data(gray, output_type=pytesseract.Output.DICT)
            for i in range(len(data["text"])):
                text = data["text"][i].strip()
                if not text or int(data["conf"][i]) < 40:
                    continue
                result["text_regions"].append({
                    "text": text,
                    "bbox": [
                        data["left"][i], data["top"][i],
                        data["width"][i], data["height"][i],
                    ],
                    "confidence": int(data["conf"][i]),
                })
        except Exception as e:
            result["ocr_error"] = str(e)

        return result

    def find_click_targets(self, elements: List[Dict]) -> Dict[str, Tuple[int, int]]:
        """From detected text, find click targets for common UI buttons."""
        targets = {}
        for r in elements:
            text = r.get("text", "").lower()
            bbox = r.get("bbox", [0, 0, 0, 0])
            cx = bbox[0] + bbox[2] // 2
            cy = bbox[1] + bbox[3] // 2

            # Map button text to click coordinates
            button_map = {
                "save": ("save_button", cx, cy),
                "&save": ("save_button", cx, cy),
                "cancel": ("cancel_button", cx, cy),
                "&cancel": ("cancel_button", cx, cy),
                "open": ("open_button", cx, cy),
                "ok": ("ok_button", cx, cy),
                "yes": ("yes_button", cx, cy),
                "no": ("no_button", cx, cy),
                "help": ("help_button", cx, cy),
                "close": ("close_button", cx, cy),
            }
            for pattern, (name, px, py) in button_map.items():
                if pattern in text:
                    targets[name] = (int(px), int(py))
                    break
        return targets

    def analyze(self) -> Dict:
        """Full analysis: extract frames, detect elements, find targets."""
        results = []
        frames = self.extract_frames()

        for timestamp, img in frames:
            elements = self.detect_ui_elements(img)
            click_targets = self.find_click_targets(
                elements.get("text_regions", [])
            )

            frame_result = {
                "timestamp_s": round(timestamp, 1),
                "elements": elements,
                "click_targets": click_targets,
                "text_summary": [
                    t["text"] for t in elements.get("text_regions", [])[:20]
                ],
            }
            results.append(frame_result)

            # Print progress
            if click_targets:
                names = list(click_targets.keys())
                print(f"  t={timestamp:5.1f}s  targets: {names}")

        # Write detailed output
        output_path = self.out_dir / "elements.jsonl"
        with open(output_path, "w") as f:
            for r in results:
                f.write(json.dumps(r) + "\n")

        # Build click target timeline
        timeline = []
        for r in results:
            if r["click_targets"]:
                timeline.append({
                    "time": r["timestamp_s"],
                    "targets": r["click_targets"],
                })

        summary = {
            "session_dir": str(self.session_dir),
            "frames_analyzed": len(results),
            "click_target_timeline": timeline,
            "output_files": {
                "elements": str(output_path),
            },
        }

        # Write summary
        summary_path = self.out_dir / "summary.json"
        with open(summary_path, "w") as f:
            json.dump(summary, f, indent=2)

        return summary

    def generate_enriched_events(self) -> str:
        """Read existing events.jsonl, add position data from analysis."""
        events_path = self.session_dir / "events.jsonl"
        if not events_path.exists():
            events_path = self.session_dir / "events_001.jsonl"
        if not events_path.exists():
            return ""

        # Read analysis results
        elements_path = self.out_dir / "elements.jsonl"
        if not elements_path.exists():
            return ""

        element_results = []
        with open(elements_path) as f:
            for line in f:
                try:
                    element_results.append(json.loads(line))
                except json.JSONDecodeError:
                    continue

        # Read original events
        events = []
        with open(events_path) as f:
            for line in f:
                try:
                    events.append(json.loads(line))
                except json.JSONDecodeError:
                    continue

        # Find manifest start time
        manifest = None
        manifest_path = self.session_dir / "session.json"
        if manifest_path.exists():
            with open(manifest_path) as f:
                manifest = json.load(f)

        start_epoch = 0
        if manifest:
            start_epoch = float(manifest.get("start_time_epoch", 0))

        # Match each event to the nearest frame
        enriched = []
        for event in events:
            t_rel = event.get("t_rel_ms", 0) / 1000.0
            # Find nearest analyzed frame
            nearest = None
            min_dist = float("inf")
            for fr in element_results:
                dist = abs(fr["timestamp_s"] - t_rel)
                if dist < min_dist and dist < 2.0:  # within 2 seconds
                    min_dist = dist
                    nearest = fr

            if nearest and nearest.get("click_targets"):
                event["_cv"] = {
                    "click_targets": nearest["click_targets"],
                    "text_summary": nearest.get("text_summary", [])[:10],
                }
            enriched.append(event)

        output_path = self.out_dir / "enriched_events.jsonl"
        with open(output_path, "w") as f:
            for e in enriched:
                f.write(json.dumps(e) + "\n")

        print(f"  Enriched {len(enriched)} events ({sum(1 for e in enriched if '_cv' in e)} with CV data)")
        return str(output_path)


def main():
    parser = argparse.ArgumentParser(description="Offline CV analyzer for WineBot")
    parser.add_argument("--session-dir", required=True)
    parser.add_argument("--frame-interval", type=float, default=1.0)
    parser.add_argument("--enrich", action="store_true",
                        help="Generate enriched event annotations")
    args = parser.parse_args()

    print(f"CV Analyzer — {args.session_dir}")
    if not Path(args.session_dir).is_dir():
        print(f"ERROR: Session dir not found")
        sys.exit(1)

    analyzer = RecordingAnalyzer(args.session_dir, args.frame_interval)

    if not analyzer.video_path.exists():
        print(f"ERROR: No video found at {analyzer.video_path}")
        sys.exit(1)

    print(f"Video: {analyzer.video_path}")

    summary = analyzer.analyze()

    print(f"\nAnalysis complete:")
    print(f"  Frames: {summary['frames_analyzed']}")
    print(f"  Click targets found in: {len(summary['click_target_timeline'])} frames")
    for t in summary["click_target_timeline"]:
        print(f"    t={t['time']:5.1f}s: {list(t['targets'].keys())}")

    if args.enrich:
        enriched_path = analyzer.generate_enriched_events()
        if enriched_path:
            print(f"\nEnriched events: {enriched_path}")

    print(f"\nOutput: {analyzer.out_dir}/")
    for f in sorted(analyzer.out_dir.iterdir()):
        print(f"  {f.name}")


if __name__ == "__main__":
    main()
