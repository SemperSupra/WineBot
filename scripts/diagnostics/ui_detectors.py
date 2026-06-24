#!/usr/bin/env python3
# EXECUTION: EITHER — runs in sidecar container or on host
# STATUS: ACTIVE — swappable UI element detector abstraction
"""
Swappable UI element detector abstraction for WineBot CV sidecar.

Detector selection via UI_DETECTOR env var:
  UI_DETECTOR=contour          (default, OpenCV edge/contour heuristics, CPU, ~0.01s)
  UI_DETECTOR=yolo             (YOLO with OmniParser UI weights, GPU, ~0.2s)
  UI_DETECTOR=omniparser       (OmniParser v2: YOLO detection + Florence-2 captions, GPU, ~0.6s)
  UI_DETECTOR=screenparser     (ScreenParser YOLOv11-L, 55 classes, GPU, ~0.3s)
  UI_DETECTOR=screenparser_wine(ScreenParser fine-tuned on Wine data, mAP50=0.951, GPU, ~0.3s)
  UI_DETECTOR=wine             (YOLOv8n fine-tuned on Wine data, mAP50=0.918, GPU, ~0.22s)
  UI_DETECTOR=uidetr1          (UI-DETR-1 RF-DETR, class-agnostic, GPU, ~0.29s)

Usage:
  from ui_detectors import get_ui_detector
  detector = get_ui_detector()
  elements = detector.detect(image)  # -> List[Dict]

Each detector returns identical structured output:
  [{"id": 0, "bbox": [x,y,w,h], "type": "button", "label": "Save",
    "confidence": 0.97, "interactive": true}]
"""

import os
import sys
import subprocess
from pathlib import Path
from typing import Dict, List, Optional, Tuple

import cv2
import numpy as np


# ── Constants (tuned for Wine desktop at 1280x720) ────────────────────────────

# Wine-specific: text is often lower contrast, buttons can be smaller
WINDOW_TITLE_HEIGHT = 25
MENU_BAR_HEIGHT = 22
BUTTON_MIN_W, BUTTON_MIN_H = 30, 18   # lowered from 40,20 for Wine's smaller buttons
BUTTON_MAX_H = 50                      # raised from 45 for Wine dialog buttons
DIALOG_MIN_W, DIALOG_MIN_H = 180, 70   # lowered from 200,80 for smaller Wine dialogs
TEXT_AREA_MIN_H = 80                   # lowered from 100 for Notepad-like editors
TEXT_FIELD_MIN_H = 16                  # lowered from 18
TEXT_FIELD_MAX_H = 40                  # raised from 35

# Contour detection thresholds (tuned for Wine's lower-contrast rendering)
CANNY_LOW = 20    # lowered from 30 — Wine renders softer edges than native Windows
CANNY_HIGH = 80   # lowered from 120

# Area filters — tuned for Wine desktop at 1280x720
MIN_CONTOUR_AREA = 150   # lowered from 400 to catch small buttons
MAX_CONTOUR_RATIO = 0.95  # fraction of total screen (unchanged)

# Morphological closing kernel — connects fragmented Wine window borders
MORPH_KERNEL_SIZE = 3  # 3x3 kernel for closing small gaps in window edges


# ── Base class ────────────────────────────────────────────────────────────────

class UIDetector:
    """Base class for swappable UI element detectors."""

    name: str = "base"
    available: bool = False
    uses_gpu: bool = False

    def _move_model_to_gpu(self):
        """Move a YOLO or torch model to GPU if available. Called by subclasses after loading."""
        try:
            import torch
            if not torch.cuda.is_available():
                return
            # Try different model attribute layouts
            for attr in ['model', '_model']:
                m = getattr(self, attr, None)
                if m is None:
                    continue
                # YOLO model — has .to() method directly
                if hasattr(m, 'to') and not hasattr(m, 'model'):
                    device = next(m.model.parameters()).device
                    if str(device) == "cpu":
                        m.to("cuda")
                # Ultralytics DetectionModel wrapper
                elif hasattr(m, 'model') and hasattr(m.model, 'parameters'):
                    device = next(m.model.parameters()).device
                    if str(device) == "cpu":
                        m.model.to("cuda")
        except Exception:
            pass

    def detect(self, image: np.ndarray) -> List[Dict]:
        """Detect UI elements in a screenshot.

        Args:
            image: BGR image as numpy array.

        Returns:
            List of dicts: {"id": int, "bbox": [x,y,w,h], "type": str,
                           "label": str, "confidence": float, "interactive": bool}
        """
        raise NotImplementedError

    def classify_ui_state(self, image: np.ndarray, elements: List[Dict]) -> str:
        """Classify overall UI state from detected elements."""
        types = {e["type"] for e in elements}
        if "dialog" in types:
            return "dialog_visible"
        if "text_area" in types:
            return "text_editor_visible"
        if "menu_bar" in types:
            return "menu_visible"
        if "button" in types:
            return "interactive_ui_visible"
        return "idle"


# ── Contour Detector (always available, built-in) ────────────────────────────

