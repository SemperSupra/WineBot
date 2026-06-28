#!/usr/bin/env python3
# EXECUTION: HOST — processes MKV files on dev machine or CI; needs ffmpeg+OpenCV+Tesseract
# STATUS: ACTIVE — primary CV analysis harness for all demo videos and session recordings
"""CV/OCR Test Runner — analyzes WineBot demo videos with built-in tools.

Extracts frames from MKV recordings, runs UI element detection (OpenCV contours)
and OCR text reading (Tesseract), generates annotated frames with bounding boxes,
and produces a structured analysis report.

Two modes:
  Mode A: "built-in" — OpenCV + Tesseract only (no GPU/container needed)
  Mode B: "full"    — also runs YOLOv8 object detection (requires cv-analyzer container)

Usage:
  python3 scripts/diagnostics/cv-test-runner.py --video demo/output/core-pipeline.mkv
  python3 scripts/diagnostics/cv-test-runner.py --video demo/output/core-pipeline.mkv --mode full

Output (in <video_dir>/analysis/<video_name>/):
  frames/           — extracted PNG frames
  annotated/        — frames with bounding box overlays
  elements.jsonl     — per-frame element data (window bboxes, text regions)
  ocr.jsonl          — per-frame OCR text (Tesseract)
  summary.json       — structured analysis summary
  report.html        — visual report with annotated frames
"""

import argparse
import json
import os
import subprocess
import sys
from pathlib import Path
from typing import Any

import cv2
import numpy as np

# Tesseract is optional — will be checked at runtime
try:
    import pytesseract
    HAS_TESSERACT = True
except ImportError:
    HAS_TESSERACT = False

try:
    from ultralytics import YOLO
    HAS_YOLO = True
except ImportError:
    HAS_YOLO = False


# ── Element Detection (from cv-element-detect.py) ────────────────────────────

WINDOW_TITLE_HEIGHT = 25
MENU_BAR_HEIGHT = 22
BUTTON_MIN_W = 40
BUTTON_MIN_H = 20
BUTTON_MAX_H = 45
DIALOG_MIN_W = 200
DIALOG_MIN_H = 80


def classify_region(x: int, y: int, w: int, h: int) -> str:
    aspect = w / max(h, 1)
    if h <= WINDOW_TITLE_HEIGHT and w > 200:
        return "title_bar"
    if h <= MENU_BAR_HEIGHT and 15 < w < 800:
        return "menu_bar"
    if BUTTON_MIN_W <= w <= 200 and BUTTON_MIN_H <= h <= BUTTON_MAX_H:
        return "button"
    if h >= 100 and w > 300:
        return "text_area"
    if 18 <= h <= 35 and w > 50:
        return "text_field"
    if w > DIALOG_MIN_W and h > DIALOG_MIN_H and h < 400:
        return "dialog"
    if w * h > 50000:
        return "panel"
    return "unknown"


def detect_rectangular_regions(img: np.ndarray) -> list[dict]:
    gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
    edges = cv2.Canny(gray, 30, 120)
    contours, _ = cv2.findContours(edges, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)

    regions = []
    for i, cnt in enumerate(contours):
        x, y, w, h = cv2.boundingRect(cnt)
        area = w * h
        if area < 400 or area > img.shape[0] * img.shape[1] * 0.95:
            continue
        if w < 15 or h < 15:
            continue
        regions.append({
            "id": i,
            "bbox": [int(x), int(y), int(w), int(h)],
            "type": classify_region(x, y, w, h),
            "area": int(area),
        })
    return regions


