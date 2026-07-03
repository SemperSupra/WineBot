#!/usr/bin/env python3
# EXECUTION: EITHER — works with screenshots from file or capture; needs OpenCV+Tesseract
# STATUS: ACTIVE — OpenCV contour detection + Tesseract OCR for live/offline element detection
"""CV + OCR UI element detector for WineBot screenshots.

Takes a screenshot (via import/xwd or image file), detects UI elements using
OpenCV contour/edge analysis, reads text via Tesseract OCR, and outputs
structured JSON of what's on screen.

Usage:
  python3 cv-element-detect.py --screenshot              # Capture + analyze
  python3 cv-element-detect.py --image /path/file.png     # Analyze existing
  python3 cv-element-detect.py --watch --interval 0.5    # Continuous mode
"""

import argparse
import json
import os
import subprocess
import sys
import time
from datetime import UTC, datetime

import cv2
import numpy as np
import pytesseract


class UIElementDetector:
    """Detects UI elements and reads text from Wine desktop screenshots."""

    # Known UI element patterns (class names, dimensions, positions)
    WINDOW_TITLE_HEIGHT = 25
    MENU_BAR_HEIGHT = 22
    BUTTON_MIN_W = 40
    BUTTON_MIN_H = 20
    BUTTON_MAX_H = 45
    EDIT_MIN_H = 18
    TEXT_AREA_MIN_H = 100
    DIALOG_MIN_W = 200
    DIALOG_MIN_H = 80

    def __init__(self):
        self.screen_width = 1280
        self.screen_height = 720

    def capture(self) -> np.ndarray:
        """Capture current Wine desktop screenshot. Returns BGR image."""
        tmp = "/tmp/cv_capture.png"
        try:
            subprocess.run(
                ["import", "-window", "root", tmp],
                capture_output=True, timeout=5,
            )
            if os.path.exists(tmp) and os.path.getsize(tmp) > 100:
                return cv2.imread(tmp)
        except Exception:
            pass
        # Fallback: xwd
        try:
            subprocess.run(
                ["xwd", "-root", "-out", "/tmp/cv_capture.xwd"],
                capture_output=True, timeout=5,
            )
            subprocess.run(
                ["convert", "xwd:/tmp/cv_capture.xwd", tmp],
                capture_output=True, timeout=5,
            )
            if os.path.exists(tmp):
                return cv2.imread(tmp)
        except Exception:
            pass
        return None

    def load_image(self, path: str):
        img = cv2.imread(path)
        if img is None:
            print(f"WARNING: Could not load image from {path}", file=sys.stderr)
        return img

    def detect_rectangular_regions(self, img: np.ndarray) -> list[dict]:
        """Find rectangular UI regions using contour analysis on edge map."""
        gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
        edges = cv2.Canny(gray, 30, 120)
        contours, _ = cv2.findContours(edges, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)

        regions = []
        for i, cnt in enumerate(contours):
            x, y, w, h = cv2.boundingRect(cnt)
            area = w * h
            # Filter noise: must be reasonably sized
            if area < 400 or area > img.shape[0] * img.shape[1] * 0.95:
                continue
            if w < 15 or h < 15:
                continue

            # Classify by shape and position
            elem_type = self._classify_region(x, y, w, h, area, img.shape)
            regions.append({
                "id": i,
                "bbox": [int(x), int(y), int(w), int(h)],
                "type": elem_type,
                "area": int(area),
                "position": self._position_name(x, y, w, h, img.shape),
            })
        return regions

    def detect_text_regions(self, img: np.ndarray) -> list[dict]:
        """Use Tesseract to find and read text in the image."""
        gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
        # Tesseract with bounding boxes
        try:
            data = pytesseract.image_to_data(gray, output_type=pytesseract.Output.DICT)
        except Exception:
            return []

        text_regions = []
        current_block = None

        for i in range(len(data["text"])):
            text = data["text"][i].strip()
            if not text:
                continue

            x, y, w, h = (
                data["left"][i], data["top"][i],
                data["width"][i], data["height"][i],
            )
            block_num = data["block_num"][i]
            conf = int(data["conf"][i])

            # Merge into blocks
            if current_block and current_block["block_num"] == block_num:
                current_block["lines"].append(text)
                # Expand bbox
                bx, by, bw, bh = current_block["bbox"]
                current_block["bbox"] = [
                    min(bx, x), min(by, y),
                    max(bx + bw, x + w) - min(bx, x),
                    max(by + bh, y + h) - min(by, y),
                ]
                current_block["confidence"] = max(current_block["confidence"], conf)
            else:
                if current_block:
                    text_regions.append(current_block)
                current_block = {
                    "block_num": block_num,
                    "bbox": [x, y, w, h],
                    "lines": [text],
                    "text": text,
                    "confidence": conf,
                }

        if current_block:
            text_regions.append(current_block)

        # Post-process: merge blocks into full text strings
        for r in text_regions:
            r["type"] = self._classify_text_region(r)
        return text_regions

    def detect_windows(self, img: np.ndarray) -> list[dict]:
        """Detect application windows by finding dark title bars with light text."""
        gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
        # Apply adaptive threshold to find title bar regions
        binary = cv2.adaptiveThreshold(
            gray, 255, cv2.ADAPTIVE_THRESH_GAUSSIAN_C,
            cv2.THRESH_BINARY, 15, 5,
        )
        contours, _ = cv2.findContours(binary, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)

        windows = []
        for cnt in contours:
            x, y, w, h = cv2.boundingRect(cnt)
            if w < 200 or h < 80 or h > 600:
                continue
            # Window-like: reasonably large rectangle
            if w > 0.3 * img.shape[1] or h > 100:
                # Try to read title text from this region
                roi = img[y : y + 30, x : x + w]
                if roi.size > 0:
                    try:
                        title = pytesseract.image_to_string(
                            roi, config="--psm 7"
                        ).strip()
                    except Exception:
                        title = ""
                else:
                    title = ""

                windows.append({
                    "bbox": [int(x), int(y), int(w), int(h)],
                    "title": title,
                    "width": int(w),
                    "height": int(h),
                })

        # Deduplicate nested windows
        return self._deduplicate_windows(windows)

    def analyze(self, img, label: str = "") -> dict:
        """Full analysis: windows, text, elements. Returns structured result."""
        if img is None:
            return {"error": "capture_failed", "screen": "1280x720",
                    "windows": [], "key_text": [], "timestamp": datetime.now(UTC).isoformat()}
        self.screen_height, self.screen_width = img.shape[:2]
        ts = datetime.now(UTC).isoformat()

        windows = self.detect_windows(img)
        text_regions = self.detect_text_regions(img)
        rect_regions = self.detect_rectangular_regions(img)

        # Cross-reference: which text belongs to which window
        interesting_windows = [w for w in windows if w.get("title")]
        window_titles = [w["title"] for w in interesting_windows]

        # Extract key phrases (dialog titles, button labels, menu items)
        key_text = []
        for tr in text_regions:
            if tr["confidence"] > 30 and len(tr["text"]) > 2:
                key_text.append(tr["text"])

        return {
            "timestamp": ts,
            "label": label,
            "screen": f"{self.screen_width}x{self.screen_height}",
            "windows_count": len(windows),
            "windows": interesting_windows,
            "window_titles": window_titles,
            "text_regions": len(text_regions),
            "key_text": key_text[:40],  # top 40 text snippets
            "rectangular_regions": len(rect_regions),
            "detected_elements": rect_regions[:20],  # top 20
        }

    # ── Private helpers ──

    def _classify_region(self, x: int, y: int, w: int, h: int,
                         area: int, shape: tuple) -> str:
        w / max(h, 1)
        sh, sw = shape[:2]

        if h <= self.WINDOW_TITLE_HEIGHT and w > 200:
            return "title_bar"
        if h <= self.MENU_BAR_HEIGHT and 15 < w < 800:
            return "menu_bar"
        if self.BUTTON_MIN_W <= w <= 200 and self.BUTTON_MIN_H <= h <= self.BUTTON_MAX_H:
            return "button"
        if h >= self.TEXT_AREA_MIN_H and w > 300:
            return "text_area"
        if self.EDIT_MIN_H <= h <= 35 and w > 50:
            return "text_field"
        if w > self.DIALOG_MIN_W and h > self.DIALOG_MIN_H and h < 400:
            return "dialog"
        if area > 50000:
            return "panel"
        return "unknown"

    def _position_name(self, x: int, y: int, w: int, h: int,
                        shape: tuple) -> str:
        sh, sw = shape[:2]
        cx = x + w // 2
        cy = y + h // 2
        parts = []
        if cy < 60: parts.append("top")
        elif cy > sh - 60: parts.append("bottom")
        else: parts.append("middle")
        if cx < 200: parts.append("left")
        elif cx > sw - 200: parts.append("right")
        else: parts.append("center")
        return "_".join(parts)

    def _classify_text_region(self, region: dict) -> str:
        text = region["text"].lower()
        y = region["bbox"][1]
        if y < 40:
            return "title_text"
        if any(w in text for w in ("file", "edit", "view", "help", "tools")):
            return "menu_label"
        if any(w in text for w in ("ok", "cancel", "save", "open", "close",
                                    "yes", "no", "abort", "retry", "ignore")):
            return "button_label"
        if any(w in text for w in ("error", "warning", "information", "confirm")):
            return "dialog_title"
        return "general_text"

    def _deduplicate_windows(self, windows: list[dict]) -> list[dict]:
        """Remove windows that are fully contained within larger windows."""
        windows.sort(key=lambda w: w["width"] * w["height"], reverse=True)
        result = []
        for w in windows:
            contained = False
            for r in result:
                if (w["bbox"][0] >= r["bbox"][0]
                    and w["bbox"][1] >= r["bbox"][1]
                    and w["bbox"][0] + w["width"] <= r["bbox"][0] + r["width"]
                    and w["bbox"][1] + w["height"] <= r["bbox"][1] + r["height"]):
                    contained = True
                    break
            if not contained:
                result.append(w)
        return result


