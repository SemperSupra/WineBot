from fastapi import APIRouter, HTTPException, Body
from typing import Optional, Dict, List
import asyncio
import os
import subprocess
import time
import uuid
import json
from api.core.models import RecordingStartModel, RecorderState
from api.core.recorder import (
    recorder_lock,
    recorder_running,
    recorder_state,
    write_recorder_state,
)
from api.core.telemetry import emit_operation_timing
from api.utils.files import (
    read_session_dir,
    resolve_session_dir,
    ensure_session_subdirs,
    write_session_dir,
    write_session_manifest,
    write_session_mode,
    write_session_control_mode,
    write_session_state,
    read_session_mode,
    read_session_state,
    next_segment_index,
    read_pid,
    performance_metrics_log_path,
)
from api.utils.process import manage_process, run_async_command, ProcessCapacityError

router = APIRouter(prefix="/recording", tags=["recording"])

DEFAULT_SESSION_ROOT = "/artifacts/sessions"


def parse_resolution(screen: str) -> str:
    if not screen:
        return "1920x1080"
    parts = screen.split("x")
    if len(parts) >= 2:
        return f"{parts[0]}x{parts[1]}"
    return screen


def generate_session_id(label: Optional[str]) -> str:
    ts = int(time.time())
    date_prefix = time.strftime("%Y-%m-%d", time.gmtime(ts))
    rand = uuid.uuid4().hex[:6]
    session_id = f"session-{date_prefix}-{ts}-{rand}"
    if label:
        import re

        safe = re.sub(r"[^a-zA-Z0-9._-]+", "-", label).strip("-")
        if safe:
            session_id = f"{session_id}-{safe}"
    return session_id


@router.post("/start")
async def start_recording(data: Optional[RecordingStartModel] = Body(default=None)):
    """Start a recording session."""
    op_started = time.perf_counter()
    if os.getenv("WINEBOT_RECORD", "0") != "1":
        raise HTTPException(
            status_code=400, detail="Recording is disabled by configuration."
        )

    async with recorder_lock:
        if data is None:
            data = RecordingStartModel()
        current_session = read_session_dir()
        
        if current_session and recorder_running(current_session):
            if recorder_state(current_session) == RecorderState.PAUSED.value:
                cmd = [
                    "python3",
                    "-m",
                    "automation.recorder",
                    "resume",
                    "--session-dir",
                    current_session,
                ]
                result = await run_async_command(cmd)
                if not result["ok"]:
                    raise HTTPException(
                        status_code=500,
                        detail=(result["stderr"] or "Failed to resume recorder"),
                    )
                return {"status": "resumed", "session_dir": current_session}
            return {"status": "already_recording", "session_dir": current_session}

        session_dir = None
        if not data.new_session and current_session and os.path.isdir(current_session):
            session_json = os.path.join(current_session, "session.json")
            session_mode = read_session_mode(current_session)
            session_state = read_session_state(current_session)
            if (
                os.path.exists(session_json)
                and not (session_mode == "oneshot" and session_state == "completed")
            ):
                session_dir = current_session

        if session_dir is None:
            session_root = data.session_root or os.getenv(
                "WINEBOT_SESSION_ROOT"
            ) or DEFAULT_SESSION_ROOT
            os.makedirs(str(session_root), exist_ok=True)
            session_id = generate_session_id(data.session_label)
            session_dir = os.path.join(str(session_root), session_id)
            os.makedirs(session_dir, exist_ok=True)
            write_session_dir(session_dir)
            write_session_manifest(session_dir, session_id)
            write_session_mode(session_dir, os.getenv("WINEBOT_SESSION_MODE", "persistent"))
            write_session_control_mode(
                session_dir, os.getenv("WINEBOT_SESSION_CONTROL_MODE", "hybrid")
            )
            ensure_session_subdirs(session_dir)
        else:
            session_id = os.path.basename(session_dir)
            ensure_session_subdirs(session_dir)
        write_session_state(session_dir, "active")

        assert isinstance(session_dir, str)
        display = data.display or os.getenv("DISPLAY", ":99")
        screen = data.resolution or os.getenv("SCREEN", "1920x1080")
        resolution = parse_resolution(str(screen))
        fps = data.fps or 30
        segment = next_segment_index(session_dir)
        segment_suffix = f"{segment:03d}"
        output_file = os.path.join(session_dir, f"video_{segment_suffix}.mkv")
        events_file = os.path.join(session_dir, f"events_{segment_suffix}.jsonl")

        cmd = [
            "python3",
            "-m",
            "automation.recorder",
            "start",
            "--session-dir",
            str(session_dir), # type: ignore
            "--display",
            str(display),
            "--resolution",
            str(resolution),
            "--fps",
            str(fps),
            "--segment",
            str(segment),
        ]
        proc = subprocess.Popen(cmd)
        try:
            manage_process(proc)
        except ProcessCapacityError as exc:
            raise HTTPException(status_code=503, detail=str(exc))

        pid = None
        pid_file = os.path.join(session_dir, "recorder.pid")
        for _ in range(10):
            pid = read_pid(pid_file)
            if pid:
                break
            await asyncio.sleep(0.1)

        result = {
            "status": "started",
            "session_id": session_id,
            "session_dir": session_dir,
            "segment": segment,
            "output_file": output_file,
            "events_file": events_file,
            "display": display,
            "resolution": resolution,
            "fps": fps,
            "recorder_pid": pid,
        }
        emit_operation_timing(
            session_dir,
            feature="recording",
            capability="start_stop",
            feature_set="recording_and_artifacts",
            operation="api_start",
            duration_ms=(time.perf_counter() - op_started) * 1000.0,
            result="ok",
            source="api",
            metric_name="recording.api_start.latency",
            tags={"status": "started", "segment": segment},
        )
        return result


