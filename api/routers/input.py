from fastapi import APIRouter, HTTPException, Body
from typing import Dict, Any, Optional
import subprocess
import os
import time
import shutil
import datetime
import uuid
import hashlib
from api.core.models import ClickModel, InputTraceStartModel, InputTraceStopModel, InputTraceX11CoreStartModel, InputTraceX11CoreStopModel, InputTraceClientStartModel, InputTraceClientStopModel, InputTraceWindowsStartModel, InputTraceWindowsStopModel
from api.core.broker import broker
from api.utils.files import (ensure_session_dir, append_input_event, append_trace_event, read_session_dir, session_id_from_dir, resolve_session_dir, 
                             input_trace_pid, input_trace_running, input_trace_state, input_trace_log_path,
                             input_trace_x11_core_pid, input_trace_x11_core_running, input_trace_x11_core_state, input_trace_x11_core_log_path, input_trace_x11_core_pid_path, write_input_trace_x11_core_state,
                             input_trace_client_enabled, input_trace_client_log_path, write_input_trace_client_state,
                             input_trace_windows_pid, input_trace_windows_running, input_trace_windows_state, input_trace_windows_backend, input_trace_windows_log_path, input_trace_windows_pid_path, write_input_trace_windows_state, write_input_trace_windows_backend,
                             input_trace_network_pid, input_trace_network_running, input_trace_network_state, input_trace_network_log_path, write_input_trace_network_state,
                             append_lifecycle_event, to_wine_path)
from api.utils.process import run_command, manage_process, pid_running, safe_command

router = APIRouter(prefix="/input", tags=["input"])

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
    
    events = []
    try:
        with open(path, "r") as f:
            lines = f.read().splitlines()
        for line in lines[-limit:]:
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
    except Exception:
        pass
    return {"events": events, "log_path": path}

@router.post("/mouse/click")
async def click_at(data: ClickModel):
    """Click at coordinates (x, y)."""
    if not await broker.check_access():
        raise HTTPException(status_code=423, detail="Agent control denied by policy")

    session_dir = ensure_session_dir()
    trace_id = uuid.uuid4().hex
    append_input_event(session_dir, {
        "event": "agent_click",
        "phase": "request",
        "origin": "agent",
        "source": "api",
        "tool": "api:/input/mouse/click",
        "x": data.x,
        "y": data.y,
        "button": 1,
        "trace_id": trace_id,
        "via": "xdotool",
    })
    run_command(["/automation/x11.sh", "click-at", str(data.x), str(data.y)])
    append_input_event(session_dir, {
        "event": "agent_click",
        "phase": "complete",
        "origin": "agent",
        "source": "api",
        "tool": "api:/input/mouse/click",
        "x": data.x,
        "y": data.y,
        "button": 1,
        "trace_id": trace_id,
        "status": "clicked",
    })
    
    # Log to Windows layer (Cross-layer consistency)
    payload = {
        "event": "mouse_down",
        "origin": "agent",
        "source": "windows",
        "x": data.x,
        "y": data.y,
        "button": 1,
        "trace_id": trace_id,
        "timestamp_epoch_ms": int(time.time() * 1000),
    }
    append_trace_event(input_trace_windows_log_path(session_dir), payload)
    
    return {"status": "clicked", "x": data.x, "y": data.y, "trace_id": trace_id}

@router.get("/trace/status")
def input_trace_status(session_id: Optional[str] = None, session_dir: Optional[str] = None, session_root: Optional[str] = None):
    """Input trace status for the active or specified session."""
    if session_id or session_dir:
        target_dir = resolve_session_dir(session_id, session_dir, session_root)
        if not os.path.isdir(target_dir):
            raise HTTPException(status_code=404, detail="Session directory not found")
    else:
        target_dir = read_session_dir()
    if not target_dir:
        return {"running": False, "state": None, "session_dir": None}
    pid = input_trace_pid(target_dir)
    return {
        "session_dir": target_dir,
        "pid": pid,
        "running": input_trace_running(target_dir),
        "state": input_trace_state(target_dir),
        "log_path": input_trace_log_path(target_dir),
    }

