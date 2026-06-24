#!/usr/bin/env python3
# EXECUTION: EITHER — API server mode in sidecar container, CLI mode on host
# STATUS: ACTIVE — winebot-cv sidecar entrypoint; /health, /analyze, /batch endpoints
"""WineBot CV Sidecar — unified CV/OCR analysis service.

Provides a lightweight FastAPI server that accepts screenshots and returns
UI element detections + OCR text. Supports two tiers:
  Tier 1 (built-in): OpenCV contour/edge detection + Tesseract OCR
  Tier 2 (full):     YOLOv8 object detection (requires PyTorch + ultralytics)

Endpoints:
  GET  /health           — liveness check, returns tier + model status
  POST /analyze          — submit PNG image, get UI elements + OCR text
  POST /batch            — submit MKV video path, get per-frame analysis
  GET  /batch/{job_id}   — check batch job status

Also runnable in CLI mode:
  python3 cv-sidecar-server.py --cli --video /path/to/video.mkv
"""

import argparse
import json
import os
import subprocess
import sys
import tempfile
import threading
import time
import traceback
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

import base64
import urllib.request

import cv2
import numpy as np

# ── Swappable detection engines ───────────────────────────────────────────────
from ui_detectors import (
    get_ui_detector, available_detectors, current_detector,
    UIDetector, ContourDetector, YOLOUIDetector, OmniParserDetector,
)
from ocr_engines import (
    get_ocr_engine, available_backends, current_backend,
    OCREngine, TesseractEngine, PaddleOCREngine,
)
# Ollama VLM backend (activated via env var VLM_PROVIDER=ollama)
try:
    from vlm_ollama import get_ollama_vlm
    _HAS_OLLAMA = True
except ImportError:
    _HAS_OLLAMA = False

# Model registry (provenance for all pipeline models)
try:
    from model_registry import ModelRegistry
    _model_registry = ModelRegistry.from_scan("/models")
except ImportError:
    _model_registry = None

# ── FastAPI (imported lazily in serve() to allow CLI-only usage) ─────────────

try:
    from fastapi import FastAPI, HTTPException
    from fastapi.responses import JSONResponse
    import uvicorn
    HAS_FASTAPI = True
except ImportError:
    HAS_FASTAPI = False


def analyze_image(img: np.ndarray, ui_detector: Optional[str] = None,
                  ocr_backend: Optional[str] = None) -> Dict:
    """Full analysis of a single image using configured engines. Returns structured JSON.

    Args:
        ui_detector: Override UI detector (contour|yolo|omniparser). None uses env default.
        ocr_backend: Override OCR engine (tesseract|paddleocr). None uses env default.
    """
    h, w = img.shape[:2]

    detector = get_ui_detector(ui_detector)
    ui_elements = detector.detect(img)
    ui_state = detector.classify_ui_state(img, ui_elements)

    ocr = get_ocr_engine(ocr_backend)
    ocr_regions = ocr.detect_text(img)

    # Find click targets from OCR text
    click_targets = _find_click_targets(ocr_regions)

    result = {
        "resolution": f"{w}x{h}",
        "detector": detector.name,
        "ocr_engine": ocr.name,
        "ui_elements": len(ui_elements),
        "element_detail": ui_elements[:30],
        "ui_state": ui_state,
        "interactive_elements": sum(1 for e in ui_elements if e.get("interactive")),
        "ocr_regions": len(ocr_regions),
        "key_text": [r["text"] for r in ocr_regions[:30] if r.get("confidence", 0) > 30],
        "click_targets": click_targets,
        "timestamp_utc": datetime.now(timezone.utc).isoformat(),
    }

    return result


def _find_click_targets(ocr_regions: List[Dict]) -> Dict[str, List[int]]:
    button_map = {
        "save": "save_button", "cancel": "cancel_button", "open": "open_button",
        "ok": "ok_button", "yes": "yes_button", "no": "no_button",
        "help": "help_button", "close": "close_button", "next": "next_button",
        "back": "back_button", "finish": "finish_button", "install": "install_button",
        "browse": "browse_button", "apply": "apply_button", "submit": "submit_button",
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


# ── Batch job tracking ───────────────────────────────────────────────────────

_batch_jobs: Dict[str, Dict] = {}


def _run_batch_job(job_id: str, video_path: str, frame_interval: float):
    _batch_jobs[job_id]["status"] = "running"
    try:
        runner_script = str(Path(__file__).resolve().parent / "cv-test-runner.py")
        output_dir = os.path.join(tempfile.gettempdir(), f"cv_batch_{job_id}")
        cmd = [sys.executable, runner_script,
               "--video", video_path,
               "--output", output_dir,
               "--frame-interval", str(frame_interval),
               "--mode", "built-in"]
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=600)
        _batch_jobs[job_id]["status"] = "complete" if result.returncode == 0 else "failed"
        _batch_jobs[job_id]["exit_code"] = result.returncode
        _batch_jobs[job_id]["completed_at"] = datetime.now(timezone.utc).isoformat()
    except subprocess.TimeoutExpired:
        _batch_jobs[job_id]["status"] = "timeout"
    except Exception as e:
        _batch_jobs[job_id]["status"] = "error"
        _batch_jobs[job_id]["error"] = str(e)


