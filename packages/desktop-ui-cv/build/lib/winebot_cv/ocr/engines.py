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

        # FAST mode: single PSM pass without preprocessing.
        # PSM 11 = sparse text — best for scattered UI labels, buttons, menus.
        # Saves 3x vs the 3-PSM pipeline. Enable with OCR_FAST=1.
        fast = os.environ.get("OCR_FAST", "0") == "1"

        if fast:
            gray = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)
            try:
                data = pytesseract.image_to_data(
                    gray, output_type=pytesseract.Output.DICT,
                    config="--psm 11"
                )
                return self._merge_ocr_results([data])
            except Exception as e:
                print(f"[tesseract] Fast OCR error: {e}", file=sys.stderr)
                return []

        # QUALITY mode (default): CLAHE + bilateral + multi-PSM
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

    Auto-detects PP-OCRv6 models (tiny/small/medium) and falls back to v5.
    Supports variant selection via constructor or PADDLE_ONNX_VARIANT env var.

    Variant sizes: tiny (1.8+4.5MB, 97ms), small (10+21MB, 150ms),
                  medium (62+77MB, 200ms).
    """

    name = "paddle_onnx"
    available = False

    def __init__(self, variant: str = None):
        self._session_det = None
        self._session_rec = None
        self._char_dict = None
        self._variant = variant
        self._model_variant = "unknown"

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
        """Load ONNX detection and recognition models. Respects variant override."""
        try:
            # Priority: explicit variant > env var > auto (tiny > small > medium > v5)
            variant = self._variant
            if not variant:
                variant = os.environ.get("PADDLE_ONNX_VARIANT", "")
            if not variant:
                variant = None

            if variant:
                variants_to_try = [variant]
            else:
                variants_to_try = ["tiny", "small", "medium"]

            for variant in variants_to_try:
                # Map variant names to file prefixes (medium → med)
                prefix_map = {"medium": "med", "small": "small", "tiny": "tiny"}
                prefix = prefix_map.get(variant, variant)
                det_path = self._find_model(f"ppocr_v6_{prefix}_det.onnx")
                rec_path = self._find_model(f"ppocr_v6_{prefix}_rec.onnx")
                dict_path = self._find_model(f"ppocr_v6_{variant}_rec.yml")
                if det_path and rec_path:
                    self._model_variant = variant
                    break
            else:
                # Fallback to v5 models
                det_path = self._find_model("ppocr_det.onnx")
                rec_path = self._find_model("ppocr_rec.onnx")
                dict_path = self._find_model("ppocr_keys_v1.txt")
                self._model_variant = "v5"

            if not det_path or not rec_path:
                print("[paddle_onnx] ONNX models not found. "
                      "Download from HF: PaddlePaddle/PP-OCRv6_*_onnx", file=sys.stderr)
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

            # Load character dictionary — try .txt file, then parse from inference.yml
            if dict_path and os.path.isfile(dict_path):
                with open(dict_path, "r", encoding="utf-8") as f:
                    content = f.read().strip()
                # Check if it's YAML (contains "PostProcess") vs plain text
                if "PostProcess" in content:
                    import yaml
                    cfg = yaml.safe_load(content)
                    self._char_dict = cfg["PostProcess"]["character_dict"]
                else:
                    self._char_dict = [line.strip() for line in content.split("\n") if line.strip()]
            elif self._find_model("inference.yml"):
                import yaml
                yml_path = self._find_model("inference.yml")
                with open(yml_path, "r") as f:
                    cfg = yaml.safe_load(f.read())
                self._char_dict = cfg.get("PostProcess", {}).get("character_dict", [])
            else:
                # Default: alphanumeric + common symbols
                import string
                self._char_dict = ["'"] + list(string.printable[:95])

            self.available = True
            providers_used = self._session_det.get_providers()
            print(f"[paddle_onnx] PP-OCRv6 {self._model_variant} loaded "
                  f"(det: {os.path.basename(det_path)}, "
                  f"rec: {os.path.basename(rec_path)}, "
                  f"providers: {providers_used})", file=sys.stderr)

        except Exception as e:
            print(f"[paddle_onnx] Failed to load models: {e}", file=sys.stderr)
            self.available = False

    def detect_text(self, image: np.ndarray) -> List[Dict]:
        if not self.available or self._session_det is None:
            return []

        try:
            h, w = image.shape[:2]

            # ── Detection: DB probability map → bounding boxes ──
            det_in = {self._session_det.get_inputs()[0].name:
                      self._preprocess_det(image)}
            det_out = self._session_det.run(None, det_in)
            prob_map = np.squeeze(det_out[0])  # [H/4, W/4]

            boxes = self._boxes_from_prob_map(prob_map, (h, w))
            if not boxes:
                return []

            # ── Recognition: batched CTC decode all crops ──
            regions = []
            if not boxes:
                return []

            # Preprocess all crops
            crops = []
            valid_boxes = []
            for bx1, by1, bx2, by2 in boxes:
                crop = image[int(by1):int(by2), int(bx1):int(bx2)]
                if crop.size > 0 and crop.shape[0] >= 8 and crop.shape[1] >= 8:
                    crops.append(self._preprocess_rec(crop))
                    valid_boxes.append((bx1, by1, bx2, by2))

            if not crops:
                return []

            # Batch all crops into single inference call
            # Mobile rec model input: [batch, 3, 48, N]
            # Pad to max width for batching
            max_w = max(c.shape[3] for c in crops)
            batch_blob = np.zeros((len(crops), 3, 48, max_w), dtype=np.float32)
            for i, c in enumerate(crops):
                _, _, hc, wc = c.shape
                batch_blob[i, :, :, :wc] = c

            rec_in = {self._session_rec.get_inputs()[0].name: batch_blob}
            rec_out = self._session_rec.run(None, rec_in)

            # Decode each output
            for i, (bx1, by1, bx2, by2) in enumerate(valid_boxes):
                try:
                    text, conf = self._ctc_decode(rec_out[0][i:i+1])
                    if text and len(text.strip()) >= 2:
                        regions.append({
                            "text": text.strip(),
                            "bbox": [int(bx1), int(by1), int(bx2-bx1), int(by2-by1)],
                            "confidence": int(conf * 100),
                            "block_num": i + 1,
                            "lines": [text.strip()],
                        })
                except Exception:
                    continue

            return regions

        except Exception as e:
            print(f"[paddle_onnx] Inference error: {e}", file=sys.stderr)
            return []

    def _preprocess_det(self, image):
        """Preprocess for detection: resize to 32-multiple, BGR→RGB, normalize."""
        h, w = image.shape[:2]
        # PP-OCRv5 det model: resize longest side to 960, keep aspect
        max_side = 960
        scale = max_side / max(h, w)
        nh, nw = int(round(h * scale / 32)) * 32, int(round(w * scale / 32)) * 32
        resized = cv2.resize(cv2.cvtColor(image, cv2.COLOR_BGR2RGB), (nw, nh))
        # Normalize: mean=[0.485,0.456,0.406], std=[0.229,0.224,0.225]
        blob = (resized.astype(np.float32) / 255.0
                - np.array([0.485, 0.456, 0.406])) / np.array([0.229, 0.224, 0.225])
        return blob.transpose(2, 0, 1)[np.newaxis, ...].astype(np.float32)

    def _boxes_from_prob_map(self, prob_map, orig_shape):
        """Convert DB probability map to bounding boxes via contour detection."""
        h, w = orig_shape
        ph, pw = prob_map.shape

        # Binary threshold
        binary = (prob_map > 0.3).astype(np.uint8) * 255

        # Find connected components
        num_labels, labels, stats, _ = cv2.connectedComponentsWithStats(
            binary, connectivity=8
        )

        boxes = []
        scale_x = w / pw
        scale_y = h / ph

        for i in range(1, num_labels):
            area = stats[i, cv2.CC_STAT_AREA]
            if area < 10:  # Minimum text region (in model-space pixels)
                continue

            x1, y1 = stats[i, cv2.CC_STAT_LEFT], stats[i, cv2.CC_STAT_TOP]
            bx2, by2 = (
                x1 + stats[i, cv2.CC_STAT_WIDTH],
                y1 + stats[i, cv2.CC_STAT_HEIGHT],
            )

            # Scale to original image
            boxes.append((
                max(0, int(x1 * scale_x - 2)),
                max(0, int(y1 * scale_y - 2)),
                min(w, int(bx2 * scale_x + 2)),
                min(h, int(by2 * scale_y + 2)),
            ))

        # Sort top-to-bottom, left-to-right
        boxes.sort(key=lambda b: (b[1], b[0]))
        return boxes

    def _preprocess_rec(self, crop):
        """Preprocess crop for recognition: 3x48xN, RGB, ImageNet-normalized."""
        h, w = crop.shape[:2]
        rec_h = 48
        ratio = rec_h / max(h, 1)
        new_w = max(4, min(int(w * ratio), 320))

        # PP-OCRv5 server rec model expects RGB, 3-channel
        rgb = cv2.cvtColor(crop, cv2.COLOR_BGR2RGB)
        resized = cv2.resize(rgb, (new_w, rec_h))
        blob = resized.astype(np.float32)
        # ImageNet normalization
        blob = (blob / 255.0 - np.array([0.5, 0.5, 0.5])) / np.array([0.5, 0.5, 0.5])
        return blob.transpose(2, 0, 1)[np.newaxis, ...].astype(np.float32)

    def _ctc_decode(self, output):
        """CTC greedy decode recognition output [T, 1, num_classes]."""
        squeezed = np.squeeze(output)
        if squeezed.ndim == 1:
            squeezed = squeezed[np.newaxis, :]
        # squeezed: [T, num_classes]
        indices = np.argmax(squeezed, axis=-1)
        probs = np.max(squeezed, axis=-1)

        chars = []
        confs = []
        blank = 0  # CTC blank token
        prev = -1

        for idx, prob in zip(indices, probs):
            idx = int(idx)
            # idx 0 = CTC blank, idx 1+ maps to char_dict[idx-1]
            if idx > 0 and idx != prev and self._char_dict and idx <= len(self._char_dict):
                chars.append(self._char_dict[idx - 1])
                confs.append(float(prob))
            prev = idx

        text = "".join(chars)
        confidence = float(np.mean(confs)) if confs else 0
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

    # Return cached engine if backend hasn't changed (including variant suffix)
    engine_key = backend or os.environ.get("OCR_BACKEND", "tesseract").lower()
    if _ocr_engine is not None and getattr(_ocr_engine, '_engine_key', '') == engine_key:
        return _ocr_engine

    if backend == "paddle" or backend == "paddleocr":
        _ocr_engine = PaddleOCREngine()
    elif backend == "paddle_onnx" or backend == "onnx":
        _ocr_engine = PaddleOCRONNXEngine()
    elif backend and backend.startswith("paddle_onnx:"):
        # Variant override: paddle_onnx:tiny, paddle_onnx:small, paddle_onnx:medium
        variant = backend.split(":", 1)[1]
        _ocr_engine = PaddleOCRONNXEngine(variant=variant)
    else:
        _ocr_engine = TesseractEngine()

    if not _ocr_engine.available:
        print(f"[ocr] {_ocr_engine.name} requested but not available, "
              f"falling back to tesseract", file=sys.stderr)
        _ocr_engine = TesseractEngine()

    # Tag engine with the key used for caching decisions
    _ocr_engine._engine_key = engine_key
    return _ocr_engine


def available_backends() -> Dict[str, bool]:
    """Return dict of backend name -> available."""
    backends = {
        "tesseract": TesseractEngine().available,
        "paddleocr": PaddleOCREngine().available,
        "paddle_onnx": PaddleOCRONNXEngine().available,
    }
    # Add v6 variants if available
    for v in ["tiny", "small", "medium"]:
        e = PaddleOCRONNXEngine(variant=v)
        if e.available:
            backends[f"paddle_onnx:{v}"] = True
    return backends


def current_backend() -> str:
    """Return the currently active OCR backend name."""
    engine = get_ocr_engine()
    return engine.name