class ContourDetector(UIDetector):
    """OpenCV edge/contour heuristics. Fast, CPU-only, always available."""

    name = "contour"
    available = True
    uses_gpu = False

    def _classify_region(self, x: int, y: int, w: int, h: int) -> str:
        aspect = w / max(h, 1)

        if h <= WINDOW_TITLE_HEIGHT and w > 200:
            return "title_bar"
        if h <= MENU_BAR_HEIGHT and 15 < w < 800:
            return "menu_bar"
        if BUTTON_MIN_W <= w <= 200 and BUTTON_MIN_H <= h <= BUTTON_MAX_H:
            return "button"
        if h >= TEXT_AREA_MIN_H and w > 300:
            return "text_area"
        if TEXT_FIELD_MIN_H <= h <= TEXT_FIELD_MAX_H and w > 50:
            return "text_field"
        if w > DIALOG_MIN_W and h > DIALOG_MIN_H and h < 400:
            return "dialog"
        if w * h > 50000:
            return "panel"
        return "unknown"

    def _is_interactive(self, elem_type: str) -> bool:
        return elem_type in ("button", "text_field", "menu_bar")

    def detect(self, image: np.ndarray) -> List[Dict]:
        gray = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)

        # Wine-specific preprocessing: CLAHE for softer Wine window borders
        clahe = cv2.createCLAHE(clipLimit=1.5, tileGridSize=(8, 8))
        enhanced = clahe.apply(gray)

        # Morphological closing to connect fragmented contour edges (Wine artifact)
        kernel = cv2.getStructuringElement(
            cv2.MORPH_RECT, (MORPH_KERNEL_SIZE, MORPH_KERNEL_SIZE)
        )
        closed = cv2.morphologyEx(enhanced, cv2.MORPH_CLOSE, kernel)

        edges = cv2.Canny(closed, CANNY_LOW, CANNY_HIGH)
        contours, _ = cv2.findContours(edges, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)

        elements = []
        for i, cnt in enumerate(contours):
            x, y, w, h = cv2.boundingRect(cnt)
            area = w * h
            screen_area = image.shape[0] * image.shape[1]

            if area < MIN_CONTOUR_AREA or area > screen_area * MAX_CONTOUR_RATIO:
                continue
            if w < 10 or h < 10:
                continue

            elem_type = self._classify_region(x, y, w, h)
            elements.append({
                "id": i,
                "bbox": [int(x), int(y), int(w), int(h)],
                "type": elem_type,
                "label": elem_type,
                "confidence": 0.5,
                "interactive": self._is_interactive(elem_type),
            })

        # Detect tint2 taskbar — characteristic dark bar at bottom of Wine desktop
        taskbar = self._detect_taskbar(image)
        elements.extend(taskbar)

        return elements

    def _detect_taskbar(self, image: np.ndarray) -> List[Dict]:
        """Detect tint2 taskbar: dark ~30px bar at bottom of Wine desktop."""
        h, w = image.shape[:2]
        bottom_strip = image[h - 35:h, 0:w]
        if bottom_strip.size == 0:
            return []
        gray = cv2.cvtColor(bottom_strip, cv2.COLOR_BGR2GRAY)
        if gray.mean() < 80:  # tint2 is dark
            return [{
                "id": -1, "bbox": [0, h - 35, w, 35],
                "type": "taskbar", "label": "tint2_taskbar",
                "confidence": 0.9, "interactive": False,
            }]
        return []


# ── YOLO UI Detector ─────────────────────────────────────────────────────────

class YOLOUIDetector(UIDetector):
    """YOLO with OmniParser's fine-tuned UI detection weights.

    Detects interactable regions, icons, buttons, text fields on screens.
    Uses ultralytics YOLO with UI-specific weights.
    """

    name = "yolo"
    available = False
    uses_gpu = False

    # COCO classes that overlap with UI elements (for fallback when UI weights unavailable)
    UI_COCO_MAP = {
        "laptop": "window",
        "tvmonitor": "window",
        "cell phone": "window",
        "book": "text_area",
        "keyboard": "text_field",
        "mouse": "button",
    }

    def __init__(self):
        try:
            from ultralytics import YOLO  # noqa: F401
            self.available = True
        except ImportError:
            self.available = False
        self._model = None

    def _load_model(self):
        if self._model is not None:
            return self._model

        from ultralytics import YOLO

        # Priority: shared model cache > project-local > env var > COCO fallback
        model_paths = [
            "/models/yolo/omniparser_icon_detect.pt",
            os.path.join(os.path.dirname(__file__), "..", "..",
                         "models", "yolo", "omniparser_icon_detect.pt"),
            os.environ.get("YOLO_MODEL_PATH", ""),
            "/models/yolo/yolov8n.pt",
        ]

        for p in model_paths:
            if not p or not os.path.exists(p):
                continue
            try:
                self._model = YOLO(p)
                # Force GPU if available (ultralytics doesn't always auto-detect)
                self._move_model_to_gpu()
                print(f"[yolo] Loaded from {p} (device: {self._model.device})", file=sys.stderr)
                if "cuda" in str(self._model.device):
                    self.uses_gpu = True
                # Log what classes this model detects
                n_classes = len(self._model.names) if hasattr(self._model, 'names') else 0
                sample_classes = list(self._model.names.values())[:5] if n_classes else []
                print(f"[yolo] {n_classes} classes: {sample_classes}", file=sys.stderr)
                return self._model
            except Exception as e:
                print(f"[yolo] Failed to load {p}: {e}", file=sys.stderr)

        # Fallback
        try:
            print("[yolo] No UI weights found, using yolov8n (COCO — "
                  "limited UI value)", file=sys.stderr)
            self._model = YOLO("yolov8n.pt")
            self._ensure_gpu()
            return self._model
        except Exception as e:
            print(f"[yolo] Failed: {e}", file=sys.stderr)
            return None

    def _is_interactive(self, cls_name: str, elem_type: str) -> bool:
        """Determine if a detected object is likely interactive UI."""
        interactive_labels = {"button", "text_field", "dropdown", "checkbox",
                              "radio", "slider", "scrollbar", "menu", "link",
                              "icon", "clickable"}
        return cls_name.lower() in interactive_labels or elem_type in interactive_labels

    def _classify_ui_type(self, cls_name: str, bbox: List[int], img_shape: Tuple) -> str:
        """Map YOLO class to UI element type."""
        h, w = img_shape[:2]
        x, y, bw, bh = bbox

        # OmniParser-trained classes (when using their weights)
        omni_types = {
            "interactable": "button",
            "icon": "button",
            "text": "text_field",
            "image": "panel",
            "button": "button",
        }

        cls_lower = cls_name.lower()
        if cls_lower in omni_types:
            return omni_types[cls_lower]

        # Geometry-based fallback
        if bh <= WINDOW_TITLE_HEIGHT and bw > 200:
            return "title_bar"
        if bh <= MENU_BAR_HEIGHT:
            return "menu_bar"
        if BUTTON_MIN_W <= bw <= 200 and BUTTON_MIN_H <= bh <= BUTTON_MAX_H:
            return "button"
        if bh >= TEXT_AREA_MIN_H and bw > 300:
            return "text_area"
        if 18 <= bh <= 35 and bw > 50:
            return "text_field"
        if bw > DIALOG_MIN_W and bh > DIALOG_MIN_H and bh < 400:
            return "dialog"

        return "interactable" if self._is_interactive(cls_name, "unknown") else "unknown"

    def detect(self, image: np.ndarray) -> List[Dict]:
        model = self._load_model()
        if model is None:
            return []

        try:
            # Lower conf + higher iou for OmniParser-style dense UI detection
            dets = model(image, verbose=False, conf=0.15, iou=0.45)
        except TypeError:
            # Older ultralytics versions don't accept conf/iou params
            try:
                dets = model(image, verbose=False)
            except Exception as e:
                print(f"[yolo] Detection error: {e}", file=sys.stderr)
                return []
        except Exception as e:
            print(f"[yolo] Detection error: {e}", file=sys.stderr)
            return []

        elements = []
        element_id = 0

        for det in dets:
            boxes = det.boxes
            if boxes is None or len(boxes) == 0:
                continue

            for i in range(len(boxes)):
                cls_id = int(boxes.cls[i])
                cls_name = det.names.get(cls_id, f"class_{cls_id}")
                x1, y1, x2, y2 = boxes.xyxy[i].tolist()
                conf = float(boxes.conf[i])

                # OmniParser "icon" class: accept lower confidence
                # (UI icons are diverse and harder for YOLO to be certain about)
                min_conf = 0.15 if cls_name == "icon" else 0.3
                if conf < min_conf:
                    continue

                bbox = [int(x1), int(y1), int(x2 - x1), int(y2 - y1)]

                # Classify: OmniParser's "icon" → geometry-based UI type
                elem_type = self._classify_ui_type(cls_name, bbox, image.shape)

                elements.append({
                    "id": element_id,
                    "bbox": bbox,
                    "type": elem_type,
                    "label": cls_name,
                    "confidence": round(conf, 3),
                    "interactive": self._is_interactive(cls_name, elem_type) or cls_name == "icon",
                })
                element_id += 1

        return elements