@router.post("/trace/start")
def input_trace_start(data: Optional[InputTraceStartModel] = Body(default=None)):
    """Start the input tracing process for the active session."""
    if data is None:
        data = InputTraceStartModel()
    if data.session_id or data.session_dir:
        session_dir = resolve_session_dir(data.session_id, data.session_dir, data.session_root)
        if not os.path.isdir(session_dir):
            raise HTTPException(status_code=404, detail="Session directory not found")
    else:
        session_dir = ensure_session_dir()
    if input_trace_running(session_dir):
        return {"status": "already_running", "session_dir": session_dir, "pid": input_trace_pid(session_dir)}

    cmd = ["python3", "-m", "automation.input_trace", "start", "--session-dir", session_dir]
    if data.include_raw:
        cmd.append("--include-raw")
    if data.motion_sample_ms and data.motion_sample_ms > 0:
        cmd.extend(["--motion-sample-ms", str(data.motion_sample_ms)])
    proc = subprocess.Popen(cmd)
    manage_process(proc)

    append_lifecycle_event(session_dir, "input_trace_started", "Input trace started", source="api")
    return {
        "status": "started",
        "session_dir": session_dir,
        "pid": proc.pid,
        "log_path": input_trace_log_path(session_dir),
    }

@router.post("/trace/stop")
def input_trace_stop(data: Optional[InputTraceStopModel] = Body(default=None)):
    """Stop the input tracing process for the active session."""
    if data is None:
        data = InputTraceStopModel()
    if data.session_id or data.session_dir:
        session_dir = resolve_session_dir(data.session_id, data.session_dir, data.session_root)
        if not os.path.isdir(session_dir):
            raise HTTPException(status_code=404, detail="Session directory not found")
    else:
        session_dir = read_session_dir()
    if not session_dir:
        return {"status": "already_stopped"}
    if not input_trace_running(session_dir):
        return {"status": "already_stopped", "session_dir": session_dir}

    result = safe_command(["python3", "-m", "automation.input_trace", "stop", "--session-dir", session_dir])
    if not result.get("ok"):
        raise HTTPException(status_code=500, detail=(result.get("stderr") or "Failed to stop input trace"))
    append_lifecycle_event(session_dir, "input_trace_stopped", "Input trace stopped", source="api")
    return {"status": "stopped", "session_dir": session_dir}

@router.get("/trace/x11core/status")
def input_trace_x11_core_status(session_id: Optional[str] = None, session_dir: Optional[str] = None, session_root: Optional[str] = None):
    """X11 core input trace status."""
    if session_id or session_dir:
        target_dir = resolve_session_dir(session_id, session_dir, session_root)
        if not os.path.isdir(target_dir):
            raise HTTPException(status_code=404, detail="Session directory not found")
    else:
        target_dir = read_session_dir()
    if not target_dir:
        return {"running": False, "state": None, "session_dir": None}
    pid = input_trace_x11_core_pid(target_dir)
    return {
        "session_dir": target_dir,
        "pid": pid,
        "running": input_trace_x11_core_running(target_dir),
        "state": input_trace_x11_core_state(target_dir),
        "log_path": input_trace_x11_core_log_path(target_dir),
    }

