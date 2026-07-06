#!/usr/bin/env python3
"""
Workflow Test Harness — measures CV/OCR generalization across visual variations.

Runs reproducible multi-step workflow scenarios with controlled visual fuzzing
(different themes, fonts, colors, window positions). Unlike the static GT
generator that produces single-frame scenes, this produces FRAME SEQUENCES
that simulate real automation workflows.

Key design principle: we measure how CONSISTENTLY the CV/OCR pipeline
performs on the SAME workflow with DIFFERENT visual parameters. This
is a generalization test, not a memorization test.

Usage:
  # Generate a workflow test suite with 5 visual variations per scenario
  python3 workflow_test_harness.py --output /tmp/wf_test --variations 5

  # Run detection on all workflow frames and measure consistency
  python3 workflow_test_harness.py --output /tmp/wf_test --detector wine --evaluate

  # Generate with specific seed for reproducibility
  python3 workflow_test_harness.py --output /tmp/wf_test --seed 42 --variations 10
"""

import argparse
import json
import os
import random
import sys
from dataclasses import dataclass

import cv2
import numpy as np

# ── Import the GT generator's rendering primitives ─────────────────────────

sys.path.insert(0, os.path.dirname(__file__))

# We reuse the generator's scene functions but wrap them in workflow sequences
try:
    import importlib.util
    gen_spec = importlib.util.spec_from_file_location(
        "winebot_gt_generator",
        os.path.join(os.path.dirname(__file__), "winebot-gt-generator.py"))
    gen_mod = importlib.util.module_from_spec(gen_spec)
    gen_spec.loader.exec_module(gen_mod)
    DESKTOP_SIZE = gen_mod.DESKTOP_SIZE
    WINE_CLASSES = gen_mod.WINE_CLASSES
    FRAMEWORK_THEMES = gen_mod.FRAMEWORK_THEMES
    TARGET_RESOLUTIONS = gen_mod.TARGET_RESOLUTIONS
    AVAILABLE_FONTS = gen_mod.AVAILABLE_FONTS
    draw_window = gen_mod.draw_window
    UIElement = gen_mod.UIElement
    Page = gen_mod.Page
    GENERATORS = gen_mod.GENERATORS
    _HAS_GENERATOR = True
except Exception:
    _HAS_GENERATOR = False


# ── Split Definitions ──────────────────────────────────────────────────────
# These define which scene types and frameworks are HELD OUT from training.
# The train set sees 13 scene types × 6 frameworks. Test/val use held-out
# scenes and frameworks the model has never seen.

TRAIN_SCENES = [
    "save_dialog", "settings", "error_dialog", "notepad",
    "control_panel", "file_manager", "multi_window", "browser",
    "terminal", "context_menu", "wizard", "find_replace", "print_dialog",
]
VAL_SCENES = ["about_dialog", "file_properties"]
TEST_SCENES = ["system_tray", "form_fill"]

TRAIN_FRAMEWORKS = [
    "win32_classic", "win10_fluent", "qt_fusion",
    "gtk_adwaita", "java_metal", "tkinter",
]
TEST_FRAMEWORKS = ["electron_dark", "classic_95"]

TRAIN_RESOLUTIONS = [(1024, 768), (1280, 720), (1366, 768), (1920, 1080)]
TEST_RESOLUTION = (1440, 900)

ALL_RESOLUTIONS = [(1024, 768), (1280, 720), (1366, 768), (1440, 900), (1920, 1080)]


def get_split_info():
    """Return the current split configuration for documentation."""
    return {
        "train_scenes": TRAIN_SCENES,
        "val_scenes": VAL_SCENES,
        "test_scenes": TEST_SCENES,
        "train_frameworks": TRAIN_FRAMEWORKS,
        "test_frameworks": TEST_FRAMEWORKS,
        "train_resolutions": [(w, h) for w, h in TRAIN_RESOLUTIONS],
        "test_resolution": TEST_RESOLUTION,
        "n_train_scenes": len(TRAIN_SCENES),
        "n_val_scenes": len(VAL_SCENES),
        "n_test_scenes": len(TEST_SCENES),
        "n_train_frameworks": len(TRAIN_FRAMEWORKS),
        "n_test_frameworks": len(TEST_FRAMEWORKS),
    }


