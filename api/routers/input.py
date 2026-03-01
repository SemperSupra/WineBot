from fastapi import APIRouter, HTTPException, Body
from typing import Dict, Any, Optional
import subprocess
import os
import time
import shutil
import datetime
import uuid
import json
import signal
import threading
from api.core.models import (
    ClickModel,
    InputTraceStartModel,
    InputTraceStopModel,
    InputTraceX11CoreStartModel,
    InputTraceX11CoreStopModel,
    InputTraceClientStartModel,
    InputTraceClientStopModel,
    InputTraceWindowsStartModel,
    InputTraceWindowsStopModel,
)
from api.core.broker import broker
from api.core.telemetry import emit_operation_timing
from api.utils.config import config
from api.utils.files import (
    append_input_event,
    append_trace_event,
    read_session_dir,
    session_id_from_dir,
    resolve_session_dir,
    input_trace_pid,
    input_trace_running,
    input_trace_state,
    input_trace_log_path,
    input_trace_x11_core_pid,
    input_trace_x11_core_running,
    input_trace_x11_core_state,
    input_trace_x11_core_log_path,
    input_trace_x11_core_pid_path,
    write_input_trace_x11_core_state,
    input_trace_client_enabled,
    input_trace_client_log_path,
    write_input_trace_client_state,
    input_trace_windows_pid,
    input_trace_windows_running,
    input_trace_windows_state,
    input_trace_windows_backend,
    input_trace_windows_log_path,
    input_trace_windows_pid_path,
    write_input_trace_windows_state,
    write_input_trace_windows_backend,
    input_trace_network_pid,
    input_trace_network_running,
    input_trace_network_state,
    input_trace_network_log_path,
    write_input_trace_network_state,
    append_lifecycle_event,
    to_wine_path,
)
from api.utils.process import (
    manage_process,
    ProcessCapacityError,
    pid_running,
    safe_command,
    run_async_command,
)


router = APIRouter(prefix="/input", tags=["input"])
input_trace_lock = threading.Lock()
input_trace_x11_core_lock = threading.Lock()
input_trace_windows_lock = threading.Lock()
input_trace_network_lock = threading.Lock()


def _require_active_session() -> str:
    session_dir = read_session_dir()
    if not session_dir or not os.path.isdir(session_dir):
        raise HTTPException(
            status_code=409,
            detail="No active session. Resume or create a session before input operations.",
        )
    return session_dir


@router.get("/events")
def input_events(
    limit: int = 200,
    since_epoch_ms: Optional[int] = None,
    source: Optional[str] = None,
    origin: Optional[str] = None,
    session_id: Optional[str] = None,
    session_dir: Optional[str] = None,
    session_root: Optional[str] = None,
):
    """Return recent input trace events."""
    if limit < 1:
        raise HTTPException(status_code=400, detail="limit must be >= 1")
    if limit > config.WINEBOT_MAX_EVENTS_QUERY:
        raise HTTPException(
            status_code=400,
            detail=f"limit must be <= {config.WINEBOT_MAX_EVENTS_QUERY}",
        )
    target_dir: Optional[str] = None
    if session_id or session_dir:
        target_dir = resolve_session_dir(session_id, session_dir, session_root)
        if not os.path.isdir(target_dir):
            raise HTTPException(status_code=404, detail="Session directory not found")
    else:
        target_dir = read_session_dir()
    if not target_dir:
        return {"events": []}

    if source == "client":
        path = input_trace_client_log_path(target_dir)
    elif source == "x11_core":
        path = input_trace_x11_core_log_path(target_dir)
    elif source == "windows":
        path = input_trace_windows_log_path(target_dir)
    elif source == "network":
        path = input_trace_network_log_path(target_dir)
    else:
        path = input_trace_log_path(target_dir)

    if not os.path.exists(path):
        return {"events": []}

    from api.utils.files import read_file_tail_lines
    raw_lines = read_file_tail_lines(path, limit=limit)
    events = []
    for line in raw_lines:
        try:
            event = json.loads(line)
        except json.JSONDecodeError:
            continue
        if since_epoch_ms is not None:
            try:
                if int(event.get("timestamp_epoch_ms", 0)) < since_epoch_ms:
                    continue
            except Exception:
                continue
        if origin is not None:
            if event.get("origin") != origin:
                continue
        events.append(event)
    
    return {"events": events, "log_path": path}