@router.post("/trace/x11core/start")
def input_trace_x11_core_start(data: Optional[InputTraceX11CoreStartModel] = Body(default=None)):
    """Start the X11 core input tracing process for the active session."""
    if data is None:
        data = InputTraceX11CoreStartModel()
    if data.session_id or data.session_dir:
        session_dir = resolve_session_dir(data.session_id, data.session_dir, data.session_root)
        if not os.path.isdir(session_dir):
            raise HTTPException(status_code=404, detail="Session directory not found")
    else:
        session_dir = ensure_session_dir()
    if input_trace_x11_core_running(session_dir):
        return {"status": "already_running", "session_dir": session_dir, "pid": input_trace_x11_core_pid(session_dir)}

    cmd = ["python3", "-m", "automation.input_trace_core", "start", "--session-dir", session_dir]
    if data.motion_sample_ms and data.motion_sample_ms > 0:
        cmd.extend(["--motion-sample-ms", str(data.motion_sample_ms)])
    proc = subprocess.Popen(cmd)
    manage_process(proc)
    try:
        with open(input_trace_x11_core_pid_path(session_dir), "w") as f:
            f.write(str(proc.pid))
    except Exception:
        pass
    write_input_trace_x11_core_state(session_dir, "running")
    append_lifecycle_event(session_dir, "input_trace_x11_core_started", "X11 core input trace started", source="api")
    return {
        "status": "started",
        "session_dir": session_dir,
        "pid": proc.pid,
        "log_path": input_trace_x11_core_log_path(session_dir),
    }

@router.post("/trace/x11core/stop")
def input_trace_x11_core_stop(data: Optional[InputTraceX11CoreStopModel] = Body(default=None)):
    """Stop the X11 core input tracing process for the active session."""
    if data is None:
        data = InputTraceX11CoreStopModel()
    if data.session_id or data.session_dir:
        session_dir = resolve_session_dir(data.session_id, data.session_dir, data.session_root)
        if not os.path.isdir(session_dir):
            raise HTTPException(status_code=404, detail="Session directory not found")
    else:
        session_dir = read_session_dir()
    if not session_dir:
        return {"status": "already_stopped"}
    if not input_trace_x11_core_running(session_dir):
        return {"status": "already_stopped", "session_dir": session_dir}

    result = safe_command(["python3", "-m", "automation.input_trace_core", "stop", "--session-dir", session_dir])
    if not result.get("ok"):
        raise HTTPException(status_code=500, detail=(result.get("stderr") or "Failed to stop x11 core trace"))
    write_input_trace_x11_core_state(session_dir, "stopped")
    append_lifecycle_event(session_dir, "input_trace_x11_core_stopped", "X11 core input trace stopped", source="api")
    return {"status": "stopped", "session_dir": session_dir}

@router.get("/trace/client/status")
def input_trace_client_status(session_id: Optional[str] = None, session_dir: Optional[str] = None, session_root: Optional[str] = None):
    """Client-side input trace status (noVNC UI)."""
    if session_id or session_dir:
        target_dir = resolve_session_dir(session_id, session_dir, session_root)
        if not os.path.isdir(target_dir):
            raise HTTPException(status_code=404, detail="Session directory not found")
    else:
        target_dir = read_session_dir()
    if not target_dir:
        return {"enabled": False, "session_dir": None}
    return {
        "session_dir": target_dir,
        "enabled": input_trace_client_enabled(target_dir),
        "log_path": input_trace_client_log_path(target_dir),
    }

@router.post("/trace/client/start")
def input_trace_client_start(data: Optional[InputTraceClientStartModel] = Body(default=None)):
    """Enable client-side input trace collection."""
    if data is None:
        data = InputTraceClientStartModel()
    if data.session_id or data.session_dir:
        session_dir = resolve_session_dir(data.session_id, data.session_dir, data.session_root)
        if not os.path.isdir(session_dir):
            raise HTTPException(status_code=404, detail="Session directory not found")
    else:
        session_dir = ensure_session_dir()
    write_input_trace_client_state(session_dir, True)
    append_lifecycle_event(session_dir, "input_trace_client_enabled", "Client input trace enabled", source="api")
    return {"status": "enabled", "session_dir": session_dir, "log_path": input_trace_client_log_path(session_dir)}