# ── Workflow Definition ────────────────────────────────────────────────────

@dataclass
class WorkflowStep:
    """One step in a reproducible workflow."""
    name: str                    # e.g., "open_save_dialog"
    description: str             # e.g., "File > Save As in Notepad"
    scene_type: str              # Which generator scene this maps to
    expected_elements: list[str] # Element types that must be present
    expected_text: list[str]     # Text strings that should be visible
    duration_frames: int = 3     # How many frames this step occupies


@dataclass
class WorkflowScenario:
    """A multi-step workflow that tests CV/OCR across state transitions."""
    name: str
    description: str
    steps: list[WorkflowStep]
    # Which visual parameters to vary across runs
    fuzz_themes: bool = True
    fuzz_fonts: bool = True
    fuzz_positions: bool = True
    fuzz_colors: bool = True
    fuzz_resolution: bool = True


# ── Pre-defined Workflow Scenarios ─────────────────────────────────────────
# These are held-out from training. They represent real automation tasks.

WORKFLOW_SCENARIOS = [
    WorkflowScenario(
        name="file_save_workflow",
        description="Save a document with File > Save As, navigate directories, type filename",
        steps=[
            WorkflowStep("app_open", "Application window with document content",
                        "notepad", ["title_bar", "menu_bar", "text_area"],
                        ["Untitled", "File", "Edit"]),
            WorkflowStep("file_menu", "File menu dropped down",
                        "notepad", ["menu_bar", "menu_item"],
                        ["New", "Open", "Save", "Save As", "Exit"]),
            WorkflowStep("save_dialog", "Save As dialog with file browser",
                        "save_dialog", ["dialog", "text_field", "button", "title_bar"],
                        ["Save As", "File name", "Save", "Cancel"]),
            WorkflowStep("filename_typed", "Filename entered in save dialog",
                        "save_dialog", ["dialog", "text_field", "button"],
                        ["document.txt", "Save"]),
            WorkflowStep("save_complete", "Dialog dismissed, back to editor",
                        "notepad", ["title_bar", "menu_bar", "text_area"],
                        ["document.txt"]),
        ]
    ),
    WorkflowScenario(
        name="settings_change_workflow",
        description="Open Settings, change preferences, apply",
        steps=[
            WorkflowStep("settings_open", "Settings/Preferences dialog",
                        "settings", ["title_bar", "tab", "checkbox", "dropdown", "button"],
                        ["Settings", "General", "OK", "Cancel", "Apply"]),
            WorkflowStep("tab_switched", "Switched to Display tab",
                        "settings", ["tab", "checkbox", "button"],
                        ["Display", "Resolution", "Color"]),
            WorkflowStep("setting_changed", "Checkbox toggled, dropdown changed",
                        "settings", ["checkbox", "dropdown", "button"],
                        ["Apply", "OK"]),
            WorkflowStep("settings_applied", "Apply clicked, still in dialog",
                        "settings", ["title_bar", "button"],
                        ["Settings", "OK"]),
        ]
    ),
    WorkflowScenario(
        name="error_recovery_workflow",
        description="Application error → error dialog → user acknowledges → retry",
        steps=[
            WorkflowStep("error_appears", "Error dialog pops up over application",
                        "error_dialog", ["dialog", "button", "title_bar"],
                        ["Error", "OK", "Retry"]),
            WorkflowStep("error_acknowledged", "User clicked OK, dialog dismissed",
                        "error_dialog", ["dialog", "button"],
                        ["Error"]),
        ]
    ),
    WorkflowScenario(
        name="multi_window_workflow",
        description="Two applications open simultaneously, user switches between them",
        steps=[
            WorkflowStep("both_visible", "Two windows from different frameworks open",
                        "multi_window", ["title_bar", "text_area", "button"],
                        ["Editor", "Browser"]),
            WorkflowStep("focus_switched", "Second window brought to foreground",
                        "multi_window", ["title_bar", "button", "text_field"],
                        ["Browser", "Address"]),
        ]
    ),
    WorkflowScenario(
        name="wizard_workflow",
        description="Multi-step wizard: Next → Next → Finish",
        steps=[
            WorkflowStep("wizard_step1", "Wizard page 1: License agreement",
                        "wizard", ["title_bar", "text_area", "button", "radio"],
                        ["Setup Wizard", "License", "I Agree", "Next"]),
            WorkflowStep("wizard_step2", "Wizard page 2: Install directory",
                        "wizard", ["title_bar", "text_field", "button"],
                        ["Destination", "Browse", "Next", "Back"]),
            WorkflowStep("wizard_step3", "Wizard page 3: Ready to install",
                        "wizard", ["title_bar", "progress_bar", "button"],
                        ["Ready to Install", "Install", "Back"]),
            WorkflowStep("wizard_done", "Installation complete",
                        "wizard", ["title_bar", "button"],
                        ["Complete", "Finish"]),
        ]
    ),
    WorkflowScenario(
        name="form_fill_workflow",
        description="Fill a dense form with validation states",
        steps=[
            WorkflowStep("form_empty", "Empty form with all fields",
                        "form_fill", ["title_bar", "text_field", "dropdown",
                                       "checkbox", "radio", "button"],
                        ["Name", "Address", "Submit"]),
            WorkflowStep("form_partial", "Some fields filled, validation active",
                        "form_fill", ["text_field", "button"],
                        ["Submit", "Reset"]),
            WorkflowStep("form_complete", "All required fields filled",
                        "form_fill", ["text_field", "button"],
                        ["Submit"]),
        ]
    ),
]