# ── OmniParser v2 Detector ───────────────────────────────────────────────────

class OmniParserDetector(UIDetector):
    """OmniParser v2: YOLOv8 interactable detection + Florence-2 functional captions.

    Produces elements with functional labels: "this button saves the file",
    "this opens a folder browser", etc. Requires GPU, ~0.6s/frame on RTX 4090.
    """

    name = "omniparser"
    available = False
    uses_gpu = True

    def __init__(self):
        self._yolo_available = False
        self._florence_available = False

        try:
            from ultralytics import YOLO  # noqa: F401
            self._yolo_available = True
        except ImportError:
            pass

        try:
            import transformers  # noqa: F401
            self._florence_available = True
        except ImportError:
            pass

        self.available = self._yolo_available
        self._yolo_model = None
        self._florence_model = None
        self._florence_processor = None

    def _load_yolo(self):
        if self._yolo_model is None:
            # Use YOLOUIDetector's loading logic
            yolo = YOLOUIDetector()
            self._yolo_model = yolo._load_model()
        return self._yolo_model

    def _load_florence(self):
        """Load Florence-2 for functional icon captioning."""
        if self._florence_model is not None or not self._florence_available:
            return

        try:
            from transformers import AutoProcessor, AutoModelForCausalLM

            model_id = os.environ.get(
                "FLORENCE_MODEL",
                "microsoft/Florence-2-base"
            )
            print(f"[omniparser] Loading Florence-2: {model_id}...", file=sys.stderr)

            self._florence_model = AutoModelForCausalLM.from_pretrained(
                model_id, trust_remote_code=True
            ).to("cpu")
            self._florence_processor = AutoProcessor.from_pretrained(
                model_id, trust_remote_code=True
            )
            print("[omniparser] Florence-2 loaded", file=sys.stderr)
        except Exception as e:
            print(f"[omniparser] Florence-2 not available: {e}", file=sys.stderr)
            self._florence_available = False

    def _caption_element(self, image: np.ndarray, bbox: List[int]) -> str:
        """Generate a functional caption for a UI element using Florence-2."""
        self._load_florence()
        if self._florence_model is None:
            return ""

        x, y, w, h = bbox
        # Crop to element region with padding
        pad = 10
        x1 = max(0, x - pad)
        y1 = max(0, y - pad)
        x2 = min(image.shape[1], x + w + pad)
        y2 = min(image.shape[0], y + h + pad)
        roi = image[y1:y2, x1:x2]

        if roi.size == 0:
            return ""

        try:
            rgb = cv2.cvtColor(roi, cv2.COLOR_BGR2RGB)
            from PIL import Image
            pil_image = Image.fromarray(rgb)

            inputs = self._florence_processor(
                text="<OD>",
                images=pil_image,
                return_tensors="pt"
            )
            generated_ids = self._florence_model.generate(
                input_ids=inputs["input_ids"],
                pixel_values=inputs["pixel_values"],
                max_new_tokens=50,
                num_beams=3,
            )
            caption = self._florence_processor.batch_decode(
                generated_ids, skip_special_tokens=True
            )[0]
            return caption.strip()
        except Exception:
            return ""

    def detect(self, image: np.ndarray) -> List[Dict]:
        """Full OmniParser pipeline: YOLO detection + Florence-2 captions."""
        model = self._load_yolo()
        if model is None:
            return []

        try:
            dets = model(image, verbose=False)
        except Exception as e:
            print(f"[omniparser] Detection error: {e}", file=sys.stderr)
            return []

        elements = []
        element_id = 0

        for det in dets:
            boxes = det.boxes
            if boxes is None or len(boxes) == 0:
                continue

            for i in range(len(boxes)):
                cls_id = int(boxes.cls[i])
                cls_name = det.names.get(cls_id, f"class_{cls_id}")
                x1, y1, x2, y2 = boxes.xyxy[i].tolist()
                conf = float(boxes.conf[i])

                if conf < 0.3:
                    continue

                bbox = [int(x1), int(y1), int(x2 - x1), int(y2 - y1)]

                # Classify UI type
                yolo_ui = YOLOUIDetector()
                elem_type = yolo_ui._classify_ui_type(cls_name, bbox, image.shape)

                # Generate functional caption (expensive — only for high-confidence elements)
                label = cls_name
                if conf > 0.7:
                    caption = self._caption_element(image, bbox)
                    if caption:
                        label = caption

                elements.append({
                    "id": element_id,
                    "bbox": bbox,
                    "type": elem_type,
                    "label": label,
                    "confidence": round(conf, 3),
                    "interactive": True,  # OmniParser only detects interactable regions
                })
                element_id += 1

        return elements


