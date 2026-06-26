#!/usr/bin/env python3
# EXECUTION: EITHER — runs in sidecar container or on host with CV sidecar access
"""
Workflow Sequence Evaluator — tracks UI state transitions across video frames.

Reads a sequence of frames from demo recordings, runs CV detection on each,
and builds a state transition graph showing how the UI evolved over time.

Can optionally validate against an expected workflow sequence (e.g., from a
demo script) to programmatically confirm multi-step workflows completed.

Usage:
  # Evaluate a directory of frames
  python3 workflow_evaluator.py --frames demo/output/demo-winebox/frames/

  # Validate against an expected workflow definition
  python3 workflow_evaluator.py --frames demo/output/demo-customs-form/frames/ \\
      --expected workflows/customs-form.yaml

  # Via CV sidecar API (when running on host)
  python3 workflow_evaluator.py --api http://localhost:8001 \\
      --frames /tmp/demo_frames/

Output:
  JSON state graph with timing, element counts, and transition confidence.
"""

import argparse
import json
import os
import sys
import time
from pathlib import Path
from typing import Any, Dict, List, Optional, Set, Tuple

import cv2
import numpy as np

# Allow importing sibling diagnostic modules
sys.path.insert(0, os.path.dirname(__file__))

# Lazy imports — these are heavy and may not be available
_ui_imports = None


def _lazy_import_ui():
    global _ui_imports
    if _ui_imports is None:
        try:
            from ui_detectors import get_ui_detector
            from ocr_engines import get_ocr_engine
            _ui_imports = (get_ui_detector, get_ocr_engine)
        except ImportError:
            _ui_imports = (None, None)
    return _ui_imports


# ── Element Fingerprinting ─────────────────────────────────────────────────────

# Grid quantization for position-robust fingerprinting
GRID_COLS = 64   # ~20px per cell at 1280px wide
GRID_ROWS = 36   # ~20px per cell at 720px tall


def _element_fingerprint(elements: List[Dict], img_shape: Tuple[int, int]) -> Set[Tuple]:
    """Produce a position-quantized fingerprint of a frame's UI elements.

    Each element becomes a (type, grid_row, grid_col) tuple. The grid
    quantization makes the fingerprint tolerant of small position jitter
    (~20px at 1280×720) while still detecting real structural changes.

    Returns a frozenset-compatible set of tuples.
    """
    h, w = img_shape[:2]
    cell_h = max(1, h / GRID_ROWS)
    cell_w = max(1, w / GRID_COLS)

    fp = set()
    for elem in elements:
        bbox = elem.get("bbox", [0, 0, 0, 0])
        cx = bbox[0] + bbox[2] / 2
        cy = bbox[1] + bbox[3] / 2
        grid_r = min(GRID_ROWS - 1, int(cy / cell_h))
        grid_c = min(GRID_COLS - 1, int(cx / cell_w))
        fp.add((elem.get("type", "unknown"), grid_r, grid_c))
    return fp


def _fingerprint_iou(fp_a: Set[Tuple], fp_b: Set[Tuple]) -> float:
    """Jaccard similarity (intersection over union) of two fingerprints."""
    if not fp_a and not fp_b:
        return 1.0
    if not fp_a or not fp_b:
        return 0.0
    intersection = len(fp_a & fp_b)
    union = len(fp_a | fp_b)
    return intersection / union if union > 0 else 0.0


# ── State Machine ──────────────────────────────────────────────────────────────