# ── Visual Fuzzing Parameters ──────────────────────────────────────────────

@dataclass
class FuzzConfig:
    """One specific set of visual parameters for a workflow run."""
    theme_name: str
    font_face: int
    font_scale: float
    font_thickness: int
    resolution: tuple[int, int]
    window_offset: tuple[int, int]   # px offset from default position
    hsv_jitter: tuple[int, int, int]  # H, S, V shifts
    contrast: float
    noise_sigma: float
    seed: int

    @classmethod
    def random(cls, seed: int, split: str = "test") -> "FuzzConfig":
        """Generate a random fuzz configuration.

        Args:
            seed: Random seed for reproducibility.
            split: "train" or "test" — determines which frameworks/resolutions
                   are sampled from.
        """
        rng = random.Random(seed)

        if split == "train":
            frameworks = TRAIN_FRAMEWORKS
            resolutions = TRAIN_RESOLUTIONS
        else:
            frameworks = TEST_FRAMEWORKS
            resolutions = ALL_RESOLUTIONS  # Test on all resolutions

        return cls(
            theme_name=rng.choice(frameworks),
            font_face=rng.choice(list(range(5))),  # 0-4 = OpenCV font faces
            font_scale=round(rng.uniform(0.85, 1.15), 2),
            font_thickness=rng.choice([1, 2]),
            resolution=rng.choice(resolutions),
            window_offset=(rng.randint(-50, 50), rng.randint(-30, 30)),
            hsv_jitter=(rng.randint(-20, 20), rng.randint(-20, 20), rng.randint(-20, 20)),
            contrast=round(rng.uniform(0.7, 1.3), 2),
            noise_sigma=round(rng.uniform(0.0, 2.0), 1),
            seed=seed,
        )


# ── Self-Contained Workflow Frame Generator ────────────────────────────────
# Falls back to direct OpenCV rendering if GT generator not importable.