# ── UI-DETR-1 Detector ────────────────────────────────────────────────────────

class UIDETR1Detector(UIDetector):
    """UI-DETR-1 by racineai/TW3 — class-agnostic interactable element detector.

    Uses RF-DETR-M (DINOv2 backbone, 33.7M params) fine-tuned on 2656 screenshots
    with 150K+ bounding boxes. MIT license.

    Finds 63% more elements than OmniParser (82.3 avg vs 50.6).
    WebClick accuracy: 70.8% (vs OmniParser 58.8%).
    """

    name = "uidetr1"
    available = False
    uses_gpu = True

    def __init__(self):
        self._model = None
        try:
            import rfdetr  # noqa: F401
            self._rfdetr_available = True
        except ImportError:
            self._rfdetr_available = False
            return

        self.available = True

    def _load_model(self):
        if self._model is not None:
            return self._model

        # Priority: shared model cache > project-local > env var
        import torch
        device = "cuda" if torch.cuda.is_available() else "cpu"

        checkpoint_paths = [
            os.path.join("/models", "uidetr1", "model.pth"),
            os.environ.get("UIDETR1_MODEL_PATH", ""),
            os.path.join(os.path.dirname(__file__), "..", "..",
                         "models", "uidetr1", "model.pth"),
        ]

        for ckpt in checkpoint_paths:
            if not ckpt or not os.path.isfile(ckpt):
                continue
            try:
                from rfdetr import RFDETR

                self._model = RFDETR.from_checkpoint(ckpt)
                self._model.optimize_for_inference()
                if device == "cuda":
                    try:
                        self._model.model.to("cuda")
                    except Exception:
                        pass  # RFDETR ModelContext doesn't always expose .to()
                self.uses_gpu = device == "cuda"
                print(f"[uidetr1] Loaded from {ckpt} (device: {device})", file=sys.stderr)
                return self._model
            except Exception as e:
                print(f"[uidetr1] Failed to load {ckpt}: {e}", file=sys.stderr)

        print("[uidetr1] No checkpoint found. Download with: "
              "hf_hub_download('racineai/UI-DETR-1', 'model.pth', "
              "local_dir='models/uidetr1')", file=sys.stderr)
        self.available = False
        return None

    def _has_cuda(self) -> bool:
        try:
            import torch
            return torch.cuda.is_available()
        except ImportError:
            return False

    def detect(self, image: np.ndarray) -> List[Dict]:
        model = self._load_model()
        if model is None:
            return []

        try:
            detections = model.predict(image, threshold=0.3)
        except Exception as e:
            print(f"[uidetr1] Detection error: {e}", file=sys.stderr)
            return []

        # supervision.Detections object: .xyxy, .confidence, .class_id, .data
        elements = []
        n = len(detections) if hasattr(detections, '__len__') else 0
        if n == 0:
            return []

        class_names = detections.data.get("class_name", []) if hasattr(detections, 'data') else []

        for i in range(n):
            x1, y1, x2, y2 = detections.xyxy[i].tolist()
            conf = float(detections.confidence[i])
            cls_id = int(detections.class_id[i])
            label = class_names[cls_id] if cls_id < len(class_names) else f"class_{cls_id}"

            bbox = [int(x1), int(y1), int(x2 - x1), int(y2 - y1)]
            elem_type = self._classify_ui_type(label, bbox, image.shape)

            elements.append({
                "id": i,
                "bbox": bbox,
                "type": elem_type,
                "label": label,
                "confidence": round(conf, 3),
                "interactive": True,
            })

        return elements

    def _classify_ui_type(self, label: str, bbox: List[int], img_shape: tuple) -> str:
        """Classify UI element by geometry (UI-DETR-1 is class-agnostic)."""
        x, y, bw, bh = bbox
        h, w = img_shape[:2]

        if bh <= WINDOW_TITLE_HEIGHT and bw > 200:
            return "title_bar"
        if bh <= MENU_BAR_HEIGHT and 15 < bw < 800:
            return "menu_bar"
        if btn_check(bw, bh):  # Reuse constants
            return "button"
        if bh >= TEXT_AREA_MIN_H and bw > 300:
            return "text_area"
        if 18 <= bh <= 35 and bw > 50:
            return "text_field"
        if bw > DIALOG_MIN_W and bh > DIALOG_MIN_H and bh < 400:
            return "dialog"

        return "interactable"


def btn_check(bw, bh):
    return BUTTON_MIN_W <= bw <= 200 and BUTTON_MIN_H <= bh <= BUTTON_MAX_H


# ── ScreenParser Detector ─────────────────────────────────────────────────────