@router.post("/stop")
async def stop_recording_endpoint():
    """Stop the active recording session."""
    op_started = time.perf_counter()
    if os.getenv("WINEBOT_RECORD", "0") != "1":
        raise HTTPException(
            status_code=400, detail="Recording is disabled by configuration."
        )

    async with recorder_lock:
        session_dir = read_session_dir()
        if not session_dir:
            return {"status": "already_stopped"}
        if not recorder_running(session_dir):
            write_recorder_state(session_dir, RecorderState.IDLE.value)
            result = {"status": "already_stopped", "session_dir": session_dir}
            emit_operation_timing(
                session_dir,
                feature="recording",
                capability="start_stop",
                feature_set="recording_and_artifacts",
                operation="api_stop",
                duration_ms=(time.perf_counter() - op_started) * 1000.0,
                result="ok",
                source="api",
                metric_name="recording.api_stop.latency",
                tags={"status": "already_stopped"},
            )
            return result

        write_recorder_state(session_dir, RecorderState.STOPPING.value)
        cmd = [
            "python3",
            "-m",
            "automation.recorder",
            "stop",
            "--session-dir",
            session_dir,
        ]
        result = await run_async_command(cmd)
        if not result["ok"]:
            raise HTTPException(
                status_code=500, detail=(result["stderr"] or "Failed to stop recorder")
            )

        for _ in range(10):
            if not recorder_running(session_dir):
                write_recorder_state(session_dir, RecorderState.IDLE.value)
                break
            await asyncio.sleep(0.2)

        result = {"status": "stopped", "session_dir": session_dir}
        emit_operation_timing(
            session_dir,
            feature="recording",
            capability="start_stop",
            feature_set="recording_and_artifacts",
            operation="api_stop",
            duration_ms=(time.perf_counter() - op_started) * 1000.0,
            result="ok",
            source="api",
            metric_name="recording.api_stop.latency",
            tags={"status": "stopped"},
        )
        return result


@router.post("/pause")
async def pause_recording():
    """Pause the active recording session."""
    op_started = time.perf_counter()
    if os.getenv("WINEBOT_RECORD", "0") != "1":
        raise HTTPException(
            status_code=400, detail="Recording is disabled by configuration."
        )

    async with recorder_lock:
        session_dir = read_session_dir()
        if not session_dir:
            return {"status": RecorderState.IDLE.value}
        if not recorder_running(session_dir):
            result = {"status": "already_paused", "session_dir": session_dir}
            emit_operation_timing(
                session_dir,
                feature="recording",
                capability="pause_resume",
                feature_set="recording_and_artifacts",
                operation="api_pause",
                duration_ms=(time.perf_counter() - op_started) * 1000.0,
                result="ok",
                source="api",
                metric_name="recording.api_pause.latency",
                tags={"status": "already_paused", "reason": "not_running"},
            )
            return result
        if recorder_state(session_dir) == RecorderState.PAUSED.value:
            result = {"status": "already_paused", "session_dir": session_dir}
            emit_operation_timing(
                session_dir,
                feature="recording",
                capability="pause_resume",
                feature_set="recording_and_artifacts",
                operation="api_pause",
                duration_ms=(time.perf_counter() - op_started) * 1000.0,
                result="ok",
                source="api",
                metric_name="recording.api_pause.latency",
                tags={"status": "already_paused", "reason": "already_paused"},
            )
            return result
        cmd = [
            "python3",
            "-m",
            "automation.recorder",
            "pause",
            "--session-dir",
            session_dir,
        ]
        result = await run_async_command(cmd)
        if not result["ok"]:
            raise HTTPException(
                status_code=500, detail=(result["stderr"] or "Failed to pause recorder")
            )
        result = {"status": "paused", "session_dir": session_dir}
        emit_operation_timing(
            session_dir,
            feature="recording",
            capability="pause_resume",
            feature_set="recording_and_artifacts",
            operation="api_pause",
            duration_ms=(time.perf_counter() - op_started) * 1000.0,
            result="ok",
            source="api",
            metric_name="recording.api_pause.latency",
            tags={"status": "paused"},
        )
        return result