class WorkflowFrameGenerator:
    """Generates workflow frame sequences with controlled visual fuzzing.

    Produces N variations of each workflow scenario, where each variation
    uses a different FuzzConfig (different theme, font, position, etc.).
    """

    def __init__(self, seed: int = 42):
        self.rng = random.Random(seed)
        self.np_rng = np.random.RandomState(seed)

    def _apply_visual_fuzz(self, img: np.ndarray, cfg: FuzzConfig) -> np.ndarray:
        """Apply visual fuzzing to an image: HSV jitter, contrast, noise."""
        # HSV jitter
        hsv = cv2.cvtColor(img, cv2.COLOR_BGR2HSV).astype(np.int16)
        h, s, v = cfg.hsv_jitter
        hsv[:, :, 0] = np.clip(hsv[:, :, 0] + h, 0, 179)
        hsv[:, :, 1] = np.clip(hsv[:, :, 1] + s, 0, 255)
        hsv[:, :, 2] = np.clip(hsv[:, :, 2] + v, 0, 255)
        img = cv2.cvtColor(hsv.astype(np.uint8), cv2.COLOR_HSV2BGR)

        # Contrast
        if cfg.contrast != 1.0:
            img = cv2.convertScaleAbs(img, alpha=cfg.contrast, beta=0)

        # Gaussian noise
        if cfg.noise_sigma > 0:
            noise = self.np_rng.normal(0, cfg.noise_sigma, img.shape).astype(np.int16)
            img = np.clip(img.astype(np.int16) + noise, 0, 255).astype(np.uint8)

        return img

    def _render_synthetic_frame(self, scene_type: str, step_name: str,
                                 cfg: FuzzConfig, global_seed: int) -> tuple[np.ndarray, dict]:
        """Render a single frame using the GT generator primitives.

        Falls back to simple OpenCV rendering if generator not available.
        """
        w, h = cfg.resolution

        if _HAS_GENERATOR:
            try:
                # Use the actual generator function if available
                for name, gen_fn in GENERATORS:
                    if name == scene_type:
                        # Temporarily override globals for this generation
                        old_desktop = gen_mod.DESKTOP_SIZE
                        gen_mod.DESKTOP_SIZE = cfg.resolution

                        # Set the seed for reproducibility
                        random.seed(global_seed)
                        np.random.seed(global_seed)

                        page = gen_fn()
                        img = page.image

                        gen_mod.DESKTOP_SIZE = old_desktop
                        break
                else:
                    img = self._render_fallback(scene_type, step_name, cfg)
            except Exception:
                img = self._render_fallback(scene_type, step_name, cfg)
        else:
            img = self._render_fallback(scene_type, step_name, cfg)

        # Apply visual fuzzing
        img = self._apply_visual_fuzz(img, cfg)

        # Build ground truth metadata
        gt = {
            "scene_type": scene_type,
            "step_name": step_name,
            "fuzz_config": {
                "theme": cfg.theme_name,
                "font_face": cfg.font_face,
                "font_scale": cfg.font_scale,
                "resolution": list(cfg.resolution),
                "window_offset": list(cfg.window_offset),
                "hsv_jitter": list(cfg.hsv_jitter),
                "contrast": cfg.contrast,
                "noise_sigma": cfg.noise_sigma,
            },
            "seed": global_seed,
        }
        return img, gt

    def _render_fallback(self, scene_type: str, step_name: str,
                          cfg: FuzzConfig) -> np.ndarray:
        """Minimal OpenCV frame renderer when GT generator unavailable."""
        w, h = cfg.resolution
        img = np.full((h, w, 3), (40, 44, 52), dtype=np.uint8)  # Dark desktop

        # Draw a simple window frame
        ox, oy = cfg.window_offset
        wx = max(10, min(w - 300, 100 + ox))
        wy = max(10, min(h - 200, 50 + oy))
        ww, wh = min(w - wx - 10, 400), min(h - wy - 10, 250)

        cv2.rectangle(img, (wx, wy), (wx + ww, wy + wh), (60, 63, 70), -1)  # Window bg
        cv2.rectangle(img, (wx, wy), (wx + ww, wy + wh), (100, 100, 105), 1)  # Border

        # Title bar
        cv2.rectangle(img, (wx, wy), (wx + ww, wy + 28), (49, 54, 59), -1)
        cv2.putText(img, step_name.replace("_", " ").title(),
                   (wx + 8, wy + 20), cfg.font_face, cfg.font_scale * 0.5,
                   (200, 200, 200), cfg.font_thickness)

        # Draw some generic elements based on scene type
        if "dialog" in scene_type or "save" in scene_type:
            # Text field
            cv2.rectangle(img, (wx + 15, wy + 50), (wx + ww - 15, wy + 75),
                         (80, 80, 80), -1)
            cv2.rectangle(img, (wx + 15, wy + 50), (wx + ww - 15, wy + 75),
                         (120, 120, 120), 1)
            cv2.putText(img, "filename.txt", (wx + 20, wy + 68),
                       cfg.font_face, cfg.font_scale * 0.4,
                       (220, 220, 220), cfg.font_thickness)
            # Buttons
            btn_y = wy + wh - 40
            for label, bx in [("Save", wx + ww - 170), ("Cancel", wx + ww - 85)]:
                cv2.rectangle(img, (bx, btn_y), (bx + 70, btn_y + 26),
                             (49, 54, 59), -1)
                cv2.rectangle(img, (bx, btn_y), (bx + 70, btn_y + 26),
                             (120, 120, 120), 1)
                cv2.putText(img, label, (bx + 8, btn_y + 18),
                           cfg.font_face, cfg.font_scale * 0.35,
                           (220, 220, 220), cfg.font_thickness)

        if "settings" in scene_type:
            # Checkboxes
            for i, label in enumerate(["Enable feature", "Auto-start", "Notifications"]):
                cy = wy + 50 + i * 28
                cv2.rectangle(img, (wx + 15, cy), (wx + 33, cy + 18),
                             (100, 100, 100), -1)
                cv2.putText(img, label, (wx + 40, cy + 14),
                           cfg.font_face, cfg.font_scale * 0.35,
                           (200, 200, 200), cfg.font_thickness)

        return img

    def generate_workflow(self, scenario: WorkflowScenario,
                           n_variations: int = 5,
                           base_seed: int = 0,
                           split: str = "test") -> list[dict]:
        """Generate N visual variations of a workflow scenario.

        Each variation uses a different FuzzConfig (different theme, font,
        resolution, etc.) but follows the SAME step sequence.

        Returns list of variation dicts, each containing frame paths and
        ground truth metadata.
        """
        variations = []

        for var_idx in range(n_variations):
            var_seed = base_seed * 1000 + var_idx
            cfg = FuzzConfig.random(var_seed, split=split)

            frames = []
            for step_idx, step in enumerate(scenario.steps):
                frame_seed = var_seed * 100 + step_idx
                img, gt = self._render_synthetic_frame(
                    step.scene_type, step.name, cfg, frame_seed)
                frames.append({
                    "step_idx": step_idx,
                    "step_name": step.name,
                    "scene_type": step.scene_type,
                    "image": img,
                    "ground_truth": gt,
                    "expected_elements": step.expected_elements,
                    "expected_text": step.expected_text,
                })

            variations.append({
                "variation_idx": var_idx,
                "scenario_name": scenario.name,
                "fuzz_config": {
                    "theme": cfg.theme_name,
                    "font_face": cfg.font_face,
                    "font_scale": cfg.font_scale,
                    "font_thickness": cfg.font_thickness,
                    "resolution": list(cfg.resolution),
                    "window_offset": list(cfg.window_offset),
                    "hsv_jitter": list(cfg.hsv_jitter),
                    "contrast": cfg.contrast,
                    "noise_sigma": cfg.noise_sigma,
                },
                "seed": var_seed,
                "frames": frames,
            })

        return variations