class ScreenParserDetector(UIDetector):
    """ScreenParser by IBM/ETH (docling-project) — 55-class UI widget detector.

    Model: YOLOv11-L (25.3M params), trained on 1.45M screenshots with 25.6M
    annotations. Apache 2.0 license. Released May 2026.

    Detects buttons, text fields, dropdowns, checkboxes, radio buttons,
    scroll bars, toggles, tabs, icons, menus, and 45 more widget types.
    """

    name = "screenparser"
    available = False
    uses_gpu = False

    # Map ScreenParser's 55 classes to our simplified UI taxonomy
    CLASS_MAP = {
        "button": "button", "icon_button": "button", "toggle_button": "button",
        "text_field": "text_field", "search_field": "text_field",
        "checkbox": "checkbox", "radio_button": "radio",
        "dropdown": "dropdown", "combo_box": "dropdown",
        "scroll_bar": "scrollbar", "slider": "slider",
        "tab": "tab", "tab_bar": "tab",
        "menu": "menu_bar", "menu_item": "menu_bar",
        "title_bar": "title_bar", "window_control": "button",
        "text_area": "text_area", "rich_text_editor": "text_area",
        "label": "text_label", "link": "link",
        "icon": "icon", "image": "panel",
        "list": "list", "list_item": "list",
        "dialog": "dialog", "tooltip": "dialog",
        "progress_bar": "progress", "status_bar": "title_bar",
        "toolbar": "menu_bar", "toolbar_button": "button",
        "splitter": "panel", "pane": "panel",
        "tree": "list", "tree_item": "list",
        "grid": "panel", "grid_cell": "text_field",
        "calendar": "panel", "date_picker": "dropdown",
        "spinner": "text_field", "stepper": "text_field",
        "pagination": "button", "breadcrumb": "link",
        "card": "panel", "carousel": "panel",
        "banner": "panel", "notification": "dialog",
        "avatar": "icon", "badge": "text_label",
        "chip": "button", "tag": "text_label",
        "divider": "panel", "accordion": "panel",
    }

    def __init__(self):
        try:
            from ultralytics import YOLO  # noqa: F401
            self._yolo_available = True
        except ImportError:
            self._yolo_available = False
            return

        self._model = None
        self.available = True

    def _load_model(self):
        if self._model is not None:
            return self._model

        from ultralytics import YOLO

        # Priority: shared model cache > project-local > env var > HF download
        checkpoint_paths = [
            "/models/screenparser/best.pt",
            os.environ.get("SCREENPARSER_MODEL_PATH", ""),
            os.path.join(os.path.dirname(__file__), "..", "..",
                         "models", "screenparser", "best.pt"),
        ]

        for p in checkpoint_paths:
            if not p or not os.path.isfile(p):
                continue
            try:
                self._model = YOLO(p)
                self._move_model_to_gpu()
                print(f"[screenparser] Loaded from {p} (device: {self._model.device})", file=sys.stderr)
                if "cuda" in str(self._model.device):
                    self.uses_gpu = True
                # Log class summary
                if hasattr(self._model, 'names'):
                    classes = list(self._model.names.values())[:10]
                    print(f"[screenparser] {len(self._model.names)} classes: {classes}...", file=sys.stderr)
                return self._model
            except Exception as e:
                print(f"[screenparser] Failed to load {p}: {e}", file=sys.stderr)

        # Fallback: download from HuggingFace
        try:
            from huggingface_hub import hf_hub_download
            model_file = hf_hub_download(
                repo_id="docling-project/ScreenParser",
                filename="best.pt",
                local_dir="/models/screenparser",
            )
            self._model = YOLO(model_file)
            self._move_model_to_gpu()
            print(f"[screenparser] Downloaded from HF: {model_file}", file=sys.stderr)
            if "cuda" in str(self._model.device):
                self.uses_gpu = True
            return self._model
        except Exception as e:
            print(f"[screenparser] HF download failed: {e}", file=sys.stderr)

        self.available = False
        return None

    def detect(self, image: np.ndarray) -> List[Dict]:
        model = self._load_model()
        if model is None:
            return []

        try:
            detections = model(image, verbose=False, conf=0.25, iou=0.45)
        except Exception as e:
            print(f"[screenparser] Detection error: {e}", file=sys.stderr)
            return []

        elements = []
        element_id = 0

        for det in detections:
            boxes = det.boxes
            if boxes is None or len(boxes) == 0:
                continue

            for i in range(len(boxes)):
                cls_id = int(boxes.cls[i])
                cls_name = det.names.get(cls_id, f"class_{cls_id}")
                x1, y1, x2, y2 = boxes.xyxy[i].tolist()
                conf = float(boxes.conf[i])

                bbox = [int(x1), int(y1), int(x2 - x1), int(y2 - y1)]
                elem_type = self.CLASS_MAP.get(cls_name.lower(), "unknown")

                # Determine if interactive
                interactive = elem_type in (
                    "button", "text_field", "dropdown", "checkbox",
                    "radio", "menu_bar", "slider", "scrollbar",
                    "tab", "link", "list", "spinner", "stepper",
                )

                elements.append({
                    "id": element_id,
                    "bbox": bbox,
                    "type": elem_type,
                    "label": f"{cls_name}",
                    "confidence": round(conf, 3),
                    "interactive": interactive,
                })
                element_id += 1

        return elements


# ── ScreenParser Wine-FineTuned Detector ───────────────────────────────────────

class ScreenParserWineDetector(ScreenParserDetector):
    """ScreenParser fine-tuned on WineBot's 18-scene GT dataset.

    Same 55-class YOLOv11-L architecture as ScreenParser, but trained on
    3,587 programmatically generated Wine desktop images across 8 UI
    framework themes. Achieves mAP50=0.951, mAP50-95=0.794 — the highest
    accuracy among all detector backends.

    Uses ScreenParser's CLASS_MAP and detect() logic — only the checkpoint
    differs. 49 MB, ~304ms/frame on RTX 3090.
    """

    name = "screenparser_wine"
    available = False
    uses_gpu = False

    def __init__(self):
        try:
            from ultralytics import YOLO  # noqa: F401
            self._yolo_available = True
        except ImportError:
            self._yolo_available = False
            return

        self._model = None
        self.available = True

    def _load_model(self):
        if self._model is not None:
            return self._model

        from ultralytics import YOLO

        # Priority: Wine-fine-tuned SP > generic ScreenParser > HF download
        paths = [
            "/models/yolo/screenparser-wine.pt",
            "/models/screenparser/best.pt",
            os.path.join(os.path.dirname(__file__), "..", "..",
                         "models", "yolo", "screenparser-wine.pt"),
            os.path.join(os.path.dirname(__file__), "..", "..",
                         "models", "screenparser", "best.pt"),
            os.environ.get("SCREENPARSER_MODEL_PATH", ""),
        ]

        for p in paths:
            if not p or not os.path.isfile(p):
                continue
            try:
                self._model = YOLO(p)
                self._move_model_to_gpu()
                print(f"[screenparser_wine] Loaded from {p} "
                      f"(device: {self._model.device})", file=sys.stderr)
                if "cuda" in str(self._model.device):
                    self.uses_gpu = True
                if hasattr(self._model, 'names'):
                    print(f"[screenparser_wine] {len(self._model.names)} classes",
                          file=sys.stderr)
                return self._model
            except Exception as e:
                print(f"[screenparser_wine] Failed to load {p}: {e}", file=sys.stderr)

        # Fallback: try HF download of generic ScreenParser
        try:
            from huggingface_hub import hf_hub_download
            model_file = hf_hub_download(
                repo_id="docling-project/ScreenParser",
                filename="best.pt",
                local_dir="/models/screenparser",
            )
            self._model = YOLO(model_file)
            self._move_model_to_gpu()
            print(f"[screenparser_wine] Downloaded generic SP from HF: {model_file}",
                  file=sys.stderr)
            if "cuda" in str(self._model.device):
                self.uses_gpu = True
            return self._model
        except Exception as e:
            print(f"[screenparser_wine] HF download failed: {e}", file=sys.stderr)

        self.available = False
        return None