@router.post("/trace/client/stop")
def input_trace_client_stop(data: Optional[InputTraceClientStopModel] = Body(default=None)):
    """Disable client-side input trace collection."""
    if data is None:
        data = InputTraceClientStopModel()
    if data.session_id or data.session_dir:
        session_dir = resolve_session_dir(data.session_id, data.session_dir, data.session_root)
        if not os.path.isdir(session_dir):
            raise HTTPException(status_code=404, detail="Session directory not found")
    else:
        session_dir = read_session_dir()
    if not session_dir:
        return {"status": "disabled"}
    write_input_trace_client_state(session_dir, False)
    append_lifecycle_event(session_dir, "input_trace_client_disabled", "Client input trace disabled", source="api")
    return {"status": "disabled", "session_dir": session_dir}

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
    payload.setdefault("timestamp_utc", datetime.datetime.now(datetime.timezone.utc).isoformat())
    append_trace_event(input_trace_client_log_path(session_dir), payload)
    return {"status": "ok"}

@router.get("/trace/windows/status")
def input_trace_windows_status(session_id: Optional[str] = None, session_dir: Optional[str] = None, session_root: Optional[str] = None):
    """Windows-side input trace status."""
    if session_id or session_dir:
        target_dir = resolve_session_dir(session_id, session_dir, session_root)
        if not os.path.isdir(target_dir):
            raise HTTPException(status_code=404, detail="Session directory not found")
    else:
        target_dir = read_session_dir()
    if not target_dir:
        return {"running": False, "state": None, "session_dir": None}
    pid = input_trace_windows_pid(target_dir)
    return {
        "session_dir": target_dir,
        "pid": pid,
        "running": input_trace_windows_running(target_dir),
        "state": input_trace_windows_state(target_dir),
        "backend": input_trace_windows_backend(target_dir),
        "log_path": input_trace_windows_log_path(target_dir),
    }

@router.post("/trace/windows/start")
def input_trace_windows_start(data: Optional[InputTraceWindowsStartModel] = Body(default=None)):
    """Start Windows-side input tracing."""
    if data is None:
        data = InputTraceWindowsStartModel()
    if data.session_id or data.session_dir:
        session_dir = resolve_session_dir(data.session_id, data.session_dir, data.session_root)
        if not os.path.isdir(session_dir):
            raise HTTPException(status_code=404, detail="Session directory not found")
    else:
        session_dir = ensure_session_dir()
    if input_trace_windows_running(session_dir):
        return {"status": "already_running", "session_dir": session_dir, "pid": input_trace_windows_pid(session_dir)}

    backend = (data.backend or os.getenv("WINEBOT_INPUT_TRACE_WINDOWS_BACKEND", "auto")).lower()
    if backend not in ("auto", "ahk", "hook"):
        raise HTTPException(status_code=400, detail="backend must be one of: auto, ahk, hook")

    hook_script = "/scripts/diagnose-wine-hook.py"
    ahk_script = "/automation/input_trace_windows.ahk"
    log_path = input_trace_windows_log_path(session_dir)
    os.makedirs(os.path.dirname(log_path), exist_ok=True)
    motion_ms = data.motion_sample_ms if data.motion_sample_ms is not None else 10
    session_id = session_id_from_dir(session_dir) or ""
    debug_keys = []
    if data.debug_keys:
        debug_keys = [k for k in data.debug_keys if k]
    elif data.debug_keys_csv:
        debug_keys = [k.strip() for k in data.debug_keys_csv.split(",") if k.strip()]

    warnings = []

    def start_ahk() -> subprocess.Popen:
        cmd = ["ahk", ahk_script, to_wine_path(log_path), str(motion_ms), session_id]
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
            raise HTTPException(status_code=500, detail="windows hook backend failed to start")
        proc = start_ahk()
        backend_used = "ahk"

    manage_process(proc)
    try:
        with open(input_trace_windows_pid_path(session_dir), "w") as f:
            f.write(str(proc.pid))
    except Exception:
        pass
    write_input_trace_windows_state(session_dir, "running")
    if backend_used:
        write_input_trace_windows_backend(session_dir, backend_used)
    append_lifecycle_event(session_dir, "input_trace_windows_started", f"Windows input trace started ({backend_used})", source="api")
    payload = {"status": "started", "session_dir": session_dir, "pid": proc.pid, "log_path": log_path, "backend": backend_used}
    if warnings:
        payload["warnings"] = warnings
    return payload