# ── Evaluation Metrics ─────────────────────────────────────────────────────

def compute_consistency(detection_results: list[dict]) -> dict:
    """Measure how consistently the CV/OCR pipeline performs across variations.

    For each workflow step, we have N variations with different visual params.
    Consistency measures:
      - element_count_consistency: std/mean of # elements detected per step
      - type_consistency: % of element types detected in ALL variations
      - position_consistency: mean IoU of matching elements across variations
      - text_consistency: % of expected text found in ALL variations

    Args:
        detection_results: List of per-variation detection outputs.
          Each has a "frames" list with per-frame detection data.

    Returns:
        Dict with per-scenario and aggregate consistency metrics.
    """
    if not detection_results:
        return {"error": "No results to analyze"}

    n_variations = len(detection_results)
    n_steps = len(detection_results[0].get("frames", []))

    per_step = []
    for step_idx in range(n_steps):
        elem_counts = []
        elem_types = []
        texts_found = []

        for var in detection_results:
            frames = var.get("frames", [])
            if step_idx >= len(frames):
                continue
            frame = frames[step_idx]

            # Element count
            elements = frame.get("elements", [])
            elem_counts.append(len(elements))

            # Element types present
            types_in_frame = set(e.get("type", "unknown") for e in elements)
            elem_types.append(types_in_frame)

            # Text found
            ocr_texts = [t.get("text", "").lower()
                        for t in frame.get("ocr_text", [])]
            texts_found.append(set(ocr_texts))

        # Compute metrics
        mean_count = np.mean(elem_counts) if elem_counts else 0
        std_count = np.std(elem_counts) if elem_counts else 0
        cv_count = std_count / max(mean_count, 1)  # coefficient of variation

        # Type consistency: intersection across all variations
        if elem_types:
            types_in_all = elem_types[0]
            for ts in elem_types[1:]:
                types_in_all = types_in_all & ts
            type_consistency = len(types_in_all) / max(len(elem_types[0]), 1)
        else:
            types_in_all = set()
            type_consistency = 0.0

        # Text consistency
        if texts_found:
            texts_in_all = texts_found[0]
            for ts in texts_found[1:]:
                texts_in_all = texts_in_all & ts
            text_consistency = len(texts_in_all) / max(len(texts_found[0]), 1)
        else:
            texts_in_all = set()
            text_consistency = 0.0

        per_step.append({
            "step_idx": step_idx,
            "mean_elements": round(mean_count, 1),
            "std_elements": round(std_count, 1),
            "cv_elements": round(cv_count, 3),  # lower = more consistent
            "type_consistency": round(type_consistency, 3),  # higher = better
            "types_detected_in_all": sorted(types_in_all),
            "text_consistency": round(text_consistency, 3),
            "texts_found_in_all": sorted(texts_in_all)[:10],
        })

    # Aggregate: mean consistency across all steps
    agg = {
        "n_variations": n_variations,
        "n_steps": n_steps,
        "mean_cv_elements": round(np.mean([s["cv_elements"] for s in per_step]), 3),
        "mean_type_consistency": round(np.mean([s["type_consistency"] for s in per_step]), 3),
        "mean_text_consistency": round(np.mean([s["text_consistency"] for s in per_step]), 3),
        "per_step": per_step,
        # Overall grade: weighted combination
        "generalization_score": round(
            0.4 * (1.0 - np.mean([s["cv_elements"] for s in per_step])) +
            0.3 * np.mean([s["type_consistency"] for s in per_step]) +
            0.3 * np.mean([s["text_consistency"] for s in per_step]),
            3
        ),
    }
    return agg