# ── Wine-FineTuned Detector ───────────────────────────────────────────────────

class WineUIDetector(YOLOUIDetector):
    """Wine-specific fine-tuned YOLO detector — 22 classes, 8 framework themes.

    Trained on 1805 synthetic Wine desktop images with 8 UI framework themes
    (win32, win10, Qt, Gtk, Java, Tk, Electron, Win95). Achieves mAP50=0.993,
    mAP50-95=0.912 on Wine desktop elements.

    Overrides YOLOUIDetector's model loading to use the fine-tuned weights
    from the shared model cache.
    """

    name = "wine"
    available = False
    uses_gpu = False

    def __init__(self):
        try:
            from ultralytics import YOLO  # noqa: F401
            self.available = True
        except ImportError:
            self.available = False
        self._model = None

    def _load_model(self):
        if self._model is not None:
            return self._model

        from ultralytics import YOLO

        # Priority: v3 (18-scene generalized) > v2 (corrected) > v1 (original)
        paths = [
            "/models/yolo/wine-finetuned-v3.pt",
            "/models/yolo/wine-finetuned-v2.pt",
            "/models/yolo/wine-finetuned.pt",
            os.path.join(os.path.dirname(__file__), "..", "..",
                         "models", "yolo", "wine-finetuned-v3.pt"),
            os.path.join(os.path.dirname(__file__), "..", "..",
                         "models", "yolo", "wine-finetuned-v2.pt"),
            os.path.join(os.path.dirname(__file__), "..", "..",
                         "models", "yolo", "wine-finetuned.pt"),
        ]
        for p in paths:
            if os.path.isfile(p):
                try:
                    self._model = YOLO(p)
                    self._move_model_to_gpu()
                    print(f"[wine] Loaded fine-tuned model from {p} "
                          f"(device: {self._model.device})", file=sys.stderr)
                    if "cuda" in str(self._model.device):
                        self.uses_gpu = True
                    return self._model
                except Exception as e:
                    print(f"[wine] Failed to load {p}: {e}", file=sys.stderr)

        print("[wine] No fine-tuned model found. Train with: "
              "fine_tune_detector.py --data .../data.yaml", file=sys.stderr)
        self.available = False
        return None

    def detect(self, image: np.ndarray) -> List[Dict]:
        """Detect Wine-specific UI elements using fine-tuned YOLO."""
        model = self._load_model()
        if model is None:
            return []

        # Wine desktop elements are well-defined — higher confidence threshold
        # than OmniParser (which uses 0.15 for vague icons)
        try:
            dets = model(image, verbose=False, conf=0.35, iou=0.45)
        except Exception as e:
            print(f"[wine] Detection error: {e}", file=sys.stderr)
            return []

        elements = []
        element_id = 0
        for det in dets:
            boxes = det.boxes
            if boxes is None or len(boxes) == 0:
                continue
            for i in range(len(boxes)):
                cls_id = int(boxes.cls[i])
                cls_name = det.names.get(cls_id, f"class_{cls_id}")
                x1, y1, x2, y2 = boxes.xyxy[i].tolist()
                conf = float(boxes.conf[i])
                bbox = [int(x1), int(y1), int(x2 - x1), int(y2 - y1)]

                elem_type = cls_name  # Fine-tuned classes ARE the UI type
                interactive = elem_type in (
                    "button", "text_field", "dropdown", "checkbox",
                    "radio", "menu_bar", "menu_item", "close_button",
                    "scrollbar", "tab", "link", "list_item",
                    "spinner_button", "toolbar",
                )
                elements.append({
                    "id": element_id, "bbox": bbox,
                    "type": elem_type, "label": cls_name,
                    "confidence": round(conf, 3),
                    "interactive": interactive,
                })
                element_id += 1
        return elements


# ── VLM Grounding Detector ────────────────────────────────────────────────────