@router.post("/trace/windows/stop")
def input_trace_windows_stop(data: Optional[InputTraceWindowsStopModel] = Body(default=None)):
    """Stop Windows-side input tracing."""
    if data is None:
        data = InputTraceWindowsStopModel()
    if data.session_id or data.session_dir:
        session_dir = resolve_session_dir(data.session_id, data.session_dir, data.session_root)
        if not os.path.isdir(session_dir):
            raise HTTPException(status_code=404, detail="Session directory not found")
    else:
        session_dir = read_session_dir()
    if not session_dir:
        return {"status": "already_stopped"}
    pid = input_trace_windows_pid(session_dir)
    if not pid or not pid_running(pid):
        write_input_trace_windows_state(session_dir, "stopped")
        return {"status": "already_stopped", "session_dir": session_dir}
    try:
        os.kill(pid, signal.SIGTERM)
    except Exception:
        raise HTTPException(status_code=500, detail="Failed to stop windows input trace")
    write_input_trace_windows_state(session_dir, "stopped")
    append_lifecycle_event(session_dir, "input_trace_windows_stopped", "Windows input trace stopped", source="api")
    return {"status": "stopped", "session_dir": session_dir}

@router.get("/trace/network/status")
def input_trace_network_status(session_id: Optional[str] = None, session_dir: Optional[str] = None, session_root: Optional[str] = None):
    """Network input trace status (VNC proxy)."""
    if session_id or session_dir:
        target_dir = resolve_session_dir(session_id, session_dir, session_root)
        if not os.path.isdir(target_dir):
            raise HTTPException(status_code=404, detail="Session directory not found")
    else:
        target_dir = read_session_dir()
    if not target_dir:
        return {"running": False, "state": None, "session_dir": None}
    pid = input_trace_network_pid(target_dir)
    return {
        "session_dir": target_dir,
        "pid": pid,
        "running": input_trace_network_running(target_dir),
        "state": input_trace_network_state(target_dir),
        "log_path": input_trace_network_log_path(target_dir),
    }

@router.post("/trace/network/start")
def input_trace_network_start(data: Optional[InputTraceClientStartModel] = Body(default=None)):
    """Enable network input trace logging (proxy must be running)."""
    if data is None:
        data = InputTraceClientStartModel()
    if data.session_id or data.session_dir:
        session_dir = resolve_session_dir(data.session_id, data.session_dir, data.session_root)
        if not os.path.isdir(session_dir):
            raise HTTPException(status_code=404, detail="Session directory not found")
    else:
        session_dir = ensure_session_dir()
    if not input_trace_network_running(session_dir):
        return {"status": "not_running", "session_dir": session_dir, "hint": "Enable WINEBOT_INPUT_TRACE_NETWORK=1 and restart the container."}
    write_input_trace_network_state(session_dir, "enabled")
    append_lifecycle_event(session_dir, "input_trace_network_enabled", "Network input trace enabled", source="api")
    return {"status": "enabled", "session_dir": session_dir, "log_path": input_trace_network_log_path(session_dir)}

@router.post("/trace/network/stop")
def input_trace_network_stop(data: Optional[InputTraceClientStopModel] = Body(default=None)):
    """Disable network input trace logging (proxy must be running)."""
    if data is None:
        data = InputTraceClientStopModel()
    if data.session_id or data.session_dir:
        session_dir = resolve_session_dir(data.session_id, data.session_dir, data.session_root)
        if not os.path.isdir(session_dir):
            raise HTTPException(status_code=404, detail="Session directory not found")
    else:
        session_dir = read_session_dir()
    if not session_dir:
        return {"status": "disabled"}
    if not input_trace_network_running(session_dir):
        return {"status": "not_running", "session_dir": session_dir}
    write_input_trace_network_state(session_dir, "disabled")
    append_lifecycle_event(session_dir, "input_trace_network_disabled", "Network input trace disabled", source="api")
    return {"status": "disabled", "session_dir": session_dir}