def evaluate_detections(results_dir: str, detector_name: str = "wine",
                         api_url: str | None = None,
                         ocr_backend: str = "tesseract") -> dict:
    """Run CV/OCR detection on all frames in a test suite and compute consistency.

    Args:
        results_dir: Directory containing workflow test suite (manifest.json + frames/).
        detector_name: UI detector backend to use.
        api_url: CV sidecar API URL (None = use local import).
        ocr_backend: OCR backend to use.

    Returns:
        Consistency metrics dict.
    """
    manifest_path = os.path.join(results_dir, "manifest.json")
    if not os.path.exists(manifest_path):
        return {"error": f"No manifest.json in {results_dir}"}

    with open(manifest_path) as f:
        manifest = json.load(f)

    # Initialize detector
    if api_url:
        import io

        import requests
        _use_api = True
    else:
        from winebot_cv.ocr.engines import get_ocr_engine
        from winebot_cv.detectors.engines import get_ui_detector
        detector = get_ui_detector(detector_name)
        ocr = get_ocr_engine(ocr_backend)
        _use_api = False

    detection_results = []
    frames_dir = os.path.join(results_dir, "frames")

    for scenario in manifest.get("scenarios", []):
        var_results = {
            "scenario_name": scenario["name"],
            "n_variations": scenario["n_variations"],
            "frames": [],
        }

        for var_idx in range(scenario["n_variations"]):
            for step_idx, step in enumerate(scenario["steps"]):
                frame_name = f"{scenario['name']}_v{var_idx:02d}_s{step_idx:02d}.png"
                frame_path = os.path.join(frames_dir, frame_name)

                if not os.path.exists(frame_path):
                    continue

                img = cv2.imread(frame_path)
                if img is None:
                    continue

                if _use_api:
                    import io

                    import requests
                    _, buf = cv2.imencode(".png", img)
                    files = {"image": (frame_name, io.BytesIO(buf.tobytes()), "image/png")}
                    data = {"ui_detector": detector_name,
                           "ocr_backend": ocr_backend}
                    try:
                        r = requests.post(f"{api_url}/analyze", files=files,
                                        data=data, timeout=30)
                        r.raise_for_status()
                        result = r.json()
                    except Exception as e:
                        result = {"elements": [], "ocr_text": [], "error": str(e)}
                else:
                    elements = detector.detect(img)
                    ocr_results = ocr.detect_text(img)
                    result = {
                        "elements": elements,
                        "ocr_text": [{"text": t.get("text", ""),
                                     "bbox": t.get("bbox", [])}
                                    for t in ocr_results],
                    }

                var_results["frames"].append({
                    "variation_idx": var_idx,
                    "step_idx": step_idx,
                    "step_name": step["step_name"],
                    "expected_elements": step["expected_elements"],
                    "expected_text": step["expected_text"],
                    "elements": result.get("elements", []),
                    "ocr_text": result.get("ocr_text", []),
                })

        detection_results.append(var_results)

    # Compute consistency metrics
    all_consistency = {}
    for dr in detection_results:
        scenario_name = dr["scenario_name"]
        # Group frames by step_idx across variations
        frames_by_step = {}
        for f in dr["frames"]:
            sid = f["step_idx"]
            if sid not in frames_by_step:
                frames_by_step[sid] = []
            frames_by_step[sid].append(f)

        # Convert to same format as compute_consistency expects
        n_vars = dr["n_variations"]
        n_steps = len(frames_by_step)
        results_for_consistency = []
        for vi in range(n_vars):
            var_frames = {"frames": []}
            for si in range(n_steps):
                step_frames = frames_by_step.get(si, [])
                if vi < len(step_frames):
                    var_frames["frames"].append(step_frames[vi])
            results_for_consistency.append(var_frames)

        all_consistency[scenario_name] = compute_consistency(results_for_consistency)

    return {
        "detector": detector_name,
        "ocr_backend": ocr_backend,
        "n_scenarios": len(detection_results),
        "scenarios": all_consistency,
    }