class WorkflowStateMachine:
    """Tracks UI state transitions across a sequence of analyzed frames."""

    def __init__(self, transition_threshold: float = 0.5):
        """
        Args:
            transition_threshold: IoU below which we declare a state transition
                                  (0.5 = elements must overlap by less than 50%).
        """
        self.threshold = transition_threshold
        self.states: List[Dict] = []          # Unique states discovered
        self.transitions: List[Dict] = []     # State A → State B edges
        self.frame_states: List[int] = []     # frame_index → state_id mapping
        self._state_fingerprints: List[Set] = []

    def _find_or_create_state(self, fp: Set[Tuple], elements: List[Dict],
                               frame_idx: int, timestamp_ms: float) -> int:
        """Match fingerprint to existing state or create a new one."""
        best_iou = 0.0
        best_state = -1

        for sid, existing_fp in enumerate(self._state_fingerprints):
            iou = _fingerprint_iou(fp, existing_fp)
            if iou > best_iou:
                best_iou = iou
                best_state = sid

        if best_iou >= self.threshold and best_state >= 0:
            # Update existing state: extend time range, refresh element count
            s = self.states[best_state]
            s["last_frame"] = frame_idx
            s["last_time_ms"] = timestamp_ms
            s["duration_frames"] = frame_idx - s["first_frame"] + 1
            s["duration_ms"] = timestamp_ms - s["first_time_ms"]
            # Update fingerprint to incorporate drift (moving average)
            self._state_fingerprints[best_state] = fp
            return best_state

        # New state
        state_id = len(self.states)
        elem_types = sorted(set(e.get("type", "unknown") for e in elements))
        self.states.append({
            "id": state_id,
            "first_frame": frame_idx,
            "last_frame": frame_idx,
            "first_time_ms": timestamp_ms,
            "last_time_ms": timestamp_ms,
            "duration_frames": 1,
            "duration_ms": 0,
            "element_count": len(elements),
            "element_types": elem_types,
            "fingerprint_size": len(fp),
        })
        self._state_fingerprints.append(fp)
        return state_id

    def add_frame(self, elements: List[Dict], frame_idx: int,
                  img_shape: Tuple[int, int], timestamp_ms: float = 0) -> int:
        """Process one frame's detection results.

        Returns the state_id assigned to this frame.
        """
        fp = _element_fingerprint(elements, img_shape)
        state_id = self._find_or_create_state(fp, elements, frame_idx, timestamp_ms)

        # Record transition if state changed
        if self.frame_states:
            prev = self.frame_states[-1]
            if prev != state_id:
                # Check if this transition already recorded
                already_seen = any(
                    t["from"] == prev and t["to"] == state_id
                    for t in self.transitions
                )
                if not already_seen:
                    self.transitions.append({
                        "from": prev,
                        "to": state_id,
                        "at_frame": frame_idx,
                        "at_time_ms": timestamp_ms,
                        "from_state": self.states[prev]["element_types"],
                        "to_state": self.states[state_id]["element_types"],
                    })

        self.frame_states.append(state_id)
        return state_id

    def to_dict(self) -> Dict:
        """Serialize the state machine to a JSON-serializable dict."""
        return {
            "total_frames": len(self.frame_states),
            "unique_states": len(self.states),
            "total_transitions": len(self.transitions),
            "states": self.states,
            "transitions": self.transitions,
            "frame_to_state": self.frame_states,
        }


# ── Expected Workflow Validator ────────────────────────────────────────────────