def detect_text_regions(img: np.ndarray) -> list[dict]:
    if not HAS_TESSERACT:
        return []
    gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
    try:
        data = pytesseract.image_to_data(gray, output_type=pytesseract.Output.DICT)
    except Exception:
        return []

    regions = []
    current_block = None
    for i in range(len(data["text"])):
        text = data["text"][i].strip()
        if not text:
            continue
        x, y, w, h = data["left"][i], data["top"][i], data["width"][i], data["height"][i]
        block_num = data["block_num"][i]
        conf = int(data["conf"][i])

        if current_block and current_block["block_num"] == block_num:
            current_block["lines"].append(text)
            bx, by, bw, bh = current_block["bbox"]
            current_block["bbox"] = [
                min(bx, x), min(by, y),
                max(bx + bw, x + w) - min(bx, x),
                max(by + bh, y + h) - min(by, y),
            ]
            current_block["confidence"] = max(current_block["confidence"], conf)
        else:
            if current_block:
                regions.append(current_block)
            current_block = {
                "block_num": block_num, "bbox": [x, y, w, h],
                "lines": [text], "text": text, "confidence": conf,
            }
    if current_block:
        regions.append(current_block)

    # Classify each text region
    for r in regions:
        txt = r["text"].lower()
        y_pos = r["bbox"][1]
        if y_pos < 40:
            r["type"] = "title_text"
        elif any(w in txt for w in ("file", "edit", "view", "help", "tools")):
            r["type"] = "menu_label"
        elif any(w in txt for w in ("ok", "cancel", "save", "open", "close",
                                     "yes", "no", "abort", "retry", "ignore")):
            r["type"] = "button_label"
        elif any(w in txt for w in ("error", "warning", "information", "confirm")):
            r["type"] = "dialog_title"
        else:
            r["type"] = "general_text"
    return regions


def find_click_targets(ocr_regions: list[dict]) -> dict[str, list[int]]:
    button_map = {
        "save": "save_button", "&save": "save_button",
        "cancel": "cancel_button", "&cancel": "cancel_button",
        "open": "open_button", "ok": "ok_button",
        "yes": "yes_button", "no": "no_button",
        "help": "help_button", "close": "close_button",
        "next": "next_button", "back": "back_button",
        "finish": "finish_button", "install": "install_button",
        "browse": "browse_button", "apply": "apply_button",
        "submit": "submit_button", "retry": "retry_button",
    }
    targets = {}
    for r in ocr_regions:
        text = r.get("text", "").lower()
        bbox = r.get("bbox", [0, 0, 0, 0])
        cx, cy = bbox[0] + bbox[2] // 2, bbox[1] + bbox[3] // 2
        for pattern, name in button_map.items():
            if pattern in text or text == pattern:
                targets[name] = [int(cx), int(cy)]
                break
    return targets


# ── Main Test Runner ─────────────────────────────────────────────────────────