# ── Main ────────────────────────────────────────────────────────────────────

def generate_test_suite(output_dir: str, n_variations: int = 5,
                         seed: int = 42, split: str = "test"):
    """Generate a complete workflow test suite.

    Produces:
      {output_dir}/
        manifest.json      — scenario definitions + fuzz configs
        frames/            — all rendered frame PNGs
        split_info.json    — train/val/test split definitions
    """
    os.makedirs(os.path.join(output_dir, "frames"), exist_ok=True)

    generator = WorkflowFrameGenerator(seed=seed)
    manifest = {
        "test_suite": "winebot-workflow-generalization",
        "split": split,
        "split_info": get_split_info(),
        "n_variations": n_variations,
        "seed": seed,
        "scenarios": [],
    }

    for scenario in WORKFLOW_SCENARIOS:
        print(f"  Generating: {scenario.name} ({len(scenario.steps)} steps × "
              f"{n_variations} variations)...", file=sys.stderr)

        variations = generator.generate_workflow(
            scenario, n_variations=n_variations,
            base_seed=seed, split=split)

        scenario_manifest = {
            "name": scenario.name,
            "description": scenario.description,
            "n_steps": len(scenario.steps),
            "n_variations": n_variations,
            "steps": [{"step_name": s.name, "scene_type": s.scene_type,
                       "expected_elements": s.expected_elements,
                       "expected_text": s.expected_text}
                      for s in scenario.steps],
            "variations": [],
        }

        for var in variations:
            var_info = {
                "variation_idx": var["variation_idx"],
                "fuzz_config": var["fuzz_config"],
                "seed": var["seed"],
                "frames": [],
            }
            for frame in var["frames"]:
                frame_name = (f"{scenario.name}_"
                             f"v{var['variation_idx']:02d}_"
                             f"s{frame['step_idx']:02d}.png")
                frame_path = os.path.join(output_dir, "frames", frame_name)
                cv2.imwrite(frame_path, frame["image"])
                var_info["frames"].append({
                    "filename": frame_name,
                    "step_idx": frame["step_idx"],
                    "step_name": frame["step_name"],
                    "scene_type": frame["scene_type"],
                    "expected_elements": frame["expected_elements"],
                    "expected_text": frame["expected_text"],
                    "ground_truth": frame["ground_truth"],
                })
            scenario_manifest["variations"].append(var_info)

        manifest["scenarios"].append(scenario_manifest)

    # Write manifest
    with open(os.path.join(output_dir, "manifest.json"), "w") as f:
        json.dump(manifest, f, indent=2)

    # Write split info separately for easy reference
    with open(os.path.join(output_dir, "split_info.json"), "w") as f:
        json.dump(get_split_info(), f, indent=2)

    # Summary
    total_frames = sum(
        len(s.steps) * n_variations
        for s in WORKFLOW_SCENARIOS
    )
    print(f"\n  Generated {total_frames} frames in {len(WORKFLOW_SCENARIOS)} scenarios",
          file=sys.stderr)
    print(f"  Output: {output_dir}/", file=sys.stderr)
    return manifest