@router.post("/mouse/click")
async def click_at(data: ClickModel):
    """Click at coordinates (x, y)."""
    op_started = time.perf_counter()
    if not await broker.check_access():
        raise HTTPException(status_code=423, detail="Agent control denied by policy")

    await broker.report_agent_activity()

    # Resolve target window if needed
    target_win_id = data.window_id
    if not target_win_id and data.window_title:
        search_res = await run_async_command(
            ["xdotool", "search", "--name", data.window_title]
        )
        if search_res["ok"]:
            ids = search_res["stdout"].strip().split("\n")
            if ids:
                target_win_id = ids[0]

    # Validate coordinates against screen resolution if not relative
    if not data.relative:
        screen = os.getenv("SCREEN", "1280x720x24")
        try:
            res_part = screen.split("x")
            max_x = int(res_part[0])
            max_y = int(res_part[1])
        except (ValueError, IndexError):
            max_x, max_y = 1280, 720

        if data.x < 0 or data.x >= max_x or data.y < 0 or data.y >= max_y:
            raise HTTPException(
                status_code=400,
                detail=f"Coordinates ({data.x}, {data.y}) out of bounds for resolution {max_x}x{max_y}",
            )

    # Get window under cursor for validation (if not explicitly targeted)
    win_id = target_win_id or "unknown"
    win_title = data.window_title or "unknown"

    if not target_win_id:
        try:
            await run_async_command(["xdotool", "mousemove", str(data.x), str(data.y)])
            win_res = await run_async_command(["xdotool", "getmousereturnwindow"])
            if win_res["ok"]:
                win_id = win_res["stdout"].strip()
                title_res = await run_async_command(
                    ["xdotool", "getwindowname", win_id]
                )
                if title_res["ok"]:
                    win_title = title_res["stdout"].strip()
        except Exception:
            pass

    session_dir = _require_active_session()

    trace_id = uuid.uuid4().hex
    append_input_event(
        session_dir,
        {
            "event": "agent_click",
            "phase": "request",
            "origin": "agent",
            "source": "api",
            "tool": "api:/input/mouse/click",
            "x": data.x,
            "y": data.y,
            "button": data.button,
            "trace_id": trace_id,
            "via": "xdotool",
            "target_window_id": win_id,
            "target_window_title": win_title,
            "relative": data.relative,
        },
    )

    cmd = ["xdotool"]
    if data.relative and target_win_id:
        cmd.extend(
            ["mousemove", "--window", target_win_id, "--sync", str(data.x), str(data.y)]
        )
    else:
        cmd.extend(["mousemove", "--sync", str(data.x), str(data.y)])

    cmd.extend(["click", str(data.button)])

    result = await run_async_command(cmd)
    if not result.get("ok"):
        emit_operation_timing(
            session_dir,
            feature="input",
            capability="mouse_click",
            feature_set="control_input_automation",
            operation="api_click",
            duration_ms=(time.perf_counter() - op_started) * 1000.0,
            result="error",
            source="api",
            metric_name="input.api_click.latency",
            tags={"reason": "xdotool_failed"},
        )
        raise HTTPException(
            status_code=500, detail=f"xdotool failed: {result.get('stderr')}"
        )

    append_input_event(
        session_dir,
        {
            "event": "agent_click",
            "phase": "complete",
            "origin": "agent",
            "source": "api",
            "tool": "api:/input/mouse/click",
            "x": data.x,
            "y": data.y,
            "button": data.button,
            "trace_id": trace_id,
            "status": "clicked",
        },
    )

    # Log to Windows layer (Cross-layer consistency)
    payload = {
        "event": "mouse_down",
        "origin": "agent",
        "source": "windows",
        "x": data.x,
        "y": data.y,
        "button": data.button,
        "trace_id": trace_id,
        "timestamp_epoch_ms": int(time.time() * 1000),
    }
    append_trace_event(input_trace_windows_log_path(session_dir), payload)

    emit_operation_timing(
        session_dir,
        feature="input",
        capability="mouse_click",
        feature_set="control_input_automation",
        operation="api_click",
        duration_ms=(time.perf_counter() - op_started) * 1000.0,
        result="ok",
        source="api",
        metric_name="input.api_click.latency",
        tags={"relative": bool(data.relative)},
    )

    return {"status": "clicked", "x": data.x, "y": data.y, "trace_id": trace_id}