class CVTestRunner:
    """Analyzes a single video file with CV+OCR, generates annotated report."""

    def __init__(self, video_path: str, output_dir: str = "",
                 frame_interval: float = 1.0, mode: str = "built-in"):
        self.video_path = Path(video_path)
        if not self.video_path.exists():
            raise FileNotFoundError(f"Video not found: {video_path}")

        self.video_name = self.video_path.stem
        self.frame_interval = frame_interval
        self.mode = mode

        if output_dir:
            self.out_dir = Path(output_dir)
        else:
            self.out_dir = self.video_path.parent / "analysis" / self.video_name
        self.out_dir.mkdir(parents=True, exist_ok=True)

        self.frames_dir = self.out_dir / "frames"
        self.annotated_dir = self.out_dir / "annotated"
        self.frames_dir.mkdir(exist_ok=True)
        self.annotated_dir.mkdir(exist_ok=True)

        self.yolo_model = None
        if mode == "full" and HAS_YOLO:
            self.yolo_model = self._load_yolo()

        self.results: list[dict] = []

    def _load_yolo(self):
        model_paths = [
            os.environ.get("YOLO_MODEL_PATH", ""),
            "/models/yolov8n.pt",
        ]
        for p in model_paths:
            if p and os.path.exists(p):
                try:
                    return YOLO(p)
                except Exception:
                    pass
        try:
            return YOLO("yolov8n.pt")
        except Exception as e:
            print(f"  YOLOv8 not loaded: {e}")
            return None

    def extract_frames(self) -> list[tuple[float, Path]]:
        """Extract frames from video. Returns [(timestamp_s, frame_path), ...]."""
        # Clean previous frames
        for f in self.frames_dir.glob("frame_*.png"):
            f.unlink()

        cmd = [
            "ffmpeg", "-y", "-v", "quiet",
            "-i", str(self.video_path),
            "-vf", "fps=1",  # 1 frame per second
            "-q:v", "2",
            f"{self.frames_dir}/frame_%04d.png",
        ]
        subprocess.run(cmd, capture_output=True)

        frames = []
        for png in sorted(self.frames_dir.glob("frame_*.png")):
            frame_num = int(png.stem.split("_")[1])
            # With fps=1: frame_0001.png = 0s, frame_0002.png = 1s, etc.
            timestamp = float(frame_num - 1)
            frames.append((timestamp, png))
        return frames

    def analyze_frame(self, img: np.ndarray, timestamp_s: float,
                      frame_path: Path) -> dict:
        """Run full analysis on a single frame."""
        h, w = img.shape[:2]
        result: dict[str, Any] = {
            "timestamp_s": round(timestamp_s, 1),
            "frame_path": str(frame_path),
            "resolution": f"{w}x{h}",
            "elements": {},
            "warnings": [],
        }

        # 1. Rectangular region detection
        regions = detect_rectangular_regions(img)
        result["elements"]["rect_regions"] = len(regions)
        result["elements"]["region_detail"] = regions[:15]  # top 15

        # 2. OCR text detection
        ocr_regions = detect_text_regions(img)
        result["elements"]["ocr_regions"] = len(ocr_regions)
        result["elements"]["ocr_detail"] = ocr_regions[:20]  # top 20
        result["text_summary"] = [r["text"] for r in ocr_regions[:20]]

        # 3. Click targets from OCR
        click_targets = find_click_targets(ocr_regions)
        result["click_targets"] = click_targets

        # 4. YOLO detection (mode: full only)
        if self.yolo_model:
            try:
                dets = self.yolo_model(img, verbose=False)
                yolo_objects = []
                for det in dets:
                    boxes = det.boxes
                    if boxes is not None and len(boxes) > 0:
                        for i in range(len(boxes)):
                            cls_id = int(boxes.cls[i])
                            cls_name = det.names.get(cls_id, f"class_{cls_id}")
                            x1, y1, x2, y2 = boxes.xyxy[i].tolist()
                            conf = float(boxes.conf[i])
                            if conf > 0.3:  # filter low confidence
                                yolo_objects.append({
                                    "label": cls_name,
                                    "bbox": [int(x1), int(y1), int(x2-x1), int(y2-y1)],
                                    "confidence": round(conf, 3),
                                })
                result["elements"]["yolo_objects"] = yolo_objects
            except Exception as e:
                result["elements"]["yolo_error"] = str(e)

        # 5. Warning detection
        warning_keywords = ("error", "warning", "fail", "abort", "denied",
                           "not found", "cannot", "unable", "exception")
        for r in ocr_regions:
            text = r.get("text", "").lower()
            if any(kw in text for kw in warning_keywords):
                result["warnings"].append({
                    "type": "warning_text",
                    "text": r["text"],
                    "bbox": r.get("bbox", []),
                    "message": f"Warning text detected: '{r['text']}'",
                })

        # Check for dialog windows
        dialog_windows = [r for r in regions if r["type"] in ("dialog", "button")]
        if dialog_windows:
            result["ui_state"] = "dialog_visible"
        elif any(r["type"] == "text_area" for r in regions):
            result["ui_state"] = "text_editor_visible"
        elif any(r["type"] == "menu_bar" for r in regions):
            result["ui_state"] = "menu_visible"
        else:
            result["ui_state"] = "idle"

        return result

    def annotate_frame(self, img: np.ndarray, result: dict) -> str:
        """Draw bounding boxes on the frame image. Returns path to annotated PNG."""
        annotated = img.copy()

        # Draw rectangular regions
        colors = {
            "title_bar": (0, 165, 255),    # orange
            "menu_bar": (255, 0, 0),        # blue
            "button": (0, 255, 0),          # green
            "text_area": (255, 255, 0),     # cyan
            "text_field": (0, 255, 255),    # yellow
            "dialog": (255, 0, 255),        # magenta
            "panel": (128, 128, 128),       # gray
            "unknown": (0, 0, 255),         # red
        }
        for r in result.get("elements", {}).get("region_detail", [])[:20]:
            x, y, w, h = r["bbox"]
            color = colors.get(r["type"], (0, 0, 255))
            cv2.rectangle(annotated, (x, y), (x + w, y + h), color, 2)
            cv2.putText(annotated, r["type"], (x, y - 4),
                        cv2.FONT_HERSHEY_SIMPLEX, 0.4, color, 1)

        # Draw OCR text bboxes
        for r in result.get("elements", {}).get("ocr_detail", [])[:15]:
            x, y, w, h = r["bbox"]
            rtype = r.get("type", "general_text")
            color = (0, 255, 0) if rtype == "button_label" else (200, 200, 200)
            cv2.rectangle(annotated, (x, y), (x + w, y + h), color, 1)
            cv2.putText(annotated, r["text"][:20], (x, y - 2),
                        cv2.FONT_HERSHEY_SIMPLEX, 0.35, color, 1)

        # Draw click targets
        for name, pos in result.get("click_targets", {}).items():
            cv2.circle(annotated, (pos[0], pos[1]), 8, (0, 0, 255), 2)
            cv2.putText(annotated, name, (pos[0] + 10, pos[1]),
                        cv2.FONT_HERSHEY_SIMPLEX, 0.5, (0, 0, 255), 1)

        # Save annotated frame
        frame_name = Path(result.get("frame_path", "frame.png")).stem
        ann_path = self.annotated_dir / f"{frame_name}_annotated.png"
        cv2.imwrite(str(ann_path), annotated)
        return str(ann_path)

    def run(self) -> dict:
        """Main entry point: extract frames, analyze, generate report."""
        print(f"CV Test Runner — {self.video_path.name}")
        print(f"  Mode: {self.mode}")
        print(f"  Frame interval: {self.frame_interval}s")
        print()

        # Extract frames
        frames = self.extract_frames()
        if not frames:
            print("ERROR: No frames extracted from video")
            return {"error": "no_frames", "video": str(self.video_path)}
        print(f"  Extracted {len(frames)} frames\n")

        # Analyze each frame
        warnings_total = 0
        frames_with_click_targets = 0
        click_targets_timeline = []

        for timestamp_s, frame_path in frames:
            img = cv2.imread(str(frame_path))
            if img is None:
                continue

            result = self.analyze_frame(img, timestamp_s, frame_path)
            annotated_path = self.annotate_frame(img, result)
            result["annotated_path"] = annotated_path
            self.results.append(result)

            # Progress output
            targets = result.get("click_targets", {})
            warnings = result.get("warnings", [])
            warnings_total += len(warnings)

            status = ""
            if targets:
                frames_with_click_targets += 1
                click_targets_timeline.append({
                    "time": timestamp_s,
                    "targets": targets,
                })
                names = list(targets.keys())
                status += f" targets={names}"
            if warnings:
                status += f" WARNINGS={len(warnings)}"
            if result.get("ui_state", "idle") != "idle":
                status += f" state={result['ui_state']}"

            text_preview = ", ".join(result.get("text_summary", [])[:3])
            print(f"  t={timestamp_s:5.1f}s  OCR={result['elements']['ocr_regions']:>3}"
                  f"  regions={result['elements']['rect_regions']:>3}"
                  f"  text=[{text_preview}]{status}")

        # Write elements.jsonl
        elements_path = self.out_dir / "elements.jsonl"
        with open(elements_path, "w", encoding="utf-8") as f:
            for r in self.results:
                # Strip image data for JSONL
                json_r = {k: v for k, v in r.items()
                          if k not in ("frame_data",)}
                f.write(json.dumps(json_r) + "\n")

        # Write OCR-only log
        ocr_path = self.out_dir / "ocr.jsonl"
        with open(ocr_path, "w", encoding="utf-8") as f:
            for r in self.results:
                ocr_entry = {
                    "t": r["timestamp_s"],
                    "text": r.get("text_summary", []),
                    "click_targets": r.get("click_targets", {}),
                    "warnings": r.get("warnings", []),
                    "ui_state": r.get("ui_state", "idle"),
                }
                f.write(json.dumps(ocr_entry) + "\n")

        # Build summary
        summary = {
            "video": str(self.video_path),
            "video_name": self.video_name,
            "mode": self.mode,
            "frame_interval_s": self.frame_interval,
            "frames_extracted": len(frames),
            "frames_analyzed": len(self.results),
            "frames_with_click_targets": frames_with_click_targets,
            "total_warnings": warnings_total,
            "click_targets_timeline": click_targets_timeline,
            "ui_states": {},
            "output_dir": str(self.out_dir),
            "output_files": {
                "elements": str(elements_path),
                "ocr": str(ocr_path),
                "summary": str(self.out_dir / "summary.json"),
                "report": str(self.out_dir / "report.html"),
            },
        }

        # Count UI states
        for r in self.results:
            state = r.get("ui_state", "idle")
            summary["ui_states"][state] = summary["ui_states"].get(state, 0) + 1

        # Write summary
        summary_path = self.out_dir / "summary.json"
        with open(summary_path, "w", encoding="utf-8") as f:
            json.dump(summary, f, indent=2)

        # Generate HTML report
        report_path = self._generate_report(summary)
        summary["output_files"]["report"] = str(report_path)

        return summary

    def _generate_report(self, summary: dict) -> Path:
        """Generate a visual HTML report."""
        report_path = self.out_dir / "report.html"

        # Build frame cards
        frame_cards = []
        for r in self.results:
            ann_path = r.get("annotated_path", "")
            ann_rel = os.path.relpath(ann_path, self.out_dir) if ann_path else ""
            targets = r.get("click_targets", {})
            warnings = r.get("warnings", [])
            text = r.get("text_summary", [])[:8]

            card_class = "card"
            if warnings:
                card_class += " warning"
            if targets:
                card_class += " targets"

            frame_cards.append(f"""
            <div class="{card_class}">
              <div class="card-header">
                <strong>t={r['timestamp_s']:.1f}s</strong>
                <span class="state">{r.get('ui_state', 'idle')}</span>
              </div>
              {f'<img src="{ann_rel}" loading="lazy">' if ann_rel else ''}
              <div class="text-regions">
                {"".join(f'<span class="ocr-text">&apos;{t}&apos;</span>' for t in text)}
              </div>
              {"".join(f'<div class="target">[click] {name}: ({pos[0]}, {pos[1]})</div>'
                       for name, pos in targets.items())}
              {"".join(f'<div class="warning">[WARN] {w["message"]}</div>' for w in warnings)}
            </div>""")

        html = f"""<!DOCTYPE html>
<html><head>
  <meta charset="utf-8">
  <title>CV Analysis — {self.video_name}</title>
  <style>
    body {{ font-family: system-ui, sans-serif; margin: 20px; background: #1a1a2e; color: #e0e0e0; }}
    h1 {{ color: #e94560; }}
    .summary {{ display: flex; gap: 20px; flex-wrap: wrap; margin-bottom: 30px; }}
    .stat {{ background: #16213e; padding: 12px 20px; border-radius: 8px; }}
    .stat-value {{ font-size: 1.8em; font-weight: bold; color: #0f3460; display:block; }}
    .stat-label {{ color: #a0a0b0; font-size: 0.8em; }}
    .cards {{ display: grid; grid-template-columns: repeat(auto-fill, minmax(280px, 1fr)); gap: 15px; }}
    .card {{ background: #16213e; border-radius: 8px; overflow: hidden; border: 2px solid #0f3460; }}
    .card.warning {{ border-color: #e94560; }}
    .card.targets {{ border-color: #00b894; }}
    .card-header {{ padding: 8px 12px; background: #0f3460; display: flex; justify-content: space-between; }}
    .state {{ font-size: 0.8em; color: #a0a0b0; }}
    .card img {{ width: 100%; display: block; }}
    .text-regions {{ padding: 8px 12px; display: flex; flex-wrap: wrap; gap: 4px; }}
    .ocr-text {{ background: #0f3460; padding: 2px 6px; border-radius: 4px; font-size: 0.75em; }}
    .target {{ padding: 4px 12px; color: #00b894; font-size: 0.8em; }}
    .warning {{ padding: 4px 12px; color: #e94560; font-size: 0.8em; }}
    .timeline {{ margin-top: 30px; }}
    .timeline-entry {{ padding: 6px 12px; border-left: 2px solid #0f3460; margin-left: 10px; }}
  </style></head><body>
  <h1>CV Analysis — {self.video_name}</h1>
  <div class="summary">
    <div class="stat"><span class="stat-value">{summary['frames_analyzed']}</span><span class="stat-label">Frames Analyzed</span></div>
    <div class="stat"><span class="stat-value">{summary['frames_with_click_targets']}</span><span class="stat-label">With Click Targets</span></div>
    <div class="stat"><span class="stat-value">{summary['total_warnings']}</span><span class="stat-label">Warnings</span></div>
    <div class="stat"><span class="stat-value">{summary.get('mode', 'built-in')}</span><span class="stat-label">Mode</span></div>
  </div>
  <h2>Click Target Timeline</h2>
  <div class="timeline">
    {''.join(f'<div class="timeline-entry">t={t["time"]:.1f}s: {", ".join(f"{k} ({v[0]},{v[1]})" for k,v in t["targets"].items())}</div>' for t in summary['click_targets_timeline'])}
  </div>
  <h2>Frames ({len(frame_cards)})</h2>
  <div class="cards">
    {''.join(frame_cards)}
  </div>
</body></html>"""

        with open(report_path, "w", encoding="utf-8") as f:
            f.write(html)
        return report_path