def main():
    parser = argparse.ArgumentParser(description="CV element detector")
    parser.add_argument("--screenshot", action="store_true", help="Capture screenshot")
    parser.add_argument("--image", help="Analyze existing image file")
    parser.add_argument("--watch", action="store_true", help="Continuous mode")
    parser.add_argument("--interval", type=float, default=1.0, help="Watch interval (s)")
    parser.add_argument("--output", default="-", help="Output file (- for stdout)")
    parser.add_argument("--label", default="auto", help="Label for this analysis")
    parser.add_argument("--jsonl", help="Append to JSONL log file")
    args = parser.parse_args()

    detector = UIElementDetector()

    if args.watch:
        print("CV Element Detector — watch mode. Ctrl+C to stop.")
        while True:
            img = detector.capture()
            result = detector.analyze(img, args.label)
            result["timestamp"] = datetime.now(UTC).isoformat()
            print(json.dumps({
                "windows": result["window_titles"],
                "key_text": result["key_text"][:10],
            }))
            if args.jsonl:
                with open(args.jsonl, "a") as f:
                    f.write(json.dumps(result) + "\n")
            time.sleep(args.interval)
        return

    # Single-shot
    img = detector.load_image(args.image) if args.image else detector.capture()

    result = detector.analyze(img, args.label)
    result["timestamp"] = datetime.now(UTC).isoformat()

    if args.jsonl:
        with open(args.jsonl, "a") as f:
            f.write(json.dumps(result) + "\n")

    output = json.dumps(result, indent=2)
    if args.output == "-":
        print(output)
    else:
        with open(args.output, "w") as f:
            f.write(output)


if __name__ == "__main__":
    main()