@router.get("/trace/status")
def input_trace_status(
    session_id: Optional[str] = None,
    session_dir: Optional[str] = None,
    session_root: Optional[str] = None,
):
    """Input trace status for the active or specified session."""
    op_started = time.perf_counter()
    target_dir: Optional[str] = None
    if session_id or session_dir:
        target_dir = resolve_session_dir(session_id, session_dir, session_root)
        if not os.path.isdir(target_dir):
            raise HTTPException(status_code=404, detail="Session directory not found")
    else:
        target_dir = read_session_dir()
    if not target_dir:
        return {"running": False, "state": None, "session_dir": None}
    assert isinstance(target_dir, str)
    pid = input_trace_pid(target_dir)
    payload = {
        "session_dir": target_dir,
        "pid": pid,
        "running": input_trace_running(target_dir),
        "state": input_trace_state(target_dir),
        "log_path": input_trace_log_path(target_dir),
    }
    emit_operation_timing(
        target_dir,
        feature="input",
        capability="trace_x11",
        feature_set="control_input_automation",
        operation="trace_status",
        duration_ms=(time.perf_counter() - op_started) * 1000.0,
        result="ok",
        source="api",
        metric_name="input.trace_status.latency",
    )
    return payload


@router.post("/trace/start")
def input_trace_start(data: Optional[InputTraceStartModel] = Body(default=None)):
    """Start the input tracing process for the active session."""
    op_started = time.perf_counter()
    if data is None:
        data = InputTraceStartModel()
    session_dir: Optional[str] = None
    if data.session_id or data.session_dir:
        session_dir = resolve_session_dir(
            data.session_id, data.session_dir, data.session_root
        )
        if not os.path.isdir(session_dir):
            raise HTTPException(status_code=404, detail="Session directory not found")
    else:
        session_dir = _require_active_session()
    if not session_dir:
        raise HTTPException(status_code=500, detail="No active session")
    assert isinstance(session_dir, str)
    with input_trace_lock:
        if input_trace_running(session_dir):
            return {
                "status": "already_running",
                "session_dir": session_dir,
                "pid": input_trace_pid(session_dir),
            }

        cmd = [
            "python3",
            "-m",
            "automation.input_trace",
            "start",
            "--session-dir",
            session_dir,
        ]
        if data.include_raw:
            cmd.append("--include-raw")
        if data.motion_sample_ms and data.motion_sample_ms > 0:
            cmd.extend(["--motion-sample-ms", str(data.motion_sample_ms)])
        proc = subprocess.Popen(cmd)
        try:
            manage_process(proc)
        except ProcessCapacityError as exc:
            raise HTTPException(status_code=503, detail=str(exc))

    append_lifecycle_event(
        session_dir, "input_trace_started", "Input trace started", source="api"
    )
    payload = {
        "status": "started",
        "session_dir": session_dir,
        "pid": proc.pid,
        "log_path": input_trace_log_path(session_dir),
    }
    emit_operation_timing(
        session_dir,
        feature="input",
        capability="trace_x11",
        feature_set="control_input_automation",
        operation="trace_start",
        duration_ms=(time.perf_counter() - op_started) * 1000.0,
        result="ok",
        source="api",
        metric_name="input.trace_start.latency",
    )
    return payload


@router.post("/trace/stop")
def input_trace_stop(data: Optional[InputTraceStopModel] = Body(default=None)):
    """Stop the input tracing process for the active session."""
    op_started = time.perf_counter()
    if data is None:
        data = InputTraceStopModel()
    session_dir: Optional[str] = None
    if data.session_id or data.session_dir:
        session_dir = resolve_session_dir(
            data.session_id, data.session_dir, data.session_root
        )
        if not os.path.isdir(session_dir):
            raise HTTPException(status_code=404, detail="Session directory not found")
    else:
        session_dir = read_session_dir() # type: ignore
    if not session_dir:
        return {"status": "already_stopped"}
    assert isinstance(session_dir, str)
    with input_trace_lock:
        if not input_trace_running(session_dir):
            return {"status": "already_stopped", "session_dir": session_dir}

        result = safe_command(
            [
                "python3",
                "-m",
                "automation.input_trace",
                "stop",
                "--session-dir",
                session_dir,
            ]
        )
        if not result.get("ok"):
            raise HTTPException(
                status_code=500,
                detail=(result.get("stderr") or "Failed to stop input trace"),
            )
    append_lifecycle_event(
        session_dir, "input_trace_stopped", "Input trace stopped", source="api"
    )
    payload = {"status": "stopped", "session_dir": session_dir}
    emit_operation_timing(
        session_dir,
        feature="input",
        capability="trace_x11",
        feature_set="control_input_automation",
        operation="trace_stop",
        duration_ms=(time.perf_counter() - op_started) * 1000.0,
        result="ok",
        source="api",
        metric_name="input.trace_stop.latency",
    )
    return payload


