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
                # PaddleOCR 3.x (paddlex-based) has different init params than 2.x.
                # Try 3.x-style init first, fall back to 2.x-style.
                lang = os.environ.get("PADDLEOCR_LANG", "en")
                try:
                    # PaddleOCR 3.7+ — PaddleX backend, no use_gpu param
                    self._engine = PaddleOCR(lang=lang, use_angle_cls=True)
                except (TypeError, ValueError):
                    # PaddleOCR 2.x — legacy params
                    self._engine = PaddleOCR(
                        use_angle_cls=True,
                        lang=lang,
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
            # PaddleOCR 3.x (PaddleX) doesn't accept cls/use_angle_cls in ocr()
            # PaddleOCR 2.x accepts cls=True for text orientation classification
            try:
                results = engine.ocr(rgb, cls=True)
            except (TypeError, ValueError):
                results = engine.ocr(rgb)
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


# ── PaddleOCR ONNX Engine ─────────────────────────────────────────────────────

class PaddleOCRONNXEngine(OCREngine):
    """PaddleOCR via ONNX Runtime. Bypasses the ONEDNN CPU bug.

    Requires exported ONNX models from PP-OCRv5 (detection + recognition).
    Place models in models/ocr/ or set PADDLE_ONNX_DIR env var.

    Falls back to Tesseract if ONNX models are not available.
    Provides a download script to export from a PaddleOCR-capable environment.
    """

    name = "paddle_onnx"
    available = False

    def __init__(self):
        self._session_det = None
        self._session_rec = None
        self._char_dict = None
        self._input_size = (640, 640)

        try:
            import onnxruntime as ort
            self._ort = ort
            # Try GPU first, fall back to CPU
            gpu_available = "CUDAExecutionProvider" in ort.get_available_providers()
            self._providers = (
                ["CUDAExecutionProvider", "CPUExecutionProvider"]
                if gpu_available
                else ["CPUExecutionProvider"]
            )
            self._onnx_available = True
        except ImportError:
            self._onnx_available = False

        # Try to load models
        if self._onnx_available:
            self._load_models()

    def _find_model(self, name: str) -> Optional[str]:
        """Search for an ONNX model file in standard locations."""
        candidates = [
            os.path.join(os.environ.get("PADDLE_ONNX_DIR", ""), name),
            os.path.join("models", "ocr", name),
            os.path.join(os.path.dirname(__file__), "..", "..", "models", "ocr", name),
            os.path.join("/models", "ocr", name),
        ]
        for p in candidates:
            if p and os.path.isfile(p):
                return p
        return None

    def _load_models(self):
        """Load ONNX detection and recognition models."""
        try:
            det_path = self._find_model("ppocr_det.onnx")
            rec_path = self._find_model("ppocr_rec.onnx")
            dict_path = self._find_model("ppocr_keys_v1.txt")

            if not det_path or not rec_path:
                print("[paddle_onnx] ONNX models not found. "
                      "Export from PaddleOCR: paddle2onnx --model_dir=...", file=sys.stderr)
                self.available = False
                return

            sess_opts = self._ort.SessionOptions()
            sess_opts.graph_optimization_level = self._ort.GraphOptimizationLevel.ORT_ENABLE_ALL

            self._session_det = self._ort.InferenceSession(
                det_path, sess_opts, providers=self._providers
            )
            self._session_rec = self._ort.InferenceSession(
                rec_path, sess_opts, providers=self._providers
            )

            # Load character dictionary
            if dict_path and os.path.isfile(dict_path):
                with open(dict_path, "r", encoding="utf-8") as f:
                    self._char_dict = [line.strip() for line in f if line.strip()]
            else:
                # Default: alphanumeric + common symbols
                import string
                self._char_dict = ["'"] + list(string.printable[:95])

            self.available = True
            providers_used = self._session_det.get_providers()
            print(f"[paddle_onnx] Models loaded (providers: {providers_used})", file=sys.stderr)

        except Exception as e:
            print(f"[paddle_onnx] Failed to load models: {e}", file=sys.stderr)
            self.available = False

    def detect_text(self, image: np.ndarray) -> List[Dict]:
        if not self.available:
            return []

        if self._session_det is None:
            return []

        try:
            h, w = image.shape[:2]

            # ── Detection: find text bounding boxes ──
            # Preprocess for detection model
            scale = min(self._input_size[0] / h, self._input_size[1] / w)
            new_h, new_w = int(h * scale), int(w * scale)
            resized = cv2.resize(image, (new_w, new_h))
            padded = np.ones(
                (self._input_size[0], self._input_size[1], 3), dtype=np.float32
            ) * 127.5
            padded[:new_h, :new_w] = resized

            # Normalize to [-1, 1]
            blob = (padded - 127.5) / 127.5
            blob = blob.transpose(2, 0, 1)[np.newaxis, ...].astype(np.float32)

            det_input = {self._session_det.get_inputs()[0].name: blob}
            det_output = self._session_det.run(None, det_input)[0]

            # Post-process detection output to get bounding boxes
            boxes = self._postprocess_det(det_output, (h, w), scale)

            if not boxes:
                return []

            # ── Recognition: read text in each box ──
            regions = []
            for i, (bx1, by1, bx2, by2) in enumerate(boxes):
                try:
                    # Crop and preprocess for recognition
                    crop = image[int(by1):int(by2), int(bx1):int(bx2)]
                    if crop.size == 0:
                        continue

                    # Resize to recognition model input (typically 32x320)
                    rec_h = 32
                    rec_w = 320
                    crop_h, crop_w = crop.shape[:2]
                    ratio = rec_h / max(crop_h, 1)
                    new_w_rec = min(int(crop_w * ratio), rec_w)
                    if new_w_rec < 4:
                        continue

                    crop_resized = cv2.resize(crop, (new_w_rec, rec_h))
                    # Normalize
                    crop_blob = ((crop_resized.astype(np.float32) - 127.5) / 127.5
                                 .transpose(2, 0, 1)[np.newaxis, ...])

                    rec_input = {self._session_rec.get_inputs()[0].name: crop_blob}
                    rec_output = self._session_rec.run(None, rec_input)[0]

                    # Decode recognition output
                    text, conf = self._decode_rec(rec_output)

                    if text and len(text.strip()) >= 2:
                        regions.append({
                            "text": text.strip(),
                            "bbox": [int(bx1), int(by1), int(bx2 - bx1), int(by2 - by1)],
                            "confidence": int(conf),
                            "block_num": i + 1,
                            "lines": [text.strip()],
                        })
                except Exception:
                    continue

            return regions

        except Exception as e:
            print(f"[paddle_onnx] Inference error: {e}", file=sys.stderr)
            return []

    def _postprocess_det(self, output, orig_shape, scale):
        """Post-process detection model output to bounding boxes.

        Simplified: assumes output is [N, 4, 2] quad boxes or [N, 4] rect boxes.
        This is a minimal implementation — full PaddleOCR post-processing
        (DB post-process) requires the detection head logic.
        """
        boxes = []
        h, w = orig_shape

        # Handle different output shapes from different model versions
        output = np.squeeze(output)

        if output.ndim == 2 and output.shape[1] == 4:
            # Rect boxes [x1, y1, x2, y2] — direct
            for det in output:
                x1, y1, x2, y2 = det
                x1, y1 = x1 / scale, y1 / scale
                x2, y2 = x2 / scale, y2 / scale
                if x2 > x1 and y2 > y1:
                    boxes.append((x1, y1, x2, y2))
        elif output.ndim == 3:
            # Quad boxes [4, 2] per detection
            for det in output:
                xs = [p[0] for p in det]
                ys = [p[1] for p in det]
                x1, y1 = min(xs) / scale, min(ys) / scale
                x2, y2 = max(xs) / scale, max(ys) / scale
                if x2 > x1 + 5 and y2 > y1 + 5:
                    boxes.append((x1, y1, x2, y2))

        # Clip to image bounds
        boxes = [(max(0, x1), max(0, y1), min(w, x2), min(h, y2))
                 for x1, y1, x2, y2 in boxes]
        return boxes

    def _decode_rec(self, output):
        """Decode recognition model output (CTC) to text and confidence."""
        if self._char_dict is None:
            return ("", 0)

        output = np.squeeze(output)
        if output.ndim == 1:
            output = output[np.newaxis, :]

        indices = np.argmax(output, axis=1)
        probs = np.max(output, axis=1)

        # CTC greedy decode: collapse repeats, remove blank (index 0)
        chars = []
        confs = []
        prev_idx = -1
        for idx, prob in zip(indices, probs):
            if idx != prev_idx and idx > 0 and idx < len(self._char_dict):
                chars.append(self._char_dict[idx])
                confs.append(prob)
            prev_idx = idx

        text = "".join(chars)
        confidence = float(np.mean(confs)) * 100 if confs else 0
        return text, confidence


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
    elif backend == "paddle_onnx" or backend == "onnx":
        _ocr_engine = PaddleOCRONNXEngine()
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
        "paddle_onnx": PaddleOCRONNXEngine().available,
    }


def current_backend() -> str:
    """Return the currently active OCR backend name."""
    engine = get_ocr_engine()
    return engine.name