@router.post("/resume")
async def resume_recording():
    """Resume the active recording session."""
    op_started = time.perf_counter()
    if os.getenv("WINEBOT_RECORD", "0") != "1":
        raise HTTPException(
            status_code=400, detail="Recording is disabled by configuration."
        )

    async with recorder_lock:
        session_dir = read_session_dir()
        if not session_dir:
            return {"status": RecorderState.IDLE.value}
        if not recorder_running(session_dir):
            result = {"status": RecorderState.IDLE.value, "session_dir": session_dir}
            emit_operation_timing(
                session_dir,
                feature="recording",
                capability="pause_resume",
                feature_set="recording_and_artifacts",
                operation="api_resume",
                duration_ms=(time.perf_counter() - op_started) * 1000.0,
                result="ok",
                source="api",
                metric_name="recording.api_resume.latency",
                tags={"status": RecorderState.IDLE.value, "reason": "not_running"},
            )
            return result
        if recorder_state(session_dir) != RecorderState.PAUSED.value:
            result = {"status": "already_recording", "session_dir": session_dir}
            emit_operation_timing(
                session_dir,
                feature="recording",
                capability="pause_resume",
                feature_set="recording_and_artifacts",
                operation="api_resume",
                duration_ms=(time.perf_counter() - op_started) * 1000.0,
                result="ok",
                source="api",
                metric_name="recording.api_resume.latency",
                tags={"status": "already_recording"},
            )
            return result
        cmd = [
            "python3",
            "-m",
            "automation.recorder",
            "resume",
            "--session-dir",
            session_dir,
        ]
        result = await run_async_command(cmd)
        if not result["ok"]:
            raise HTTPException(
                status_code=500,
                detail=(result["stderr"] or "Failed to resume recorder"),
            )
        result = {"status": "resumed", "session_dir": session_dir}
        emit_operation_timing(
            session_dir,
            feature="recording",
            capability="pause_resume",
            feature_set="recording_and_artifacts",
            operation="api_resume",
            duration_ms=(time.perf_counter() - op_started) * 1000.0,
            result="ok",
            source="api",
            metric_name="recording.api_resume.latency",
            tags={"status": "resumed"},
        )
        return result


@router.get("/perf/summary")
def recording_performance_summary(
    session_id: Optional[str] = None,
    session_dir: Optional[str] = None,
    session_root: Optional[str] = None,
):
    target_dir: Optional[str] = None
    if session_id or session_dir:
        target_dir = resolve_session_dir(session_id, session_dir, session_root)
        if not os.path.isdir(target_dir):
            raise HTTPException(status_code=404, detail="Session directory not found")
    else:
        target_dir = read_session_dir()
    if not target_dir:
        return {"session_dir": None, "metrics": {}}

    log_path = performance_metrics_log_path(target_dir)
    if not os.path.exists(log_path):
        return {"session_dir": target_dir, "log_path": log_path, "metrics": {}}

    def summarize(values):
        vals = sorted(values)
        n = len(vals)
        if n == 0:
            return {}

        def pct(p):
            idx = int(round((n - 1) * p))
            return vals[idx]

        return {
            "count": n,
            "min_ms": round(vals[0], 3),
            "mean_ms": round(sum(vals) / n, 3),
            "p50_ms": round(pct(0.50), 3),
            "p90_ms": round(pct(0.90), 3),
            "p95_ms": round(pct(0.95), 3),
            "p99_ms": round(pct(0.99), 3),
            "max_ms": round(vals[-1], 3),
        }

    metrics: Dict[str, List[float]] = {}
    line_count = 0
    parse_errors = 0
    try:
        with open(log_path, "r", encoding="utf-8") as handle:
            for raw in handle:
                line_count += 1
                line = raw.strip()
                if not line:
                    continue
                try:
                    payload = json.loads(line)
                except Exception:
                    parse_errors += 1
                    continue
                if payload.get("event") != "performance_metric":
                    continue
                metric = str(payload.get("metric", "")).strip()
                if not metric:
                    continue
                value = payload.get("value_ms")
                try:
                    value_f = float(value)
                except Exception:
                    continue
                metrics.setdefault(metric, []).append(value_f)
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"Failed to read metrics: {exc}")

    summary = {name: summarize(values) for name, values in metrics.items() if values}
    return {
        "session_dir": target_dir,
        "log_path": log_path,
        "lines_read": line_count,
        "parse_errors": parse_errors,
        "metrics": summary,
    }