class VLMGroundingDetector(UIDetector):
    """Vision-Language Model for natural-language GUI element grounding.

    Uses KV-Ground-8B (vocaela/KV-Ground-8B-BaseGuiOwl1.5-0315) — a
    specialized GUI grounding VLM based on Qwen3-VL-8B. Achieves 73.2
    on ScreenSpot-Pro, 94.6 on ScreenSpot-V2.

    Unlike class-based detectors, the VLM takes a natural language query
    (e.g. "find the Save button") and returns the specific element's
    bounding box. This is complementary — the class-based detector finds
    all elements of known types, while the VLM finds specific elements
    described in natural language.

    Supports:
      - BF16 via transformers (~16 GB VRAM, full quality)
      - INT4 via llama-cpp-python (~6 GB VRAM, GGUF quantized)
      - Automatic fallback between providers
    """

    name = "vlm_ground"
    available = False
    uses_gpu = True

    # Model identifiers
    HF_REPO = "vocaela/KV-Ground-8B-BaseGuiOwl1.5-0315"
    GGUF_REPO = "mradermacher/KV-Ground-8B-BaseGuiOwl1.5-0315-GGUF"
    GGUF_FILE = "KV-Ground-8B-BaseGuiOwl1.5-0315-Q4_K_M.gguf"

    def __init__(self):
        self._model = None
        self._processor = None
        self._backend = None  # "transformers" or "llama_cpp"

        # Check availability lazily — don't load the model until needed
        try:
            import torch  # noqa: F401
            self._torch_available = True
        except ImportError:
            self._torch_available = False

        # Try transformers path
        try:
            import transformers  # noqa: F401
            self._has_transformers = True
        except ImportError:
            self._has_transformers = False

        # Try llama-cpp path (lighter weight)
        try:
            import llama_cpp  # noqa: F401
            self._has_llama_cpp = True
        except ImportError:
            self._has_llama_cpp = False

        self.available = self._torch_available and (
            self._has_transformers or self._has_llama_cpp
        )

    def _load_model(self):
        """Lazy-load the VLM model on first use."""
        if self._model is not None:
            return

        import torch

        # Try GGUF (llama-cpp-python) first — lighter, faster startup
        if self._has_llama_cpp:
            gguf_path = os.environ.get(
                "VLM_MODEL_PATH",
                f"/models/vlm/{self.GGUF_FILE}"
            )
            if os.path.isfile(gguf_path):
                try:
                    import llama_cpp
                    from llama_cpp import Llama

                    print(f"[vlm_ground] Loading GGUF from {gguf_path}...",
                          file=sys.stderr)
                    self._model = Llama(
                        model_path=gguf_path,
                        n_ctx=4096,
                        n_gpu_layers=-1,  # All layers on GPU
                        verbose=False,
                    )
                    self._backend = "llama_cpp"
                    print(f"[vlm_ground] GGUF model loaded (GPU layers: all)",
                          file=sys.stderr)
                    return
                except Exception as e:
                    print(f"[vlm_ground] GGUF load failed: {e}", file=sys.stderr)

        # Try transformers path
        if self._has_transformers:
            try:
                from transformers import AutoProcessor, AutoModelForVision2Seq
                from qwen_vl_utils import process_vision_info

                model_dir = os.environ.get(
                    "VLM_MODEL_DIR",
                    f"/models/vlm/{self.HF_REPO.split('/')[-1]}"
                )

                print(f"[vlm_ground] Loading transformers VLM from {model_dir}...",
                      file=sys.stderr)

                # Download from HF if not cached
                if not os.path.isdir(model_dir) or not os.path.isfile(
                    os.path.join(model_dir, "config.json")
                ):
                    model_id = os.environ.get("VLM_HF_REPO", self.HF_REPO)
                    self._model = AutoModelForVision2Seq.from_pretrained(
                        model_id,
                        torch_dtype=torch.bfloat16,
                        device_map="auto",
                        trust_remote_code=True,
                    )
                    self._processor = AutoProcessor.from_pretrained(
                        model_id,
                        trust_remote_code=True,
                    )
                else:
                    self._model = AutoModelForVision2Seq.from_pretrained(
                        model_dir,
                        torch_dtype=torch.bfloat16,
                        device_map="auto",
                        trust_remote_code=True,
                    )
                    self._processor = AutoProcessor.from_pretrained(
                        model_dir,
                        trust_remote_code=True,
                    )

                self._backend = "transformers"
                print(f"[vlm_ground] Transformers model loaded on {self._model.device}",
                      file=sys.stderr)
                return

            except ImportError:
                print("[vlm_ground] qwen_vl_utils not available", file=sys.stderr)
            except Exception as e:
                print(f"[vlm_ground] Transformers load failed: {e}", file=sys.stderr)

        self.available = False
        print("[vlm_ground] No VLM backend available. Download model to "
              f"/models/vlm/ or install llama-cpp-python/transformers",
              file=sys.stderr)

    def ground(self, image: np.ndarray, query: str) -> Optional[Dict]:
        """Ground a natural language query to a specific UI element.

        Args:
            image: BGR screenshot as numpy array.
            query: Natural language description, e.g. "the Save button"
                   or "the File menu item".

        Returns:
            Dict with bbox, label, confidence, or None if not found.
            {"bbox": [x, y, w, h], "label": "Save button",
             "confidence": 0.95, "query": "the Save button"}
        """
        self._load_model()
        if self._model is None:
            return None

        if self._backend == "llama_cpp":
            return self._ground_llama_cpp(image, query)
        elif self._backend == "transformers":
            return self._ground_transformers(image, query)
        return None

    def _ground_llama_cpp(self, image: np.ndarray, query: str) -> Optional[Dict]:
        """Use llama-cpp-python with GGUF-quantized model."""
        import base64

        # Encode image as base64 JPEG
        _, buf = cv2.imencode(".jpg", image, [cv2.IMWRITE_JPEG_QUALITY, 85])
        img_b64 = base64.b64encode(buf).decode("utf-8")

        # Build prompt with image + instruction
        data_url = f"data:image/jpeg;base64,{img_b64}"
        prompt = (
            f"<|vision_start|>{data_url}<|vision_end|>"
            f"Point to {query}. Return the bounding box coordinates "
            f"in format [x1, y1, x2, y2] normalized to 0-1000."
        )

        try:
            response = self._model.create_chat_completion(
                messages=[{"role": "user", "content": prompt}],
                max_tokens=128,
                temperature=0.0,
            )
            text = response["choices"][0]["message"]["content"]
        except Exception as e:
            print(f"[vlm_ground] llama.cpp inference error: {e}", file=sys.stderr)
            return None

        return self._parse_grounding_response(text, query)

    def _ground_transformers(self, image: np.ndarray, query: str) -> Optional[Dict]:
        """Use transformers with full BF16 model."""
        import torch
        from qwen_vl_utils import process_vision_info

        # Convert BGR to RGB
        rgb = cv2.cvtColor(image, cv2.COLOR_BGR2RGB)
        from PIL import Image
        pil_img = Image.fromarray(rgb)

        messages = [
            {"role": "user", "content": [
                {"type": "image", "image": pil_img},
                {"type": "text", "text": f"Point to {query}."},
            ]}
        ]

        try:
            text = self._processor.apply_chat_template(
                messages, tokenize=False, add_generation_prompt=True
            )
            image_inputs, video_inputs = process_vision_info(messages)
            inputs = self._processor(
                text=[text],
                images=image_inputs,
                videos=video_inputs,
                padding=True,
                return_tensors="pt",
            ).to(self._model.device)

            with torch.no_grad():
                generated_ids = self._model.generate(
                    **inputs, max_new_tokens=128, temperature=0.0
                )
            generated_ids = [
                output_ids[len(input_ids):]
                for input_ids, output_ids in zip(inputs.input_ids, generated_ids)
            ]
            response = self._processor.batch_decode(
                generated_ids, skip_special_tokens=True
            )[0]
        except Exception as e:
            print(f"[vlm_ground] Transformers inference error: {e}", file=sys.stderr)
            return None

        return self._parse_grounding_response(response, query)

    def _parse_grounding_response(self, text: str, query: str) -> Optional[Dict]:
        """Parse model output for bounding box coordinates.

        Handles common output formats:
          - [x1, y1, x2, y2]  (normalized 0-1000 or pixel coords)
          - <box>x1 y1 x2 y2</box>
          - JSON-like: {"bbox": [x1, y1, x2, y2]}
        """
        import re
        import json

        # Try to extract coordinates
        # Pattern 1: [number, number, number, number]
        m = re.search(r'\[(\d+)[,\s]+(\d+)[,\s]+(\d+)[,\s]+(\d+)\]', text)
        if m:
            coords = [int(m.group(i)) for i in range(1, 5)]
            # If coordinates are > 1000, they're likely pixel coordinates
            if max(coords) > 1000:
                # Already pixel coords, convert from x1y1x2y2 to xywh
                return {
                    "bbox": [coords[0], coords[1],
                             coords[2] - coords[0], coords[3] - coords[1]],
                    "label": query,
                    "confidence": 0.85,
                    "raw_response": text,
                }
            else:
                # Normalized 0-1000 → need image size for conversion
                return {
                    "bbox": coords,  # Caller should denormalize
                    "label": query,
                    "confidence": 0.85,
                    "normalized": "0-1000",
                    "raw_response": text,
                }

        # Pattern 2: <box>x1 y1 x2 y2</box>
        m = re.search(r'<box>\s*(\d+)\s+(\d+)\s+(\d+)\s+(\d+)\s*</box>', text)
        if m:
            coords = [int(m.group(i)) for i in range(1, 5)]
            return {
                "bbox": [coords[0], coords[1],
                         coords[2] - coords[0], coords[3] - coords[1]],
                "label": query,
                "confidence": 0.85,
                "raw_response": text,
            }

        # No coordinate format matched
        print(f"[vlm_ground] Could not parse coordinates from: {text[:200]}",
              file=sys.stderr)
        return {"label": query, "confidence": 0.3, "raw_response": text}

    def detect(self, image: np.ndarray) -> List[Dict]:
        """VLM grounding is query-driven — detect() returns empty.

        Use ground(image, query) for natural-language element finding.
        """
        return []