@router.get("/trace/x11core/status")
def input_trace_x11_core_status(
    session_id: Optional[str] = None,
    session_dir: Optional[str] = None,
    session_root: Optional[str] = None,
):
    """X11 core input trace status."""
    op_started = time.perf_counter()
    target_dir: Optional[str] = None
    if session_id or session_dir:
        target_dir = resolve_session_dir(session_id, session_dir, session_root)
        if not os.path.isdir(target_dir):
            raise HTTPException(status_code=404, detail="Session directory not found")
    else:
        target_dir = read_session_dir()
    if not target_dir:
        return {"running": False, "state": None, "session_dir": None}
    assert isinstance(target_dir, str)
    pid = input_trace_x11_core_pid(target_dir)
    payload = {
        "session_dir": target_dir,
        "pid": pid,
        "running": input_trace_x11_core_running(target_dir),
        "state": input_trace_x11_core_state(target_dir),
        "log_path": input_trace_x11_core_log_path(target_dir),
    }
    emit_operation_timing(
        target_dir,
        feature="input",
        capability="trace_x11_core",
        feature_set="control_input_automation",
        operation="trace_status",
        duration_ms=(time.perf_counter() - op_started) * 1000.0,
        result="ok",
        source="api",
        metric_name="input.trace_x11_core_status.latency",
    )
    return payload


@router.post("/trace/x11core/start")
def input_trace_x11_core_start(
    data: Optional[InputTraceX11CoreStartModel] = Body(default=None),
):
    """Start the X11 core input tracing process for the active session."""
    op_started = time.perf_counter()
    if data is None:
        data = InputTraceX11CoreStartModel()
    session_dir: Optional[str] = None
    if data.session_id or data.session_dir:
        session_dir = resolve_session_dir(
            data.session_id, data.session_dir, data.session_root
        )
        if not os.path.isdir(session_dir):
            raise HTTPException(status_code=404, detail="Session directory not found")
    else:
        session_dir = _require_active_session()
    if not session_dir:
        raise HTTPException(status_code=500, detail="No active session")
    assert isinstance(session_dir, str)
    with input_trace_x11_core_lock:
        if input_trace_x11_core_running(session_dir):
            return {
                "status": "already_running",
                "session_dir": session_dir,
                "pid": input_trace_x11_core_pid(session_dir),
            }

        cmd = [
            "python3",
            "-m",
            "automation.input_trace_core",
            "start",
            "--session-dir",
            session_dir,
        ]
        if data.motion_sample_ms and data.motion_sample_ms > 0:
            cmd.extend(["--motion-sample-ms", str(data.motion_sample_ms)])
        proc = subprocess.Popen(cmd)
        try:
            manage_process(proc)
        except ProcessCapacityError as exc:
            raise HTTPException(status_code=503, detail=str(exc))
        try:
            with open(input_trace_x11_core_pid_path(session_dir), "w") as f:
                f.write(str(proc.pid))
        except Exception:
            pass
    write_input_trace_x11_core_state(session_dir, "running")
    append_lifecycle_event(
        session_dir,
        "input_trace_x11_core_started",
        "X11 core input trace started",
        source="api",
    )
    payload = {
        "status": "started",
        "session_dir": session_dir,
        "pid": proc.pid,
        "log_path": input_trace_x11_core_log_path(session_dir),
    }
    emit_operation_timing(
        session_dir,
        feature="input",
        capability="trace_x11_core",
        feature_set="control_input_automation",
        operation="trace_start",
        duration_ms=(time.perf_counter() - op_started) * 1000.0,
        result="ok",
        source="api",
        metric_name="input.trace_x11_core_start.latency",
    )
    return payload


