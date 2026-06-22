#!/usr/bin/env python3
# EXECUTION: EITHER — runs in sidecar container or on host
# STATUS: ACTIVE — swappable OCR engine abstraction (Tesseract / PaddleOCR)
"""
Swappable OCR engine abstraction for WineBot CV sidecar.

Engine selection via OCR_BACKEND env var:
  OCR_BACKEND=tesseract   (default, always available, ~50MB, 82-94% accuracy)
  OCR_BACKEND=paddle      (requires paddlepaddle + paddleocr, ~95-97% accuracy)

Usage:
  from ocr_engines import get_ocr_engine
  engine = get_ocr_engine()
  regions = engine.detect_text(image)  # -> List[Dict]

Each engine returns identical structured output:
  [{"text": "Save", "bbox": [x,y,w,h], "confidence": 95, "block_num": 3, "lines": ["Save"]}]
"""

import os
import sys
from typing import Dict, List, Optional

import cv2
import numpy as np


# ── Base class ────────────────────────────────────────────────────────────────

class OCREngine:
    """Base class for swappable OCR engines."""

    name: str = "base"
    available: bool = False

    def detect_text(self, image: np.ndarray) -> List[Dict]:
        """Detect text regions in an image.

        Args:
            image: BGR image as numpy array.

        Returns:
            List of dicts: {"text": str, "bbox": [x,y,w,h], "confidence": int,
                           "block_num": int, "lines": [str]}
        """
        raise NotImplementedError


# ── Tesseract Engine ──────────────────────────────────────────────────────────