def validate_workflow(sm: WorkflowStateMachine,
                      expected_states: List[Dict]) -> Dict:
    """Compare observed state sequence against an expected workflow.

    Args:
        sm: The observed state machine from frame analysis.
        expected_states: List of expected states, each with:
            - name: Human-readable state name (e.g., "browser_open")
            - required_types: List of element types that must be present
            - optional_types: List of element types that may be present
            - order: Expected position in sequence (0-based)

    Returns:
        Validation result dict with matched/missed states and confidence.
    """
    matched = []
    missed = []
    extra = []
    state_order = []

    # For each expected state, find the best matching observed state
    for exp in expected_states:
        required = set(exp.get("required_types", []))
        optional = set(exp.get("optional_types", []))
        all_wanted = required | optional

        best_match = None
        best_score = 0.0
        best_sid = -1

        for obs in sm.states:
            obs_types = set(obs["element_types"])

            # Score: what fraction of required types are present?
            if not required:
                # No requirements — match any state
                score = 1.0
            else:
                matched_req = len(required & obs_types)
                score = matched_req / len(required)

            # Bonus for optional matches
            if optional:
                matched_opt = len(optional & obs_types)
                score += 0.3 * (matched_opt / len(optional))

            if score > best_score:
                best_score = score
                best_match = obs
                best_sid = obs["id"]

        result = {
            "expected_name": exp.get("name", "unnamed"),
            "expected_types": sorted(all_wanted),
            "required_types": sorted(required),
            "matched": best_score >= 0.5,
            "confidence": round(best_score, 3),
            "matched_state_id": best_sid,
            "observed_types": best_match["element_types"] if best_match else [],
        }

        if best_score >= 0.5:
            matched.append(result)
            state_order.append(exp.get("name", "unnamed"))
        else:
            missed.append(result)

    # Check for extra states (observed but not expected)
    expected_type_sets = [set(e.get("required_types", [])) | set(e.get("optional_types", []))
                          for e in expected_states]
    matched_ids = {m["matched_state_id"] for m in matched if m["matched_state_id"] >= 0}
    for obs in sm.states:
        if obs["id"] not in matched_ids:
            obs_types = set(obs["element_types"])
            # Check if this is genuinely unexpected
            if not any(_fingerprint_iou(obs_types, exp_set) > 0.3
                      for exp_set in expected_type_sets):
                extra.append({
                    "state_id": obs["id"],
                    "observed_types": obs["element_types"],
                    "first_frame": obs["first_frame"],
                })

    # Overall verdict
    completion_ratio = len(matched) / max(len(expected_states), 1)
    sequential = _check_sequential_order(sm, matched, expected_states)

    return {
        "verdict": "passed" if completion_ratio >= 0.8 and sequential else "partial",
        "completion_ratio": round(completion_ratio, 3),
        "sequential_order_ok": sequential,
        "matched_states": matched,
        "missed_states": missed,
        "extra_states": extra,
        "observed_sequence": [sm.states[sid]["element_types"]
                             for sid in sm.frame_states[::max(1, len(sm.frame_states)//10)]],
    }


def _check_sequential_order(sm: WorkflowStateMachine,
                            matched: List[Dict],
                            expected: List[Dict]) -> bool:
    """Verify that matched states appear in the expected order."""
    # Build expected order from state names
    expected_order = {e.get("name", ""): i for i, e in enumerate(expected)}

    # Get frame indices for matched states
    ordered = []
    for m in matched:
        sid = m["matched_state_id"]
        if sid >= 0 and sid < len(sm.states):
            ordered.append((sm.states[sid]["first_frame"], m["expected_name"]))

    ordered.sort()

    # Check that names appear in expected sequence
    prev_idx = -1
    for _, name in ordered:
        cur_idx = expected_order.get(name, -1)
        if cur_idx < prev_idx:
            return False
        prev_idx = max(prev_idx, cur_idx)

    return True


# ── Frame Processor ────────────────────────────────────────────────────────────


class FrameProcessor:
    """Runs CV detection on a sequence of frames and builds the state machine."""

    def __init__(self, ui_detector: str = "wine", ocr_backend: str = "tesseract",
                 api_url: Optional[str] = None):
        self.ui_detector_name = ui_detector
        self.ocr_backend_name = ocr_backend
        self.api_url = api_url
        self._detector = None
        self._ocr = None

    def _ensure_engines(self):
        """Initialize detection engines, preferring local import over API."""
        if self._detector is not None:
            return

        if self.api_url:
            # Use remote CV sidecar — defer initialization to per-frame calls
            return

        get_det, get_ocr = _lazy_import_ui()
        if get_det is None:
            print("ERROR: ui_detectors not importable and no --api URL given",
                  file=sys.stderr)
            sys.exit(1)

        self._detector = get_det(self.ui_detector_name)
        self._ocr = get_ocr(self.ocr_backend_name)
        print(f"  Detector: {self._detector.name} "
              f"({'GPU' if self._detector.uses_gpu else 'CPU'})", file=sys.stderr)
        print(f"  OCR: {self._ocr.name}", file=sys.stderr)

    def _detect_local(self, img: np.ndarray) -> List[Dict]:
        self._ensure_engines()
        if self._detector is None:
            return []
        return self._detector.detect(img)

    def _detect_api(self, img: np.ndarray, frame_path: str = "") -> List[Dict]:
        """Use CV sidecar API for detection.

        Passes the frame file path (which must be accessible from the
        sidecar container). Falls back to saving a temp file if needed.
        """
        import requests
        import tempfile

        try:
            # Prefer passing image_path (sidecar reads from shared filesystem)
            payload = {"image_path": frame_path,
                       "ui_detector": self.ui_detector_name,
                       "ocr_backend": self.ocr_backend_name}
            r = requests.post(f"{self.api_url}/analyze",
                              json=payload, timeout=30)
            r.raise_for_status()
            result = r.json()
            return result.get("elements", [])
        except Exception as e:
            print(f"  [API] Detection error ({type(e).__name__}): {e}",
                  file=sys.stderr)
            return []

    def detect(self, img: np.ndarray, frame_path: str = "") -> List[Dict]:
        if self.api_url:
            return self._detect_api(img, frame_path)
        return self._detect_local(img)


# ── Main Pipeline ──────────────────────────────────────────────────────────────


def process_frames(frame_dir: str, processor: FrameProcessor,
                   transition_threshold: float = 0.5,
                   start_time_ms: float = 0.0) -> WorkflowStateMachine:
    """Process all PNG frames in a directory and build a state machine.

    Args:
        frame_dir: Directory containing frame_*.png files.
        processor: Configured FrameProcessor.
        transition_threshold: IoU threshold for state transitions.
        start_time_ms: Base timestamp for frame 0.

    Returns:
        Populated WorkflowStateMachine.
    """
    sm = WorkflowStateMachine(transition_threshold=transition_threshold)

    frame_files = sorted(Path(frame_dir).glob("frame_*.png"))
    if not frame_files:
        # Try alternate naming: *.png sorted alphabetically
        frame_files = sorted(Path(frame_dir).glob("*.png"))
        # Filter out diff images
        frame_files = [f for f in frame_files if "diff_" not in f.name]

    if not frame_files:
        print(f"ERROR: No frame_*.png files found in {frame_dir}", file=sys.stderr)
        return sm

    print(f"Processing {len(frame_files)} frames from {frame_dir}...", file=sys.stderr)

    n_frames = len(frame_files)
    last_report = 0

    for idx, fpath in enumerate(frame_files):
        img = cv2.imread(str(fpath))
        if img is None:
            print(f"  [WARN] Could not read {fpath.name}", file=sys.stderr)
            continue

        elements = processor.detect(img, frame_path=str(fpath))
        timestamp = start_time_ms + (idx * 1000.0 / 5.0)  # assume ~5fps if unknown
        sm.add_frame(elements, idx, img.shape[:2], timestamp)

        # Progress: every 10% or 50 frames
        if idx > 0 and (idx - last_report >= max(1, n_frames // 10)):
            pct = 100 * idx // n_frames
            print(f"  {pct:3d}%  frame {idx}/{n_frames}  "
                  f"{len(elements)} elements  "
                  f"{len(sm.states)} states found", file=sys.stderr)
            last_report = idx

    print(f"  Done: {n_frames} frames → {len(sm.states)} unique states, "
          f"{len(sm.transitions)} transitions", file=sys.stderr)
    return sm


def print_summary(sm: WorkflowStateMachine, validation: Optional[Dict] = None):
    """Print a human-readable summary of the state machine."""
    print()
    print("=" * 72)
    print("  Workflow Sequence Evaluation")
    print("=" * 72)
    print(f"  Frames processed:     {sm.to_dict()['total_frames']}")
    print(f"  Unique UI states:     {len(sm.states)}")
    print(f"  State transitions:    {len(sm.transitions)}")
    print()

    # State timeline
    print("  State Timeline:")
    print(f"  {'State':>5s}  {'Types':<40s}  {'Elems':>5s}  {'Frames':>7s}  {'First':>6s}")
    print(f"  {'-----':>5s}  {'----':<40s}  {'-----':>5s}  {'------':>7s}  {'-----':>6s}")
    for s in sm.states:
        types_str = ", ".join(s["element_types"][:6])
        if len(s["element_types"]) > 6:
            types_str += f" +{len(s['element_types']) - 6} more"
        print(f"  S{s['id']:03d}   {types_str:<40s}  "
              f"{s['element_count']:>5d}  "
              f"{s['first_frame']:>4d}-{s['last_frame']:<4d}  "
              f"{s['duration_ms']:>5.0f}ms")
    print()

    # Transitions
    if sm.transitions:
        print("  Transitions:")
        for t in sm.transitions:
            from_types = ", ".join(t["from_state"][:3])
            to_types = ", ".join(t["to_state"][:3])
            print(f"    S{t['from']:03d} → S{t['to']:03d} "
                  f"(@frame {t['at_frame']}): "
                  f"[{from_types}...] → [{to_types}...]")
        print()

    # Validation
    if validation:
        print(f"  Validation: {validation['verdict'].upper()}")
        print(f"  Completion:  {validation['completion_ratio']:.0%} "
              f"({len(validation['matched_states'])}/{len(validation['matched_states']) + len(validation['missed_states'])} states)")
        if validation['missed_states']:
            print(f"  Missed states:")
            for m in validation['missed_states']:
                print(f"    ✗ {m['expected_name']}: needed {m['required_types']}")
        if validation['extra_states']:
            print(f"  Extra states: {len(validation['extra_states'])}")
        print()

    print("=" * 72)


# ── CLI ────────────────────────────────────────────────────────────────────────


# ── CLIP Scene Labeler ─────────────────────────────────────────────────────────


def label_states_with_clip(sm: WorkflowStateMachine, frame_dir: str,
                            clip_index_dir: str) -> WorkflowStateMachine:
    """Label each state with its CLIP-predicted scene type.

    For each unique state, finds the representative frame (midpoint of the
    state's frame range), looks up its CLIP embedding, and assigns the
    top-3 nearest text labels (e.g., "save_dialog", "settings", etc.).

    Args:
        sm: Populated state machine from frame analysis.
        frame_dir: Directory containing the frame PNGs.
        clip_index_dir: CLIP frame index directory (built via /search/build).

    Returns:
        Same state machine with scene labels added to each state.
    """
    try:
        from clip_embedder import get_clip_embedder
        from clip_index import FrameIndex
    except ImportError:
        print("  [CLIP] clip_embedder/clip_index not available — skipping labels",
              file=sys.stderr)
        return sm

    clip = get_clip_embedder()
    if not clip.available:
        print("  [CLIP] No CLIP backend available — skipping labels",
              file=sys.stderr)
        return sm

    if not os.path.isdir(clip_index_dir):
        print(f"  [CLIP] Index not found: {clip_index_dir} — skipping labels",
              file=sys.stderr)
        return sm

    idx = FrameIndex(clip_index_dir)
    if len(idx) == 0:
        print("  [CLIP] Empty index — skipping labels", file=sys.stderr)
        return sm

    # Scene type candidates for zero-shot classification
    SCENE_CANDIDATES = [
        "a save dialog with file name and type fields",
        "a settings window with tabs and checkboxes",
        "an error dialog with a message and OK button",
        "a notepad text editor with a menu bar",
        "a control panel with settings categories",
        "a file manager with a file listing",
        "a browser window with navigation controls",
        "a terminal window with command prompt",
        "a context menu with options",
        "a wizard dialog with step-by-step pages",
        "an about dialog with application information",
        "a properties dialog with file metadata",
        "a desktop with multiple open windows",
        "a form fill dialog with input fields",
    ]

    # Embed scene candidates once
    candidate_embs = clip.embed_text(SCENE_CANDIDATES)
    candidate_embs = candidate_embs / np.linalg.norm(candidate_embs, axis=1, keepdims=True)

    for state in sm.states:
        # Find representative frame (midpoint of state's frame range)
        mid_frame = (state["first_frame"] + state["last_frame"]) // 2
        frame_files = sorted(
            [f for f in os.listdir(frame_dir) if f.endswith((".png", ".jpg"))]
        )
        if mid_frame >= len(frame_files):
            continue

        frame_path = os.path.join(frame_dir, frame_files[mid_frame])

        # Look up in CLIP index
        frame_result = idx.find_by_path(frame_path)
        if frame_result is None:
            continue

        # Classify scene type via zero-shot
        frame_emb = np.array(frame_result["embedding"], dtype=np.float32)
        frame_emb = frame_emb / np.linalg.norm(frame_emb)
        scores = candidate_embs @ frame_emb  # cosine similarity
        top3 = np.argsort(scores)[-3:][::-1]

        state["clip_labels"] = [
            {
                "scene": SCENE_CANDIDATES[i].split(" ")[1]
                         if "a " in SCENE_CANDIDATES[i]
                         else SCENE_CANDIDATES[i].split(" ")[0],
                "description": SCENE_CANDIDATES[i],
                "confidence": round(float(scores[i]), 3),
            }
            for i in top3
        ]

        # Also store the raw embedding for downstream use
        state["clip_embedding"] = [
            round(float(frame_emb[j]), 6) for j in range(0, min(4, len(frame_emb)))
        ]  # Just first 4 dims as fingerprint

    return sm


# ── Main ────────────────────────────────────────────────────────────────────────


def main():
    parser = argparse.ArgumentParser(
        description="Evaluate UI workflow sequence from demo frame captures")
    parser.add_argument("--frames", required=True,
                        help="Directory containing frame PNGs")
    parser.add_argument("--expected", default=None,
                        help="JSON file with expected workflow definition")
    parser.add_argument("--api", default=None,
                        help="CV sidecar API URL (e.g., http://localhost:8001)")
    parser.add_argument("--detector", default="wine",
                        help="UI detector backend (default: wine)")
    parser.add_argument("--ocr", default="tesseract",
                        help="OCR backend (default: tesseract)")
    parser.add_argument("--threshold", type=float, default=0.5,
                        help="IoU threshold for state transitions (default: 0.5)")
    parser.add_argument("--output", default=None,
                        help="Write JSON output to file")
    parser.add_argument("--quiet", action="store_true",
                        help="Suppress progress output")
    parser.add_argument("--clip-search", default=None, metavar="QUERY",
                        help="Natural language search over CLIP index (e.g., "
                             "'find save dialog frames')")
    parser.add_argument("--clip-index", default=None, metavar="DIR",
                        help="CLIP frame index directory (for semantic scene labels)")
    parser.add_argument("--clip-k", type=int, default=20, metavar="N",
                        help="Top-K results from CLIP search (default: 20)")

    args = parser.parse_args()

    if not os.path.isdir(args.frames):
        print(f"ERROR: frames directory not found: {args.frames}")
        sys.exit(1)

    # Initialize processor
    processor = FrameProcessor(
        ui_detector=args.detector,
        ocr_backend=args.ocr,
        api_url=args.api,
    )

    # Process frames
    t0 = time.time()
    sm = process_frames(args.frames, processor,
                        transition_threshold=args.threshold)
    elapsed = time.time() - t0

    # CLIP scene labeling
    if args.clip_index:
        print(f"\n  [CLIP] Labeling states with scene types from {args.clip_index}...",
              file=sys.stderr)
        sm = label_states_with_clip(sm, args.frames, args.clip_index)

    # CLIP semantic search results
    clip_results = None
    if args.clip_search:
        print(f"\n  [CLIP] Searching: \"{args.clip_search}\"...", file=sys.stderr)
        try:
            from clip_embedder import get_clip_embedder
            from clip_index import FrameIndex

            clip = get_clip_embedder()
            if clip.available and args.clip_index and os.path.isdir(args.clip_index):
                idx = FrameIndex(args.clip_index)
                if len(idx) > 0:
                    results = idx.search(args.clip_search, k=args.clip_k,
                                         clip_embedder=clip)
                    clip_results = {
                        "query": args.clip_search,
                        "total_in_index": len(idx),
                        "results": [
                            {
                                "path": r["path"],
                                "similarity": r["similarity"],
                                "metadata": r.get("metadata", {}),
                            }
                            for r in results
                        ],
                    }
                    print(f"  [CLIP] Found {len(results)} matching frames",
                          file=sys.stderr)
        except ImportError as e:
            print(f"  [CLIP] Import error: {e}", file=sys.stderr)

    # Load expected workflow if provided
    expected = None
    if args.expected and os.path.isfile(args.expected):
        with open(args.expected) as f:
            expected = json.load(f)

    # Validate if expected workflow provided
    validation = None
    if expected:
        validation = validate_workflow(sm, expected.get("states", []))

    # Output
    result = {
        "workflow": sm.to_dict(),
        "config": {
            "frames_dir": args.frames,
            "detector": args.detector,
            "transition_threshold": args.threshold,
            "processing_time_s": round(elapsed, 2),
        },
    }
    if validation:
        result["validation"] = validation
    if clip_results:
        result["clip_search"] = clip_results

    if args.output:
        with open(args.output, "w") as f:
            json.dump(result, f, indent=2)
        print(f"Wrote: {args.output}", file=sys.stderr)

    if not args.quiet:
        print_summary(sm, validation)
        if clip_results:
            print(f"\n  CLIP Search Results for \"{clip_results['query']}\":")
            for i, r in enumerate(clip_results["results"][:5]):
                meta = r.get("metadata", {})
                scene = meta.get("scene_type", "unknown")
                print(f"  #{i+1}  similarity={r['similarity']:.3f}  "
                      f"scene={scene}  {r['path']}")
            if len(clip_results["results"]) > 5:
                print(f"  ... and {len(clip_results['results'])-5} more")
    else:
        # Minimal output
        output = {
            "frames": sm.to_dict()["total_frames"],
            "states": len(sm.states),
            "transitions": len(sm.transitions),
            "verdict": validation["verdict"] if validation else "unevaluated",
            "processing_time_s": round(elapsed, 2),
        }
        if clip_results:
            output["clip_matches"] = len(clip_results["results"])
        print(json.dumps(output))


if __name__ == "__main__":
    main()