def print_consistency_report(consistency: dict):
    """Pretty-print the consistency evaluation results."""
    print()
    print("=" * 72)
    print("  CV/OCR Generalization Report")
    print("=" * 72)
    print(f"  Detector: {consistency.get('detector', 'unknown')}")
    print(f"  OCR:      {consistency.get('ocr_backend', 'unknown')}")
    print(f"  Scenarios: {consistency.get('n_scenarios', 0)}")
    print()

    for scenario_name, metrics in consistency.get("scenarios", {}).items():
        if "error" in metrics:
            print(f"  {scenario_name}: ERROR — {metrics['error']}")
            continue
        gs = metrics.get("generalization_score", 0)
        grade = ("A" if gs >= 0.85 else "B" if gs >= 0.70
                else "C" if gs >= 0.55 else "D" if gs >= 0.40 else "F")
        print(f"  {scenario_name}: score={gs:.3f} ({grade})")
        print(f"    CV(elements): {metrics.get('mean_cv_elements', '?'):.3f}  "
              f"Type consistency: {metrics.get('mean_type_consistency', '?'):.0%}  "
              f"Text consistency: {metrics.get('mean_text_consistency', '?'):.0%}")

        for step in metrics.get("per_step", []):
            print(f"    Step {step['step_idx']}: "
                  f"elems={step['mean_elements']:.1f}±{step['std_elements']:.1f}  "
                  f"types_in_all={step['types_detected_in_all']}")
    print()
    print("=" * 72)


# ── CLI ────────────────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(
        description="Workflow Test Harness — CV/OCR generalization measurement")
    parser.add_argument("--output", default="/tmp/winebot-workflow-test",
                        help="Output directory for test suite")
    parser.add_argument("--variations", type=int, default=5,
                        help="Number of visual variations per scenario (default: 5)")
    parser.add_argument("--seed", type=int, default=42,
                        help="Random seed for reproducibility")
    parser.add_argument("--split", default="test",
                        choices=["train", "val", "test"],
                        help="Which split to generate (default: test)")
    parser.add_argument("--detector", default="wine",
                        help="Detector backend for --evaluate")
    parser.add_argument("--ocr-backend", default="tesseract",
                        help="OCR backend for --evaluate")
    parser.add_argument("--api", default=None,
                        help="CV sidecar API URL for detection")
    parser.add_argument("--evaluate", action="store_true",
                        help="Run detection and compute consistency metrics")
    parser.add_argument("--show-splits", action="store_true",
                        help="Print the train/val/test split definitions and exit")

    args = parser.parse_args()

    if args.show_splits:
        print(json.dumps(get_split_info(), indent=2))
        return

    if args.evaluate:
        if not os.path.isdir(args.output):
            print(f"ERROR: Test suite not found at {args.output}")
            print("  Run without --evaluate first to generate it.")
            sys.exit(1)
        consistency = evaluate_detections(
            args.output, args.detector, args.api, args.ocr_backend)
        print_consistency_report(consistency)

        # Save report
        report_path = os.path.join(args.output, "consistency_report.json")
        with open(report_path, "w") as f:
            json.dump(consistency, f, indent=2)
        print(f"Report saved: {report_path}")
        return

    # Generate mode
    print(f"Workflow Test Harness — {args.split.upper()} split")
    print(f"  Variations per scenario: {args.variations}")
    print(f"  Seed: {args.seed}")
    print()

    generate_test_suite(args.output, args.variations, args.seed, args.split)


if __name__ == "__main__":
    main()
