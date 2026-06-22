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

# ── FastAPI (imported lazily in serve() to allow CLI-only usage) ─────────────

try:
    from fastapi import FastAPI, HTTPException
    from fastapi.responses import JSONResponse
    import uvicorn
    HAS_FASTAPI = True
except ImportError:
    HAS_FASTAPI = False


def analyze_image(img: np.ndarray) -> Dict:
    """Full analysis of a single image using configured engines. Returns structured JSON."""
    h, w = img.shape[:2]

    detector = get_ui_detector()
    ui_elements = detector.detect(img)
    ui_state = detector.classify_ui_state(img, ui_elements)

    ocr = get_ocr_engine()
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

        return {
            "status": "healthy",
            "opencv": cv2.__version__,
            "active": {
                "ui_detector": active_detector,
                "ocr_engine": active_ocr,
            },
            "available_detectors": detectors,
            "available_ocr_backends": ocr_backends,
            "env": {
                "UI_DETECTOR": os.environ.get("UI_DETECTOR", "contour"),
                "OCR_BACKEND": os.environ.get("OCR_BACKEND", "tesseract"),
            },
        }

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
        result = analyze_image(img)
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