# ── API Server ───────────────────────────────────────────────────────────────

def create_app() -> FastAPI:
    app = FastAPI(title="WineBot CV Sidecar", version="1.0")

    @app.get("/health")
    async def health():
        detectors = available_detectors()
        ocr_backends = available_backends()
        active_detector = current_detector()
        active_ocr = current_backend()

        # Check VLM provider (Ollama or local)
        vlm_status = "disabled"
        vlm_model = None
        vlm_host = None
        vlm_provenance = None
        vlm_provider = os.environ.get("VLM_PROVIDER", "").lower()

        if vlm_provider == "ollama" and _HAS_OLLAMA:
            ollama = get_ollama_vlm()
            if ollama and ollama.available:
                vlm_status = "connected"
                vlm_model = ollama.model
                vlm_host = ollama.host
                vlm_provenance = ollama.provenance
            else:
                vlm_status = "unreachable"
        elif detectors.get("vlm_ground"):
            vlm_status = "local"

        # Git commit for reproducibility
        git_commit = ""
        try:
            from provenance import get_git_commit
            git_commit = get_git_commit()
        except ImportError:
            pass

        return {
            "status": "healthy",
            "opencv": cv2.__version__,
            "active": {
                "ui_detector": active_detector,
                "ocr_engine": active_ocr,
            },
            "available_detectors": detectors,
            "available_ocr_backends": ocr_backends,
            "vlm": {
                "provider": vlm_provider or "none",
                "status": vlm_status,
                "model": vlm_model,
                "host": vlm_host,
                "provenance": vlm_provenance,
            },
            "model_catalog": {
                "total": _model_registry.to_dict()["total_models"] if _model_registry else 0,
                "active": _model_registry.to_dict()["active_models"] if _model_registry else 0,
                "fingerprinted_at": _model_registry.to_dict()["generated_at"] if _model_registry else "",
            } if _model_registry else None,
            "provenance": {
                "git_commit": git_commit,
            },
            "env": {
                "UI_DETECTOR": os.environ.get("UI_DETECTOR", "contour"),
                "OCR_BACKEND": os.environ.get("OCR_BACKEND", "paddle_onnx:tiny"),
            },
        }

    @app.get("/models")
    async def model_catalog():
        """Full model provenance catalog with SHA256 fingerprints.

        Returns the complete model registry including:
          - Upstream provenance (source repo, license, citation)
          - Training lineage (dataset, splits, hyperparameters)
          - Deployment fingerprints (SHA256, file size, last validated)
          - Version lifecycle (active/deprecated/superseded)
          - Supply chain audit trail

        Useful for paper methods sections and reproducibility.
        """
        if _model_registry is None:
            raise HTTPException(status_code=501, detail="Model registry not available")

        return JSONResponse(content=_model_registry.to_dict())

    @app.get("/models/citation")
    async def model_citation():
        """Methods-section citation string for all pipeline models."""
        if _model_registry is None:
            raise HTTPException(status_code=501, detail="Model registry not available")

        return JSONResponse(content={
            "citation": _model_registry.get_citation(),
            "audit_trail": _model_registry.audit_trail(),
        })

    @app.post("/analyze")
    async def analyze(request_data: Dict):
        """Analyze a single image. Accepts JSON with image_path.

        Optional: "ocr_backend" and "ui_detector" keys to override defaults
        for this request (e.g. comparative analysis).
        """
        image_path = request_data.get("image_path", "")
        if not image_path or not os.path.exists(image_path):
            raise HTTPException(status_code=400, detail="image_path required and must exist")

        img = cv2.imread(image_path)
        if img is None:
            raise HTTPException(status_code=400, detail=f"Cannot read image: {image_path}")

        # Allow per-request engine override for comparative analysis
        req_ui = request_data.get("ui_detector")
        req_ocr = request_data.get("ocr_backend")
        result = analyze_image(img, ui_detector=req_ui, ocr_backend=req_ocr)
        return JSONResponse(content=result)

    @app.post("/batch")
    async def batch_start(request_data: Dict):
        """Start a batch analysis job on an MKV video."""
        video_path = request_data.get("video_path", "")
        if not video_path or not os.path.exists(video_path):
            raise HTTPException(status_code=400, detail="video_path required and must exist")

        job_id = str(uuid.uuid4())[:8]
        frame_interval = request_data.get("frame_interval", 1.0)

        _batch_jobs[job_id] = {
            "job_id": job_id, "video": video_path,
            "frame_interval": frame_interval, "status": "pending",
            "created_at": datetime.now(timezone.utc).isoformat(),
        }

        # Fire and forget (in production, use a task queue)
        t = threading.Thread(target=_run_batch_job, args=(job_id, video_path, frame_interval), daemon=True)
        t.start()

        return JSONResponse(content={"job_id": job_id, "status": "pending"})

    @app.get("/batch/{job_id}")
    async def batch_status(job_id: str):
        if job_id not in _batch_jobs:
            raise HTTPException(status_code=404, detail="Job not found")
        return JSONResponse(content=_batch_jobs[job_id])

    # ── Live CV Watcher ───────────────────────────────────────────────────

    _watch_state = {"running": False, "frame_index": 0, "started_at": "",
                    "output_dir": "", "session_dir": "", "api_url": "",
                    "api_token": ""}
    _watch_thread = None

    def _watch_loop():
        """Background loop: capture screenshots via API, analyze, write jsonl."""
        import urllib.request
        import base64
        import time as _time

        state = _watch_state
        out_dir = state["output_dir"]
        os.makedirs(out_dir, exist_ok=True)
        log_path = os.path.join(out_dir, "watcher.jsonl")

        # Write header
        with open(log_path, "w", encoding="utf-8") as f:
            f.write(json.dumps({
                "event": "watcher_start",
                "timestamp_utc": datetime.now(timezone.utc).isoformat(),
                "output_dir": out_dir,
            }) + "\n")

        last_frame = None
        while state["running"]:
            loop_start = _time.time()
            ts = datetime.now(timezone.utc).isoformat()
            ts_epoch = int(_time.time() * 1000)

            try:
                # Capture screenshot from WineBot API
                api_url = state["api_url"]
                token = state["api_token"]
                ss_path = os.path.join(out_dir, f"frame_{state['frame_index']:04d}.png")

                req = urllib.request.Request(f"{api_url}/screenshot")
                if token:
                    req.add_header("X-API-Key", token)
                with urllib.request.urlopen(req, timeout=5) as resp:
                    with open(ss_path, "wb") as f:
                        f.write(resp.read())

                if os.path.exists(ss_path) and os.path.getsize(ss_path) > 100:
                    img = cv2.imread(ss_path)
                    if img is not None:
                        # Analyze with current engines
                        result = analyze_image(img)
                        pixels_changed = 0
                        if last_frame is not None:
                            diff = cv2.absdiff(last_frame, cv2.cvtColor(img, cv2.COLOR_BGR2GRAY))
                            pixels_changed = int((diff > 30).sum())

                        # Window inventory via API
                        windows = []
                        try:
                            req2 = urllib.request.Request(f"{api_url}/windows")
                            if token:
                                req2.add_header("X-API-Key", token)
                            with urllib.request.urlopen(req2, timeout=3) as resp2:
                                win_data = json.loads(resp2.read())
                                windows = [w.get("title", "") for w in win_data.get("windows", [])]
                        except Exception:
                            pass

                        # Detection: find interesting windows
                        interesting = [w for w in windows if any(
                            kw in w.lower() for kw in
                            ("notepad", "save", "error", "winebot", "vlc", "wine",
                             "dialog", "warning", "confirm", "open", "cmd", "registry",
                             "supertux", "zip", "install", "browse")
                        )]

                        snapshot = {
                            "event": "snapshot",
                            "index": state["frame_index"],
                            "timestamp_utc": ts,
                            "timestamp_epoch_ms": ts_epoch,
                            "frame_path": ss_path,
                            "pixels_changed": pixels_changed,
                            "windows_count": len(windows),
                            "windows": windows,
                            "interesting_windows": interesting,
                            "elements": result,
                        }
                        with open(log_path, "a", encoding="utf-8") as f:
                            f.write(json.dumps(snapshot) + "\n")

                        last_frame = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
                        state["frame_index"] += 1

            except Exception as e:
                with open(log_path, "a", encoding="utf-8") as f:
                    f.write(json.dumps({
                        "event": "watcher_error", "error": str(e),
                        "timestamp_utc": ts,
                    }) + "\n")

            # Sleep for the remaining interval
            elapsed = _time.time() - loop_start
            interval = state.get("interval", 1.0)
            _time.sleep(max(0, interval - elapsed))

        # Write footer on stop
        with open(log_path, "a", encoding="utf-8") as f:
            f.write(json.dumps({
                "event": "watcher_stop",
                "timestamp_utc": datetime.now(timezone.utc).isoformat(),
                "total_frames": state["frame_index"],
            }) + "\n")

        state["running"] = False

    @app.post("/watch/start")
    async def watch_start(request_data: Dict):
        """Start live CV watcher. Captures screenshots via WineBot API.

        Required: api_url (e.g. http://winebot:8000), session_dir
        Optional: api_token, interval (default 1.0s)
        """
        if _watch_state["running"]:
            return JSONResponse(content={
                "status": "already_running",
                "frame_index": _watch_state["frame_index"],
            })

        api_url = request_data.get("api_url", "http://localhost:8000")
        session_dir = request_data.get("session_dir", "")
        if not session_dir:
            raise HTTPException(status_code=400, detail="session_dir required")

        output_dir = os.path.join(session_dir, "analysis", "cv")
        interval = float(request_data.get("interval", 1.0))

        _watch_state.update({
            "running": True, "frame_index": 0,
            "started_at": datetime.now(timezone.utc).isoformat(),
            "output_dir": output_dir, "session_dir": session_dir,
            "api_url": api_url, "api_token": request_data.get("api_token", ""),
            "interval": interval,
        })

        _watch_thread = threading.Thread(target=_watch_loop, daemon=True)
        _watch_thread.start()

        return JSONResponse(content={
            "status": "started", "output_dir": output_dir,
            "interval": interval, "api_url": api_url,
        })

    @app.post("/watch/stop")
    async def watch_stop():
        """Stop live CV watcher. Returns summary of captured frames."""
        if not _watch_state["running"]:
            return JSONResponse(content={"status": "not_running"})

        _watch_state["running"] = False
        return JSONResponse(content={
            "status": "stopped",
            "total_frames": _watch_state["frame_index"],
            "output_dir": _watch_state["output_dir"],
        })

    @app.get("/watch/status")
    async def watch_status():
        """Get current watcher state."""
        return JSONResponse(content={
            "running": _watch_state["running"],
            "frame_index": _watch_state["frame_index"],
            "started_at": _watch_state["started_at"],
            "output_dir": _watch_state["output_dir"],
        })

    @app.post("/wait-for-window")
    async def wait_for_window(request_data: Dict):
        """Poll for a window by title substring using CV/OCR.

        Replaces xdotool-based cv_wait() for Wine 10.0 where X11 window
        names are empty. Captures screenshots from the WineBot API,
        runs detection+OCR, and checks if the expected window title
        appears in the OCR text.

        Request body:
          {"window_title": "Acrobat", "timeout": 30,
           "api_url": "http://172.17.0.1:8000",
           "api_token": "..."}

        Returns:
          {"found": true, "window_title": "Acrobat Reader DC",
           "position": [x, y, w, h], "elapsed_s": 2.5, "confidence": 0.95}
          or {"found": false, "elapsed_s": 30.0}
        """
        import time as _time

        window_substr = request_data.get("window_title", "")
        timeout = int(request_data.get("timeout", 30))
        api_url = request_data.get("api_url", os.environ.get("WINEBOT_API_URL", ""))
        api_token = request_data.get("api_token", os.environ.get("WINEBOT_API_TOKEN", ""))

        if not window_substr:
            raise HTTPException(status_code=400, detail="window_title required")
        if not api_url:
            raise HTTPException(status_code=400, detail="api_url required")

        window_lower = window_substr.lower()
        deadline = _time.time() + timeout

        while _time.time() < deadline:
            # Capture screenshot from WineBot API
            try:
                req = urllib.request.Request(f"{api_url}/screenshot")
                if api_token:
                    req.add_header("X-API-Key", api_token)
                with urllib.request.urlopen(req, timeout=5) as resp:
                    img_data = resp.read()
                if len(img_data) < 100:
                    _time.sleep(0.5)
                    continue

                nparr = np.frombuffer(img_data, np.uint8)
                img = cv2.imdecode(nparr, cv2.IMREAD_COLOR)
                if img is None:
                    _time.sleep(0.5)
                    continue
            except Exception:
                _time.sleep(1.0)
                continue

            # Analyze the screenshot
            result = analyze_image(img)

            # Search OCR text for the window title
            for entry in result.get("ocr_text", []):
                text = entry.get("text", "")
                if window_lower in text.lower():
                    elapsed = _time.time() - (deadline - timeout)
                    bbox = entry.get("bbox", [0, 0, 0, 0])
                    print(f"[wait-for-window] Found '{text}' "
                          f"after {elapsed:.1f}s", file=sys.stderr)
                    return JSONResponse(content={
                        "found": True,
                        "window_title": text,
                        "position": bbox,
                        "elapsed_s": round(elapsed, 2),
                        "confidence": round(entry.get("confidence", 0.8), 3),
                    })

            # Also check element labels
            for elem in result.get("elements", []):
                label = elem.get("label", "")
                if window_lower in label.lower():
                    elapsed = _time.time() - (deadline - timeout)
                    print(f"[wait-for-window] Found element '{label}' "
                          f"after {elapsed:.1f}s", file=sys.stderr)
                    return JSONResponse(content={
                        "found": True,
                        "window_title": label,
                        "position": elem.get("bbox", [0, 0, 0, 0]),
                        "elapsed_s": round(elapsed, 2),
                        "confidence": round(elem.get("confidence", 0.8), 3),
                    })

            _time.sleep(0.5)

        # Timeout
        elapsed = timeout
        print(f"[wait-for-window] TIMEOUT: '{window_substr}' not found "
              f"after {timeout}s", file=sys.stderr)
        return JSONResponse(content={
            "found": False,
            "window_title": window_substr,
            "elapsed_s": round(float(elapsed), 2),
        })

    @app.post("/ground")
    async def vlm_ground(request_data: Dict):
        """Ground a natural language query to a specific UI element.

        Tries Ollama VLM first (if VLM_PROVIDER=ollama is set and
        OLLAMA_HOST points to a reachable server), falls back to
        the local VLM grounding detector (KV-Ground-8B).

        Request body:
          {"image": "<base64 PNG>", "query": "the blue Submit button"}

        Returns:
          {"found": true, "bbox": [x, y, w, h], "label": "Submit button",
           "confidence": 0.92, "query": "the blue Submit button",
           "backend": "ollama"}
        """
        import time as _time

        img_b64 = request_data.get("image", "")
        query = request_data.get("query", "")

        if not img_b64:
            raise HTTPException(status_code=400, detail="image required")
        if not query:
            raise HTTPException(status_code=400, detail="query required")

        # Decode image
        try:
            img_bytes = base64.b64decode(img_b64)
        except Exception:
            raise HTTPException(status_code=400, detail="invalid base64 image")

        nparr = np.frombuffer(img_bytes, np.uint8)
        img = cv2.imdecode(nparr, cv2.IMREAD_COLOR)
        if img is None:
            raise HTTPException(status_code=400, detail="could not decode image")

        # --- Try Ollama VLM first ---
        if _HAS_OLLAMA:
            ollama = get_ollama_vlm()
            if ollama is not None:
                t0 = _time.time()
                result = ollama.ground(img, query)
                elapsed = (_time.time() - t0) * 1000

                if result and result.get("bbox") and result.get("confidence", 0) >= 0.3:
                    return JSONResponse(content={
                        "found": True,
                        "bbox": result["bbox"],
                        "label": result.get("label", query),
                        "confidence": result.get("confidence", 0.0),
                        "query": query,
                        "backend": "ollama",
                        "model": ollama.model,
                        "inference_ms": round(elapsed, 1),
                        "provenance": ollama.provenance,
                    })
                if result:
                    # VLM responded but couldn't parse coordinates
                    return JSONResponse(content={
                        "found": False,
                        "query": query,
                        "backend": "ollama",
                        "raw_response": result.get("raw_response", ""),
                    })

        # --- Fall back to local VLM detector ---
        detector_backend = request_data.get("ui_detector", "vlm_ground")
        detector = get_ui_detector(detector_backend)

        if not hasattr(detector, 'ground'):
            raise HTTPException(
                status_code=400,
                detail=f"detector '{detector.name}' does not support grounding. "
                       f"Set VLM_PROVIDER=ollama OLLAMA_HOST=... or use 'vlm_ground' "
                       f"with a local model."
            )

        result = detector.ground(img, query)
        if result is None or result.get("confidence", 0) < 0.3:
            return JSONResponse(content={
                "found": False,
                "query": query,
                "backend": detector.name,
            })

        return JSONResponse(content={
            "found": True,
            "bbox": result.get("bbox", [0, 0, 0, 0]),
            "label": result.get("label", query),
            "confidence": result.get("confidence", 0.0),
            "query": query,
            "backend": detector.name,
        })

    @app.post("/describe")
    async def describe_frame(request_data: Dict):
        """Generate a natural language description of a UI screenshot.

        Tries Ollama VLM first (if VLM_PROVIDER=ollama is set),
        falls back to local Florence-2.

        Request body:
          {"image": "<base64 PNG>", "style": "detailed"}

        Style options (Florence-2): brief, detailed, more_detailed, od, ocr
        Style options (Ollama):    brief, detailed

        Returns:
          {"caption": "...", "style": "detailed", "backend": "ollama",
           "model": "qwen3.5:35b", "inference_ms": 450}
        """
        import time as _time

        img_b64 = request_data.get("image", "")
        style = request_data.get("style", "detailed")

        if not img_b64:
            raise HTTPException(status_code=400, detail="image required")

        # Decode image
        try:
            img_bytes = base64.b64decode(img_b64)
        except Exception:
            raise HTTPException(status_code=400, detail="invalid base64 image")

        nparr = np.frombuffer(img_bytes, np.uint8)
        img = cv2.imdecode(nparr, cv2.IMREAD_COLOR)
        if img is None:
            raise HTTPException(status_code=400, detail="could not decode image")

        # --- Try Ollama VLM first ---
        if _HAS_OLLAMA:
            ollama = get_ollama_vlm()
            if ollama is not None:
                t0 = _time.time()
                caption = ollama.describe(img, style=style)
                elapsed = (_time.time() - t0) * 1000

                if caption:
                    return JSONResponse(content={
                        "caption": caption,
                        "style": style,
                        "backend": "ollama",
                        "model": ollama.model,
                        "inference_ms": round(elapsed, 1),
                        "provenance": ollama.provenance,
                    })

        # --- Try captioning sidecar ---
        captioning_url = os.environ.get("CAPTIONING_SIDECAR_URL", "")
        if captioning_url:
            try:
                body = json.dumps({
                    "image": img_b64, "style": style
                }).encode("utf-8")
                req = urllib.request.Request(
                    f"{captioning_url}/caption",
                    data=body,
                    headers={"Content-Type": "application/json"},
                    method="POST",
                )
                t0 = _time.time()
                with urllib.request.urlopen(req, timeout=90) as resp:
                    result = json.loads(resp.read().decode())
                    elapsed = (_time.time() - t0) * 1000
                    if result.get("caption"):
                        return JSONResponse(content={
                            "caption": result["caption"],
                            "style": style,
                            "backend": "captioning_sidecar",
                            "model": result.get("model", "Florence-2"),
                            "inference_ms": round(elapsed, 1),
                        })
            except Exception as e:
                print(f"[describe] Captioning sidecar unavailable: {e}",
                      file=sys.stderr)

        # --- Fall back to local Florence-2 ---
        try:
            from florence2_captioner import get_captioner
        except ImportError:
            raise HTTPException(
                status_code=501,
                detail="No captioner available. Set VLM_PROVIDER=ollama "
                       "OLLAMA_HOST=... or install transformers + Florence-2.")

        captioner = get_captioner()
        if not captioner.available:
            raise HTTPException(
                status_code=503,
                detail="No captioner available. Set VLM_PROVIDER=ollama "
                       "or install Florence-2 to /models/florence2/")

        t0 = _time.time()
        caption = captioner.caption(img, style=style)
        elapsed = (_time.time() - t0) * 1000

        return JSONResponse(content={
            "caption": caption,
            "style": style,
            "backend": captioner.name,
            "inference_ms": round(elapsed, 1),
        })

    @app.post("/search")
    async def search_frames(request_data: Dict):
        """Semantic search over the frame archive using natural language.

        Uses CLIP embeddings to find frames matching a text description.
        Requires a pre-built frame index (created via /search/build).

        Request body:
          {"query": "a save dialog with a filename text field",
           "k": 10, "index_dir": "/data/frame_index"}

        Returns:
          {"results": [{path, similarity, metadata}, ...], "query_ms": 15}
        """
        import time as _time

        query = request_data.get("query", "")
        k = int(request_data.get("k", 10))
        index_dir = request_data.get("index_dir", "/data/frame_index")

        if not query:
            raise HTTPException(status_code=400, detail="query required")

        # Lazy-load embedder + index
        try:
            from clip_embedder import get_clip_embedder
            from clip_index import FrameIndex
        except ImportError:
            raise HTTPException(
                status_code=501,
                detail="CLIP embedder not available")

        clip = get_clip_embedder()
        if not clip.available:
            raise HTTPException(
                status_code=503,
                detail="No CLIP backend available")

        t0 = _time.time()
        idx = FrameIndex(index_dir)
        results = idx.search(query, k=k, clip_embedder=clip)
        elapsed = (_time.time() - t0) * 1000

        return JSONResponse(content={
            "query": query,
            "total_in_index": len(idx),
            "results": results,
            "query_ms": round(elapsed, 1),
        })

    @app.post("/search/build")
    async def build_search_index(request_data: Dict):
        """Build a CLIP embedding index from a directory of frames.

        Processes all PNG frames, embeds them with CLIP, and persists
        the index for later search.

        Request body:
          {"frames_dir": "/data/frames", "index_dir": "/data/frame_index",
           "max_frames": 10000, "metadata": {"workflow": "demo-1"}}

        Returns:
          {"total_frames": 520, "build_time_s": 6.2,
           "embeddings_per_second": 83}
        """
        import time as _time

        frames_dir = request_data.get("frames_dir", "")
        index_dir = request_data.get("index_dir", "/data/frame_index")
        max_frames = int(request_data.get("max_frames", 10000))
        base_metadata = request_data.get("metadata", {})

        if not frames_dir or not os.path.isdir(frames_dir):
            raise HTTPException(status_code=400,
                                detail="frames_dir required and must exist")

        try:
            from clip_embedder import get_clip_embedder
            from clip_index import FrameIndex
        except ImportError:
            raise HTTPException(
                status_code=501,
                detail="CLIP embedder not available")

        clip = get_clip_embedder()
        if not clip.available:
            raise HTTPException(
                status_code=503,
                detail="No CLIP backend available")

        # Collect frame files
        frame_files = sorted([
            f for f in os.listdir(frames_dir)
            if f.endswith(('.png', '.PNG'))
        ])[:max_frames]

        if not frame_files:
            raise HTTPException(status_code=400,
                                detail=f"No PNG frames in {frames_dir}")

        # Also load manifest if present
        manifest_path = os.path.join(frames_dir, "manifest.json")
        manifest = {}
        if os.path.exists(manifest_path):
            try:
                with open(manifest_path) as f:
                    manifest = json.load(f)
            except Exception:
                pass

        # Embed frames in batches for efficiency
        idx = FrameIndex(index_dir)
        batch_size = 32
        total = 0
        t0 = _time.time()

        for batch_start in range(0, len(frame_files), batch_size):
            batch_files = frame_files[batch_start:batch_start + batch_size]
            batch_imgs = []
            batch_meta = []

            for fname in batch_files:
                fpath = os.path.join(frames_dir, fname)
                img = cv2.imread(fpath)
                if img is None:
                    continue
                batch_imgs.append(img)
                # Merge base metadata with per-frame info
                meta = dict(base_metadata)
                meta["filename"] = fname
                batch_meta.append(meta)

            if not batch_imgs:
                continue

            embeddings = clip.embed_batch(batch_imgs)
            idx.add_batch(
                [os.path.join(frames_dir, f) for f in batch_files[:len(batch_imgs)]],
                embeddings,
                batch_meta,
            )
            total += len(batch_imgs)

            if total % 500 == 0:
                print(f"[search/build] {total}/{len(frame_files)} frames indexed",
                      file=sys.stderr)

        idx.save()
        elapsed = _time.time() - t0

        print(f"[search/build] Indexed {total} frames in {elapsed:.1f}s "
              f"({total/elapsed:.0f} fps)", file=sys.stderr)

        return JSONResponse(content={
            "total_frames": total,
            "index_dir": index_dir,
            "build_time_s": round(elapsed, 2),
            "embeddings_per_second": round(total / max(elapsed, 0.001), 0),
            "stats": idx.stats(),
        })

    @app.post("/benchmark")
    async def benchmark(request_data: Dict):
        """Run multi-engine benchmark with statistical rigor.

        Request body:
          {"frames_dir": "/bench_frames",
           "engines": [{"ui_detector":"yolo", "ocr_backend":"tesseract"}, ...],
           "warmup_frames": 3, "iterations": 10, "confidence": 0.95}

        Returns full benchmark JSON with per-frame timing, CI95, and accuracy
        metrics if a manifest.json is present in the frames directory.
        """
        frames_dir = request_data.get("frames_dir", "")
        if not frames_dir or not os.path.isdir(frames_dir):
            raise HTTPException(status_code=400, detail="frames_dir required and must exist")

        try:
            from benchmark_runner import run_benchmark
        except ImportError:
            raise HTTPException(status_code=500,
                                detail="benchmark_runner module not found")

        engines = request_data.get("engines", [
            {"ui_detector": "contour", "ocr_backend": "tesseract"},
            {"ui_detector": "yolo", "ocr_backend": "tesseract"},
        ])
        warmup = int(request_data.get("warmup_frames", 3))
        iterations = int(request_data.get("iterations", 10))
        confidence = float(request_data.get("confidence", 0.95))
        max_frames = request_data.get("max_frames")

        result = run_benchmark(
            frames_dir=frames_dir,
            engines=engines,
            warmup_frames=warmup,
            iterations=iterations,
            confidence=confidence,
            max_frames=int(max_frames) if max_frames else None,
        )

        return JSONResponse(content=result)

    return app