@router.post("/trace/x11core/stop")
def input_trace_x11_core_stop(
    data: Optional[InputTraceX11CoreStopModel] = Body(default=None),
):
    """Stop the X11 core input tracing process for the active session."""
    op_started = time.perf_counter()
    if data is None:
        data = InputTraceX11CoreStopModel()
    if data.session_id or data.session_dir:
        session_dir = resolve_session_dir(
            data.session_id, data.session_dir, data.session_root
        )
        if not os.path.isdir(session_dir):
            raise HTTPException(status_code=404, detail="Session directory not found")
    else:
        session_dir = read_session_dir() # type: ignore
    if not session_dir:
        return {"status": "already_stopped"}
    assert isinstance(session_dir, str)
    with input_trace_x11_core_lock:
        if not input_trace_x11_core_running(session_dir):
            return {"status": "already_stopped", "session_dir": session_dir}

        result = safe_command(
            [
                "python3",
                "-m",
                "automation.input_trace_core",
                "stop",
                "--session-dir",
                session_dir,
            ]
        )
        if not result.get("ok"):
            raise HTTPException(
                status_code=500,
                detail=(result.get("stderr") or "Failed to stop x11 core trace"),
            )
    write_input_trace_x11_core_state(session_dir, "stopped")
    append_lifecycle_event(
        session_dir,
        "input_trace_x11_core_stopped",
        "X11 core input trace stopped",
        source="api",
    )
    payload = {"status": "stopped", "session_dir": session_dir}
    emit_operation_timing(
        session_dir,
        feature="input",
        capability="trace_x11_core",
        feature_set="control_input_automation",
        operation="trace_stop",
        duration_ms=(time.perf_counter() - op_started) * 1000.0,
        result="ok",
        source="api",
        metric_name="input.trace_x11_core_stop.latency",
    )
    return payload


@router.get("/trace/client/status")
def input_trace_client_status(
    session_id: Optional[str] = None,
    session_dir: Optional[str] = None,
    session_root: Optional[str] = None,
):
    """Client-side input trace status (noVNC UI)."""
    target_dir: Optional[str] = None
    if session_id or session_dir:
        target_dir = resolve_session_dir(session_id, session_dir, session_root)
        if not os.path.isdir(target_dir):
            raise HTTPException(status_code=404, detail="Session directory not found")
    else:
        target_dir = read_session_dir()
    if not target_dir:
        return {"enabled": False, "session_dir": None}
    assert isinstance(target_dir, str)
    return {
        "session_dir": target_dir,
        "enabled": input_trace_client_enabled(target_dir),
        "log_path": input_trace_client_log_path(target_dir),
    }


@router.post("/trace/client/start")
def input_trace_client_start(
    data: Optional[InputTraceClientStartModel] = Body(default=None),
):
    """Enable client-side input trace collection."""
    op_started = time.perf_counter()
    if data is None:
        data = InputTraceClientStartModel()
    session_dir: Optional[str] = None
    if data.session_id or data.session_dir:
        session_dir = resolve_session_dir(
            data.session_id, data.session_dir, data.session_root
        )
        if not os.path.isdir(session_dir):
            raise HTTPException(status_code=404, detail="Session directory not found")
    else:
        session_dir = _require_active_session()
    if not session_dir:
        raise HTTPException(status_code=500, detail="No active session")
    assert isinstance(session_dir, str)
    write_input_trace_client_state(session_dir, True)
    append_lifecycle_event(
        session_dir,
        "input_trace_client_enabled",
        "Client input trace enabled",
        source="api",
    )
    payload = {
        "status": "enabled",
        "session_dir": session_dir,
        "log_path": input_trace_client_log_path(session_dir),
    }
    emit_operation_timing(
        session_dir,
        feature="input",
        capability="trace_client",
        feature_set="control_input_automation",
        operation="trace_enable",
        duration_ms=(time.perf_counter() - op_started) * 1000.0,
        result="ok",
        source="api",
        metric_name="input.trace_client_enable.latency",
    )
    return payload


@router.post("/trace/client/stop")
def input_trace_client_stop(
    data: Optional[InputTraceClientStopModel] = Body(default=None),
):
    """Disable client-side input trace collection."""
    op_started = time.perf_counter()
    if data is None:
        data = InputTraceClientStopModel()
    session_dir: Optional[str] = None
    if data.session_id or data.session_dir:
        session_dir = resolve_session_dir(
            data.session_id, data.session_dir, data.session_root
        )
        if not os.path.isdir(session_dir):
            raise HTTPException(status_code=404, detail="Session directory not found")
    else:
        session_dir = read_session_dir() # type: ignore
    if not session_dir:
        return {"status": "disabled"}
    assert isinstance(session_dir, str)
    write_input_trace_client_state(session_dir, False)
    append_lifecycle_event(
        session_dir,
        "input_trace_client_disabled",
        "Client input trace disabled",
        source="api",
    )
    payload = {"status": "disabled", "session_dir": session_dir}
    emit_operation_timing(
        session_dir,
        feature="input",
        capability="trace_client",
        feature_set="control_input_automation",
        operation="trace_disable",
        duration_ms=(time.perf_counter() - op_started) * 1000.0,
        result="ok",
        source="api",
        metric_name="input.trace_client_disable.latency",
    )
    return payload


