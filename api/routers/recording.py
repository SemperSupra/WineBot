from fastapi import APIRouter, HTTPException, Body
from typing import Optional, Dict, List
import asyncio
import os
import subprocess
import time
import uuid
import json
from api.core.models import (
    RecordingStartModel,
    RecorderState,
    RecordingActionResponse,
    RecordingStartResponse,
)
from api.core.recorder import (
    recorder_lock,
    recorder_running,
    recorder_state,
    write_recorder_state,
)
from api.core.telemetry import emit_operation_timing
from api.core import monitor as recording_monitor
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
from api.utils.config import config
from api.core.operations import (
    create_operation,
    heartbeat_operation,
    complete_operation,
    fail_operation,
)

router = APIRouter(prefix="/recording", tags=["recording"])

DEFAULT_SESSION_ROOT = "/artifacts/sessions"


def set_manual_pause_lock(session_dir: str, locked: bool) -> None:
    """Compatibility wrapper: no-op if monitor helper is unavailable."""
    maybe_fn = getattr(recording_monitor, "set_manual_pause_lock", None)
    if callable(maybe_fn):
        maybe_fn(session_dir, locked)


def _int_env(name: str, default: int, minimum: int = 0, maximum: Optional[int] = None) -> int:
    raw = os.getenv(name, "").strip()
    try:
        value = int(raw) if raw else default
    except Exception:
        value = default
    value = max(minimum, value)
    if maximum is not None:
        value = min(maximum, value)
    return value


def _action_response(
    *,
    action: str,
    status: str,
    session_dir: Optional[str] = None,
    operation_id: Optional[str] = None,
    converged: bool = True,
    warning: Optional[str] = None,
) -> Dict[str, object]:
    """Return a normalized action payload while preserving legacy status values."""
    payload: Dict[str, object] = {
        "action": action,
        "status": status,
        "result": "converged" if converged else "accepted",
        "converged": converged,
    }
    if session_dir:
        payload["session_dir"] = session_dir
    if operation_id:
        payload["operation_id"] = operation_id
    if warning:
        payload["warning"] = warning
    return payload


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