# ── CLI Mode ─────────────────────────────────────────────────────────────────

def cli_single(image_path: str):
    img = cv2.imread(image_path)
    if img is None:
        print(f"ERROR: Cannot read {image_path}", file=sys.stderr)
        sys.exit(1)
    result = analyze_image(img)
    print(json.dumps(result, indent=2))


def cli_batch(video_path: str, output_dir: str = "", frame_interval: float = 1.0):
    """Run cv-test-runner.py logic directly."""
    if not os.path.exists(video_path):
        print(f"ERROR: Video not found: {video_path}", file=sys.stderr)
        sys.exit(1)

    # Use the existing cv-test-runner.py for full batch processing
    script_dir = Path(__file__).resolve().parent
    runner = script_dir / "cv-test-runner.py"
    if runner.exists():
        cmd = [sys.executable, str(runner), "--video", video_path,
               "--frame-interval", str(frame_interval), "--mode", "built-in"]
        if output_dir:
            cmd.extend(["--output", output_dir])
        subprocess.run(cmd)
    else:
        print(f"ERROR: cv-test-runner.py not found at {runner}", file=sys.stderr)
        sys.exit(1)


def serve(host: str = "0.0.0.0", port: int = 8001):
    if not HAS_FASTAPI:
        print("ERROR: FastAPI/uvicorn not installed. Use CLI mode: --cli", file=sys.stderr)
        sys.exit(1)
    app = create_app()
    detector = get_ui_detector()
    ocr = get_ocr_engine()

    print(f"WineBot CV Sidecar starting on {host}:{port}")
    print(f"  UI Detector: {detector.name} ({'available' if detector.available else 'UNAVAILABLE'}"
          f"{', GPU' if detector.uses_gpu else ', CPU'})")
    print(f"  OCR Engine:  {ocr.name} ({'available' if ocr.available else 'UNAVAILABLE'})")

    # Show all available backends
    all_detectors = available_detectors()
    all_ocr = available_backends()
    print(f"  Detectors available: {', '.join(k for k,v in all_detectors.items() if v)}")
    print(f"  OCR backends available: {', '.join(k for k,v in all_ocr.items() if v)}")
    print(f"  Switch via: UI_DETECTOR=<name> OCR_BACKEND=<name>")

    # Show VLM status
    vlm_provider = os.environ.get("VLM_PROVIDER", "").lower()
    if vlm_provider == "ollama":
        ohost = os.environ.get("OLLAMA_HOST", "localhost:11434")
        omodel = os.environ.get("OLLAMA_VLM_MODEL", "qwen3.5:35b")
        print(f"  VLM Provider: ollama ({omodel} @ {ohost})")
        try:
            from vlm_ollama import get_ollama_vlm
            o = get_ollama_vlm()
            print(f"  VLM Status: {'connected' if (o and o.available) else 'unreachable'}")
        except ImportError:
            print(f"  VLM Status: module unavailable")
    else:
        print(f"  VLM Provider: local (set VLM_PROVIDER=ollama for remote)")

    # Show model catalog summary
    if _model_registry:
        reg = _model_registry
        active = reg.get_active()
        fingerprinted = sum(
            1 for e in reg.entries.values()
            if e.deployment and e.deployment.content_sha256
        )
        print(f"  Model Registry: {len(reg.entries)} total, {len(active)} active, "
              f"{fingerprinted} fingerprinted")
        # Summarize by stage
        stages = {}
        for e in reg.entries.values():
            s = e.pipeline_stage
            stages[s] = stages.get(s, 0) + 1
        print(f"  Model stages: " + ", ".join(
            f"stage {s}: {c}" for s, c in sorted(stages.items())))

    uvicorn.run(app, host=host, port=port, log_level="info")


# ── Main ─────────────────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(description="WineBot CV Sidecar")
    parser.add_argument("--serve", action="store_true", help="Start API server")
    parser.add_argument("--host", default="0.0.0.0")
    parser.add_argument("--port", type=int, default=8001)
    parser.add_argument("--cli", action="store_true", help="CLI mode")
    parser.add_argument("--image", help="Single image path (CLI mode)")
    parser.add_argument("--video", help="Video path for batch (CLI mode)")
    parser.add_argument("--output", default="", help="Output dir (CLI batch)")
    parser.add_argument("--frame-interval", type=float, default=1.0)

    args = parser.parse_args()

    if args.cli:
        if args.image:
            cli_single(args.image)
        elif args.video:
            cli_batch(args.video, args.output, args.frame_interval)
        else:
            print("CLI mode requires --image or --video", file=sys.stderr)
            sys.exit(1)
    else:
        serve(args.host, args.port)


if __name__ == "__main__":
    main()