class TesseractEngine(OCREngine):
    """Tesseract OCR via pytesseract. Lightweight, always available."""

    name = "tesseract"
    available = False

    def __init__(self):
        try:
            import pytesseract  # noqa: F401
            self.available = True
        except ImportError:
            self.available = False

    def detect_text(self, image: np.ndarray) -> List[Dict]:
        if not self.available:
            return []

        import pytesseract
        gray = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)

        # Wine desktop preprocessing: enhance low-contrast UI text
        # 1. CLAHE (Contrast Limited Adaptive Histogram Equalization) —
        #    critical for Wine's lower-contrast text rendering vs native Windows
        clahe = cv2.createCLAHE(clipLimit=2.0, tileGridSize=(8, 8))
        enhanced = clahe.apply(gray)

        # 2. Bilateral filter — reduce noise while preserving text edges
        denoised = cv2.bilateralFilter(enhanced, 9, 75, 75)

        # 3. Try multiple PSM modes to maximize UI text detection:
        #    PSM 6 = uniform block of text (best for dialog text, button labels)
        #    PSM 11 = sparse text (best for scattered UI elements, menu items)
        #    PSM 3 = fully automatic (fallback)
        all_data = []
        for psm in [6, 11, 3]:
            try:
                config = f"--psm {psm} -c tessedit_char_whitelist=''"
                data = pytesseract.image_to_data(
                    denoised, output_type=pytesseract.Output.DICT, config=config
                )
                all_data.append(data)
            except Exception:
                pass

        if not all_data:
            try:
                data = pytesseract.image_to_data(
                    denoised, output_type=pytesseract.Output.DICT
                )
                all_data = [data]
            except Exception as e:
                print(f"[tesseract] OCR error: {e}", file=sys.stderr)
                return []

        # Merge results from all PSM modes, deduplicate by text+bbox overlap
        return self._merge_ocr_results(all_data)

    def _merge_ocr_results(self, all_data: list) -> List[Dict]:
        """Merge OCR results from multiple PSM modes, deduplicating overlaps."""
        regions = []
        seen_texts = set()

        for data in all_data:
            for i in range(len(data["text"])):
                text = data["text"][i].strip()
                if not text or len(text) < 2:  # skip single-char noise
                    continue

                conf = int(data["conf"][i])
                if conf < 40:  # raised from default 30 for higher quality
                    continue

                x, y, w, h = data["left"][i], data["top"][i], data["width"][i], data["height"][i]

                # Deduplicate: same text at roughly same position
                key = (text.lower(), x // 10, y // 10)
                if key in seen_texts:
                    continue
                seen_texts.add(key)

                regions.append({
                    "text": text,
                    "bbox": [x, y, w, h],
                    "confidence": conf,
                    "block_num": int(data["block_num"][i]),
                    "lines": [text],
                })

        # Post-process: classify each text region by UI role
        for r in regions:
            r["ui_role"] = self._classify_ui_role(r)

        return regions

    def _classify_ui_role(self, region: Dict) -> str:
        """Classify OCR-detected text by its UI role on a Windows/Wine desktop."""
        text = region["text"].lower()
        y = region["bbox"][1]

        # Position-based: top of screen = title bar
        if y < 30:
            return "title_text"

        # Text-based classification
        menu_words = {"file", "edit", "view", "help", "tools", "window", "format",
                      "settings", "options", "media", "playback", "audio", "video",
                      "navigation", "bookmarks", "debug"}
        if any(w == text for w in menu_words):
            return "menu_label"

        button_words = {"ok", "cancel", "save", "open", "close", "yes", "no",
                        "abort", "retry", "ignore", "apply", "submit", "next",
                        "back", "finish", "install", "browse", "remove", "add",
                        "create", "delete", "edit", "refresh", "update", "continue"}
        if any(w in text for w in button_words):
            return "button_label"

        dialog_words = {"error", "warning", "information", "confirm", "message",
                        "notice", "alert", "caution", "critical"}
        if any(w in text for w in dialog_words):
            return "dialog_title"

        # Heuristic: short text (1-3 words) in middle of screen = likely UI label
        word_count = len(text.split())
        if word_count <= 3 and 30 <= y <= 690:
            return "ui_label"

        return "general_text"


# ── PaddleOCR Engine ──────────────────────────────────────────────────────────

class PaddleOCREngine(OCREngine):
    """PaddleOCR engine. Higher accuracy, layout-aware, requires paddlepaddle."""

    name = "paddleocr"
    available = False

    def __init__(self):
        try:
            from paddleocr import PaddleOCR  # noqa: F401
            self.available = True
        except ImportError:
            self.available = False

        self._engine = None

    def _get_engine(self):
        if self._engine is None and self.available:
            try:
                from paddleocr import PaddleOCR
                # use_angle_cls=True for rotated text detection
                # lang='en' for English; add 'ch' etc. for multi-language
                self._engine = PaddleOCR(
                    use_angle_cls=True,
                    lang=os.environ.get("PADDLEOCR_LANG", "en"),
                    use_gpu=os.environ.get("PADDLEOCR_GPU", "false").lower() == "true",
                    show_log=False,
                )
                print("[paddleocr] Engine initialized", file=sys.stderr)
            except Exception as e:
                print(f"[paddleocr] Init error: {e}", file=sys.stderr)
                self.available = False
        return self._engine

    def detect_text(self, image: np.ndarray) -> List[Dict]:
        engine = self._get_engine()
        if engine is None:
            return []

        try:
            # PaddleOCR expects RGB, OpenCV gives BGR
            rgb = cv2.cvtColor(image, cv2.COLOR_BGR2RGB)
            results = engine.ocr(rgb, cls=True)
        except Exception as e:
            print(f"[paddleocr] Detection error: {e}", file=sys.stderr)
            return []

        if not results or not results[0]:
            return []

        regions = []
        for i, line in enumerate(results[0]):
            if line is None:
                continue
            # PaddleOCR 3.x format: [[[x1,y1],[x2,y2],[x3,y3],[x4,y4]], (text, confidence)]
            bbox_points = line[0]
            text, confidence = line[1]

            if not text or not text.strip():
                continue

            # Convert 4-point bbox to [x, y, w, h]
            xs = [p[0] for p in bbox_points]
            ys = [p[1] for p in bbox_points]
            x, y = int(min(xs)), int(min(ys))
            w, h = int(max(xs) - x), int(max(ys) - y)

            regions.append({
                "text": text.strip(),
                "bbox": [x, y, w, h],
                "confidence": round(float(confidence) * 100),
                "block_num": i + 1,
                "lines": [text.strip()],
            })

        return regions


# ── Factory ───────────────────────────────────────────────────────────────────

_ocr_engine: Optional[OCREngine] = None


def get_ocr_engine(backend: Optional[str] = None) -> OCREngine:
    """Get or create the configured OCR engine.

    Args:
        backend: "tesseract", "paddle", or None (reads OCR_BACKEND env var, default "tesseract")
    """
    global _ocr_engine

    if backend is None:
        backend = os.environ.get("OCR_BACKEND", "tesseract").lower()

    # Return cached engine if backend hasn't changed
    if _ocr_engine is not None and _ocr_engine.name == backend:
        return _ocr_engine

    if backend == "paddle" or backend == "paddleocr":
        _ocr_engine = PaddleOCREngine()
    else:
        _ocr_engine = TesseractEngine()

    if not _ocr_engine.available:
        print(f"[ocr] {_ocr_engine.name} requested but not available, "
              f"falling back to tesseract", file=sys.stderr)
        _ocr_engine = TesseractEngine()

    return _ocr_engine


def available_backends() -> Dict[str, bool]:
    """Return dict of backend name -> available."""
    return {
        "tesseract": TesseractEngine().available,
        "paddleocr": PaddleOCREngine().available,
    }


def current_backend() -> str:
    """Return the currently active OCR backend name."""
    engine = get_ocr_engine()
    return engine.name