@router.post("/start", response_model=RecordingStartResponse, response_model_exclude_none=True)
async def start_recording(data: Optional[RecordingStartModel] = Body(default=None)):
    """Start a recording session."""
    op_started = time.perf_counter()
    if os.getenv("WINEBOT_RECORD", "0") != "1":
        raise HTTPException(
            status_code=400, detail="Recording is disabled by configuration."
        )

    session_dir_hint = read_session_dir()
    operation_id = await create_operation(
        "recording_start", session_dir=session_dir_hint, metadata={}
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
                result = await run_async_command(
                    cmd, timeout=config.WINEBOT_TIMEOUT_RECORDING_CONTROL_SECONDS
                )
                if not result["ok"]:
                    await fail_operation(operation_id, error=result.get("stderr") or "resume failed")
                    raise HTTPException(
                        status_code=500,
                        detail=(result["stderr"] or "Failed to resume recorder"),
                    )
                payload = _action_response(
                    action="start",
                    status="resumed",
                    session_dir=current_session,
                    operation_id=operation_id,
                    converged=True,
                )
                set_manual_pause_lock(current_session, False)
                await complete_operation(operation_id, result=payload)
                return payload
            payload = _action_response(
                action="start",
                status="already_recording",
                session_dir=current_session,
                operation_id=operation_id,
                converged=True,
            )
            await complete_operation(operation_id, result=payload)
            return payload

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
        await heartbeat_operation(
            operation_id,
            phase="spawn",
            message="starting recorder process",
            progress=40,
        )
        proc = subprocess.Popen(cmd)
        try:
            manage_process(proc)
        except ProcessCapacityError as exc:
            await fail_operation(operation_id, error=str(exc))
            raise HTTPException(status_code=503, detail=str(exc))

        pid = None
        pid_file = os.path.join(session_dir, "recorder.pid")
        for _ in range(10):
            pid = read_pid(pid_file)
            if pid:
                break
            await asyncio.sleep(0.1)

        result = _action_response(
            action="start",
            status="started",
            session_dir=session_dir,
            operation_id=operation_id,
            converged=True,
        )
        result.update(
            {
            "session_id": session_id,
            "segment": segment,
            "output_file": output_file,
            "events_file": events_file,
            "display": display,
            "resolution": resolution,
            "fps": fps,
            "recorder_pid": pid,
            }
        )
        set_manual_pause_lock(session_dir, False)
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
        await complete_operation(operation_id, result=result)
        return result


@router.post("/stop", response_model=RecordingActionResponse, response_model_exclude_none=True)
async def stop_recording_endpoint():
    """Stop the active recording session."""
    op_started = time.perf_counter()
    if os.getenv("WINEBOT_RECORD", "0") != "1":
        raise HTTPException(
            status_code=400, detail="Recording is disabled by configuration."
        )

    operation_id = await create_operation(
        "recording_stop", session_dir=read_session_dir(), metadata={}
    )
    async with recorder_lock:
        session_dir = read_session_dir()
        if not session_dir:
            payload = _action_response(
                action="stop",
                status="already_stopped",
                operation_id=operation_id,
                converged=True,
            )
            await complete_operation(operation_id, result=payload)
            return payload
        if not recorder_running(session_dir):
            write_recorder_state(session_dir, RecorderState.IDLE.value)
            result = _action_response(
                action="stop",
                status="already_stopped",
                session_dir=session_dir,
                operation_id=operation_id,
                converged=True,
            )
            set_manual_pause_lock(session_dir, False)
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
            await complete_operation(operation_id, result=result)
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
        result = await run_async_command(
            cmd, timeout=config.WINEBOT_TIMEOUT_RECORDING_STOP_SECONDS
        )
        if not result["ok"]:
            await fail_operation(
                operation_id, error=(result.get("stderr") or "Failed to stop recorder")
            )
            raise HTTPException(
                status_code=500, detail=(result["stderr"] or "Failed to stop recorder")
            )

        # Keep API stop responsive; finalization can continue asynchronously.
        sync_wait_sec = _int_env(
            "WINEBOT_RECORDING_STOP_SYNC_WAIT_SECONDS",
            default=3,
            minimum=1,
            maximum=max(1, int(config.WINEBOT_TIMEOUT_RECORDING_STOP_SECONDS)),
        )
        settle_iters = max(1, int(sync_wait_sec * 5))
        stopped = False
        for _ in range(settle_iters):
            if not recorder_running(session_dir):
                write_recorder_state(session_dir, RecorderState.IDLE.value)
                stopped = True
                break
            await asyncio.sleep(0.2)
        if not stopped:
            result = _action_response(
                action="stop",
                status="stop_requested",
                session_dir=session_dir,
                operation_id=operation_id,
                converged=False,
                warning="Recorder stop requested; finalization still in progress.",
            )
            await complete_operation(operation_id, result=result)
            return result

        result = _action_response(
            action="stop",
            status="stopped",
            session_dir=session_dir,
            operation_id=operation_id,
            converged=True,
        )
        set_manual_pause_lock(session_dir, False)
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
        await complete_operation(operation_id, result=result)
        return result


@router.post("/pause", response_model=RecordingActionResponse, response_model_exclude_none=True)
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
            return _action_response(
                action="pause",
                status=RecorderState.IDLE.value,
                converged=True,
            )
        if not recorder_running(session_dir):
            result = _action_response(
                action="pause",
                status="already_paused",
                session_dir=session_dir,
                converged=True,
            )
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
            result = _action_response(
                action="pause",
                status="already_paused",
                session_dir=session_dir,
                converged=True,
            )
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
        result = await run_async_command(
            cmd, timeout=config.WINEBOT_TIMEOUT_RECORDING_CONTROL_SECONDS
        )
        if not result["ok"]:
            # If pause command races with recorder state transition, treat desired
            # target as converging instead of surfacing a hard API failure.
            current_state = recorder_state(session_dir)
            if current_state == RecorderState.PAUSED.value or not recorder_running(session_dir):
                result = {"ok": True, "stdout": "", "stderr": ""}
            else:
                retry = await run_async_command(
                    cmd, timeout=config.WINEBOT_TIMEOUT_RECORDING_CONTROL_SECONDS
                )
                if retry.get("ok"):
                    result = {"ok": True, "stdout": "", "stderr": ""}
                else:
                    raise HTTPException(
                        status_code=500,
                        detail=(retry.get("stderr") or result.get("stderr") or "Failed to pause recorder"),
                    )
        settle_iters = max(1, int(config.WINEBOT_RECORDING_STATE_SETTLE_SECONDS * 5))
        paused = False
        for attempt in range(2):
            for _ in range(settle_iters):
                if recorder_state(session_dir) == RecorderState.PAUSED.value:
                    paused = True
                    break
                await asyncio.sleep(0.2)
            if paused:
                break
            # Retry a single time if pause signal was acknowledged but state lagged.
            retry = await run_async_command(
                cmd, timeout=config.WINEBOT_TIMEOUT_RECORDING_CONTROL_SECONDS
            )
            if not retry.get("ok"):
                break
        result = _action_response(
            action="pause",
            status="paused",
            session_dir=session_dir,
            converged=True,
        )
        set_manual_pause_lock(session_dir, True)
        if not paused:
            raise HTTPException(
                status_code=504,
                detail="Recorder did not enter paused state before timeout",
            )
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


@router.post("/resume", response_model=RecordingActionResponse, response_model_exclude_none=True)
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
            return _action_response(
                action="resume",
                status=RecorderState.IDLE.value,
                converged=True,
            )
        if not recorder_running(session_dir):
            result = _action_response(
                action="resume",
                status=RecorderState.IDLE.value,
                session_dir=session_dir,
                converged=True,
            )
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
            result = _action_response(
                action="resume",
                status="already_recording",
                session_dir=session_dir,
                converged=True,
            )
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
        result = await run_async_command(
            cmd, timeout=config.WINEBOT_TIMEOUT_RECORDING_CONTROL_SECONDS
        )
        if not result["ok"]:
            # Handle race where resume target is already reached.
            current_state = recorder_state(session_dir)
            if current_state != RecorderState.PAUSED.value and recorder_running(session_dir):
                result = {"ok": True, "stdout": "", "stderr": ""}
            else:
                raise HTTPException(
                    status_code=500,
                    detail=(result["stderr"] or "Failed to resume recorder"),
                )
        settle_iters = max(1, int(config.WINEBOT_RECORDING_STATE_SETTLE_SECONDS * 5))
        resumed = False
        for attempt in range(2):
            for _ in range(settle_iters):
                current_state = recorder_state(session_dir)
                if current_state != RecorderState.PAUSED.value and recorder_running(session_dir):
                    resumed = True
                    break
                await asyncio.sleep(0.2)
            if resumed:
                break
            retry = await run_async_command(
                cmd, timeout=config.WINEBOT_TIMEOUT_RECORDING_CONTROL_SECONDS
            )
            if not retry.get("ok"):
                break
        result = _action_response(
            action="resume",
            status="resumed",
            session_dir=session_dir,
            converged=True,
        )
        set_manual_pause_lock(session_dir, False)
        if not resumed:
            result["status"] = "resume_requested"
            result["result"] = "accepted"
            result["converged"] = False
            result["warning"] = "Resume requested; recorder state convergence pending."
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