@router.post("/client/event")
async def input_client_event(event: Optional[Dict[str, Any]] = Body(default=None)):
    """Record a client-side input event (noVNC UI)."""
    # Signal user activity to broker (auto-revokes agent)
    await broker.report_user_activity()

    session_dir = read_session_dir()
    if not session_dir:
        return {"status": "ignored", "reason": "no_session"}
    if not input_trace_client_enabled(session_dir):
        return {"status": "ignored", "reason": "client_trace_disabled"}
    payload = dict(event or {})
    payload.setdefault("source", "novnc_client")
    payload.setdefault("layer", "client")
    payload.setdefault("event", "client_event")
    payload.setdefault("origin", "user")
    payload.setdefault("tool", "novnc-ui")
    payload.setdefault("session_id", session_id_from_dir(session_dir))
    payload.setdefault("timestamp_epoch_ms", int(time.time() * 1000))
    payload.setdefault(
        "timestamp_utc", datetime.datetime.now(datetime.timezone.utc).isoformat()
    )
    append_trace_event(input_trace_client_log_path(session_dir), payload)
    return {"status": "ok"}


@router.get("/trace/windows/status")
def input_trace_windows_status(
    session_id: Optional[str] = None,
    session_dir: Optional[str] = None,
    session_root: Optional[str] = None,
):
    """Windows-side input trace status."""
    op_started = time.perf_counter()
    target_dir: Optional[str] = None
    if session_id or session_dir:
        target_dir = resolve_session_dir(session_id, session_dir, session_root)
        if not os.path.isdir(target_dir):
            raise HTTPException(status_code=404, detail="Session directory not found")
    else:
        target_dir = read_session_dir()
    if not target_dir:
        return {"running": False, "state": None, "session_dir": None}
    assert isinstance(target_dir, str)
    pid = input_trace_windows_pid(target_dir)
    payload = {
        "session_dir": target_dir,
        "pid": pid,
        "running": input_trace_windows_running(target_dir),
        "state": input_trace_windows_state(target_dir),
        "backend": input_trace_windows_backend(target_dir),
        "log_path": input_trace_windows_log_path(target_dir),
    }
    emit_operation_timing(
        target_dir,
        feature="input",
        capability="trace_windows",
        feature_set="control_input_automation",
        operation="trace_status",
        duration_ms=(time.perf_counter() - op_started) * 1000.0,
        result="ok",
        source="api",
        metric_name="input.trace_windows_status.latency",
    )
    return payload