def main():
    parser = argparse.ArgumentParser(
        description="CV/OCR Test Runner for WineBot demo videos")
    parser.add_argument("--video", required=True,
                        help="Path to MKV video file")
    parser.add_argument("--output", default="",
                        help="Output directory (default: <video_dir>/analysis/<name>/)")
    parser.add_argument("--frame-interval", type=float, default=1.0,
                        help="Seconds between extracted frames")
    parser.add_argument("--mode", choices=["built-in", "full"], default="built-in",
                        help="Analysis mode: built-in (OpenCV+Tesseract) or full (YOLOv8)")
    args = parser.parse_args()

    if not HAS_TESSERACT:
        print("WARNING: pytesseract not available — OCR text disabled", file=sys.stderr)
        print("  Install: pip install pytesseract", file=sys.stderr)
        print("  System:  apt-get install tesseract-ocr-eng", file=sys.stderr)
        print()

    runner = CVTestRunner(
        video_path=args.video,
        output_dir=args.output,
        frame_interval=args.frame_interval,
        mode=args.mode,
    )

    try:
        summary = runner.run()
    except Exception as e:
        print(f"ERROR: {e}", file=sys.stderr)
        import traceback
        traceback.print_exc()
        sys.exit(1)

    print("\nAnalysis complete!")
    if "error" in summary:
        print(f"   Error:  {summary['error']}")
        return
    print(f"   Video:       {summary['video_name']}")
    print(f"   Frames:      {summary['frames_analyzed']}")
    print(f"   Click targets in {summary['frames_with_click_targets']} frames")
    print(f"   Warnings:    {summary['total_warnings']}")
    print(f"   Output:      {summary['output_dir']}/")
    for name, path in summary.get("output_files", {}).items():
        print(f"     {name}: {path}")


if __name__ == "__main__":
    main()