# ── Factory ───────────────────────────────────────────────────────────────────

_ui_detector: Optional[UIDetector] = None


def get_ui_detector(backend: Optional[str] = None) -> UIDetector:
    """Get or create the configured UI element detector.

    Args:
        backend: "contour", "yolo", "omniparser", or None (reads UI_DETECTOR env var)
    """
    global _ui_detector

    if backend is None:
        backend = os.environ.get("UI_DETECTOR", "contour").lower()

    if _ui_detector is not None and _ui_detector.name == backend:
        return _ui_detector

    if backend == "omniparser":
        _ui_detector = OmniParserDetector()
        if not _ui_detector.available:
            print(f"[ui] OmniParser requested but YOLO not available, "
                  f"falling back to contour", file=sys.stderr)
            _ui_detector = ContourDetector()
    elif backend == "yolo":
        _ui_detector = YOLOUIDetector()
        if not _ui_detector.available:
            print(f"[ui] YOLO requested but ultralytics not available, "
                  f"falling back to contour", file=sys.stderr)
            _ui_detector = ContourDetector()
    elif backend == "uidetr1":
        _ui_detector = UIDETR1Detector()
        if not _ui_detector.available:
            print(f"[ui] UI-DETR-1 requested but rfdetr not available, "
                  f"falling back to contour", file=sys.stderr)
            _ui_detector = ContourDetector()
    elif backend == "screenparser":
        _ui_detector = ScreenParserDetector()
        if not _ui_detector.available:
            print(f"[ui] ScreenParser requested but not available, "
                  f"falling back to contour", file=sys.stderr)
            _ui_detector = ContourDetector()
    elif backend == "screenparser_wine":
        _ui_detector = ScreenParserWineDetector()
        if not _ui_detector.available:
            print(f"[ui] ScreenParser Wine requested but not available, "
                  f"falling back to contour", file=sys.stderr)
            _ui_detector = ContourDetector()
    elif backend == "wine":
        _ui_detector = WineUIDetector()
        if not _ui_detector.available:
            print(f"[ui] Wine fine-tuned requested but not available, "
                  f"falling back to contour", file=sys.stderr)
            _ui_detector = ContourDetector()
    elif backend == "vlm_ground":
        _ui_detector = VLMGroundingDetector()
        if not _ui_detector.available:
            print(f"[ui] VLM grounding requested but no backend available, "
                  f"falling back to contour", file=sys.stderr)
            _ui_detector = ContourDetector()
    else:
        _ui_detector = ContourDetector()

    return _ui_detector


def available_detectors() -> Dict[str, bool]:
    """Return dict of detector name -> available."""
    return {
        "contour": ContourDetector().available,
        "yolo": YOLOUIDetector().available,
        "omniparser": OmniParserDetector().available,
        "uidetr1": UIDETR1Detector().available,
        "screenparser": ScreenParserDetector().available,
        "screenparser_wine": ScreenParserWineDetector().available,
        "wine": WineUIDetector().available,
        "vlm_ground": VLMGroundingDetector().available,
    }


def current_detector() -> str:
    """Return the currently active UI detector name."""
    detector = get_ui_detector()
    return detector.name