@router.post("/trace/windows/start")
def input_trace_windows_start(
    data: Optional[InputTraceWindowsStartModel] = Body(default=None),
):
    """Start Windows-side input tracing."""
    op_started = time.perf_counter()
    if data is None:
        data = InputTraceWindowsStartModel()
    session_dir: Optional[str] = None
    if data.session_id or data.session_dir:
        session_dir = resolve_session_dir(
            data.session_id, data.session_dir, data.session_root
        )
        if not os.path.isdir(session_dir):
            raise HTTPException(status_code=404, detail="Session directory not found")
    else:
        session_dir = _require_active_session()
    if not session_dir:
        raise HTTPException(status_code=500, detail="No active session")
    assert isinstance(session_dir, str)
    with input_trace_windows_lock:
        if input_trace_windows_running(session_dir):
            return {
                "status": "already_running",
                "session_dir": session_dir,
                "pid": input_trace_windows_pid(session_dir),
            }

        backend_val = data.backend or os.getenv("WINEBOT_INPUT_TRACE_WINDOWS_BACKEND") or "auto"
        backend = backend_val.lower()
        if backend not in ("auto", "ahk", "hook"):
            raise HTTPException(
                status_code=400, detail="backend must be one of: auto, ahk, hook"
            )

        hook_script = "/scripts/diagnostics/diagnose-wine-hook.py"
        ahk_script = "/automation/core/input_trace_windows.ahk"
        log_path = input_trace_windows_log_path(session_dir)
        os.makedirs(os.path.dirname(log_path), exist_ok=True)
        motion_ms = data.motion_sample_ms if data.motion_sample_ms is not None else 10
        session_id = session_id_from_dir(session_dir) or ""
        debug_keys = []
        if data.debug_keys:
            debug_keys = [k for k in data.debug_keys if k]
        elif data.debug_keys_csv:
            debug_keys = [
                k.strip() for k in data.debug_keys_csv.split(",") if k.strip()
            ]

        warnings = []

        def start_ahk() -> subprocess.Popen:
            # Convert script path to Windows style
            win_script_path = safe_command(["winepath", "-w", ahk_script])["stdout"]
            cmd = [
                "ahk",
                win_script_path,
                to_wine_path(log_path),
                str(motion_ms),
                session_id,
            ]
            if debug_keys:
                cmd.append(",".join(debug_keys))
                if data.debug_sample_ms is not None:
                    cmd.append(str(data.debug_sample_ms))
            return subprocess.Popen(cmd)

        def start_hook() -> Optional[subprocess.Popen]:
            if not shutil.which("winpy"):
                return None
            if not os.path.exists(hook_script):
                return None
            cmd = [
                "winpy",
                hook_script,
                "--out",
                log_path,
                "--duration",
                "0",
                "--source",
                "windows",
                "--layer",
                "windows",
                "--origin",
                "unknown",
                "--tool",
                "win_hook",
            ]
            if session_id:
                cmd.extend(["--session-id", session_id])
            proc = subprocess.Popen(cmd)
            time.sleep(0.2)
            if proc.poll() is not None:
                return None
            return proc

        proc = None
        backend_used = None

        if backend in ("auto", "hook"):
            proc = start_hook()
            if proc:
                backend_used = "hook"
                if debug_keys:
                    warnings.append("windows trace hook backend ignores debug_keys")
        if proc is None:
            if backend == "hook":
                raise HTTPException(
                    status_code=500, detail="windows hook backend failed to start"
                )
            proc = start_ahk()
            backend_used = "ahk"

        try:
            manage_process(proc)
        except ProcessCapacityError as exc:
            raise HTTPException(status_code=503, detail=str(exc))
        try:
            with open(input_trace_windows_pid_path(session_dir), "w") as f:
                f.write(str(proc.pid))
        except Exception:
            pass
        write_input_trace_windows_state(session_dir, "running")
        if backend_used:
            write_input_trace_windows_backend(session_dir, backend_used)

    append_lifecycle_event(
        session_dir,
        "input_trace_windows_started",
        f"Windows input trace started ({backend_used})",
        source="api",
    )
    payload = {
        "status": "started",
        "session_dir": session_dir,
        "pid": proc.pid,
        "log_path": log_path,
        "backend": backend_used,
    }
    if warnings:
        payload["warnings"] = warnings
    emit_operation_timing(
        session_dir,
        feature="input",
        capability="trace_windows",
        feature_set="control_input_automation",
        operation="trace_start",
        duration_ms=(time.perf_counter() - op_started) * 1000.0,
        result="ok",
        source="api",
        metric_name="input.trace_windows_start.latency",
        tags={"backend": backend_used or "unknown"},
    )
    return payload


@router.post("/trace/windows/stop")
def input_trace_windows_stop(
    data: Optional[InputTraceWindowsStopModel] = Body(default=None),
):
    """Stop Windows-side input tracing."""
    op_started = time.perf_counter()
    if data is None:
        data = InputTraceWindowsStopModel()
    session_dir: Optional[str] = None
    if data.session_id or data.session_dir:
        session_dir = resolve_session_dir(
            data.session_id, data.session_dir, data.session_root
        )
        if not os.path.isdir(session_dir):
            raise HTTPException(status_code=404, detail="Session directory not found")
    else:
        session_dir = read_session_dir() # type: ignore
    if not session_dir:
        return {"status": "already_stopped"}
    assert isinstance(session_dir, str)
    with input_trace_windows_lock:
        pid = input_trace_windows_pid(session_dir)
        if not pid or not pid_running(pid):
            write_input_trace_windows_state(session_dir, "stopped")
            return {"status": "already_stopped", "session_dir": session_dir}
        try:
            os.kill(pid, signal.SIGTERM)
        except Exception:
            raise HTTPException(
                status_code=500, detail="Failed to stop windows input trace"
            )
    write_input_trace_windows_state(session_dir, "stopped")
    append_lifecycle_event(
        session_dir,
        "input_trace_windows_stopped",
        "Windows input trace stopped",
        source="api",
    )
    payload = {"status": "stopped", "session_dir": session_dir}
    emit_operation_timing(
        session_dir,
        feature="input",
        capability="trace_windows",
        feature_set="control_input_automation",
        operation="trace_stop",
        duration_ms=(time.perf_counter() - op_started) * 1000.0,
        result="ok",
        source="api",
        metric_name="input.trace_windows_stop.latency",
    )
    return payload


@router.get("/trace/network/status")
def input_trace_network_status(
    session_id: Optional[str] = None,
    session_dir: Optional[str] = None,
    session_root: Optional[str] = None,
):
    """Network input trace status (VNC proxy)."""
    op_started = time.perf_counter()
    target_dir: Optional[str] = None
    if session_id or session_dir:
        target_dir = resolve_session_dir(session_id, session_dir, session_root)
        if not os.path.isdir(target_dir):
            raise HTTPException(status_code=404, detail="Session directory not found")
    else:
        target_dir = read_session_dir()
    if not target_dir:
        return {"running": False, "state": None, "session_dir": None}
    assert isinstance(target_dir, str)
    pid = input_trace_network_pid(target_dir)
    payload = {
        "session_dir": target_dir,
        "pid": pid,
        "running": input_trace_network_running(target_dir),
        "state": input_trace_network_state(target_dir),
        "log_path": input_trace_network_log_path(target_dir),
    }
    emit_operation_timing(
        target_dir,
        feature="input",
        capability="trace_network",
        feature_set="control_input_automation",
        operation="trace_status",
        duration_ms=(time.perf_counter() - op_started) * 1000.0,
        result="ok",
        source="api",
        metric_name="input.trace_network_status.latency",
    )
    return payload


@router.post("/trace/network/start")
def input_trace_network_start(
    data: Optional[InputTraceClientStartModel] = Body(default=None),
):
    """Enable network input trace logging (proxy must be running)."""
    op_started = time.perf_counter()
    if data is None:
        data = InputTraceClientStartModel()
    session_dir: Optional[str] = None
    if data.session_id or data.session_dir:
        session_dir = resolve_session_dir(
            data.session_id, data.session_dir, data.session_root
        )
        if not os.path.isdir(session_dir):
            raise HTTPException(status_code=404, detail="Session directory not found")
    else:
        session_dir = _require_active_session()
    assert isinstance(session_dir, str)
    with input_trace_network_lock:
        if not input_trace_network_running(session_dir):
            return {
                "status": "not_running",
                "session_dir": session_dir,
                "hint": "Enable WINEBOT_INPUT_TRACE_NETWORK=1 and restart the container.",
            }
        write_input_trace_network_state(session_dir, "enabled")
    append_lifecycle_event(
        session_dir,
        "input_trace_network_enabled",
        "Network input trace enabled",
        source="api",
    )
    payload = {
        "status": "enabled",
        "session_dir": session_dir,
        "log_path": input_trace_network_log_path(session_dir),
    }
    emit_operation_timing(
        session_dir,
        feature="input",
        capability="trace_network",
        feature_set="control_input_automation",
        operation="trace_enable",
        duration_ms=(time.perf_counter() - op_started) * 1000.0,
        result="ok",
        source="api",
        metric_name="input.trace_network_enable.latency",
    )
    return payload


@router.post("/trace/network/stop")
def input_trace_network_stop(
    data: Optional[InputTraceClientStopModel] = Body(default=None),
):
    """Disable network input trace logging (proxy must be running)."""
    op_started = time.perf_counter()
    if data is None:
        data = InputTraceClientStopModel()
    session_dir: Optional[str] = None
    if data.session_id or data.session_dir:
        session_dir = resolve_session_dir(
            data.session_id, data.session_dir, data.session_root
        )
        if not os.path.isdir(session_dir):
            raise HTTPException(status_code=404, detail="Session directory not found")
    else:
        session_dir = read_session_dir() # type: ignore
    if not session_dir:
        return {"status": "disabled"}
    assert isinstance(session_dir, str)
    with input_trace_network_lock:
        if not input_trace_network_running(session_dir):
            return {"status": "not_running", "session_dir": session_dir}
        write_input_trace_network_state(session_dir, "disabled")
    append_lifecycle_event(
        session_dir,
        "input_trace_network_disabled",
        "Network input trace disabled",
        source="api",
    )
    payload = {"status": "disabled", "session_dir": session_dir}
    emit_operation_timing(
        session_dir,
        feature="input",
        capability="trace_network",
        feature_set="control_input_automation",
        operation="trace_disable",
        duration_ms=(time.perf_counter() - op_started) * 1000.0,
        result="ok",
        source="api",
        metric_name="input.trace_network_disable.latency",
    )
    return payload
