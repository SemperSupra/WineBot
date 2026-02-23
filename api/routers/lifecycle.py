from fastapi import APIRouter, HTTPException, Body
from typing import Dict, Any, Optional
import asyncio
import json
import os
import signal
import threading
import time
import subprocess
from api.utils.files import (
    read_session_dir,
    lifecycle_log_path,
    append_lifecycle_event,
    resolve_session_dir,
    ensure_session_subdirs,
    ensure_user_profile,
    write_session_dir,
    write_session_manifest,
    link_wine_user_dir,
    write_session_state,
    recorder_running,
    read_session_state,
    read_session_mode,
    read_session_control_mode,
    write_session_control_mode,
    validate_path,
    write_instance_state,
    read_instance_state,
)
from api.core.versioning import ARTIFACT_SCHEMA_VERSION
from api.utils.process import safe_command, find_processes
from api.core.recorder import stop_recording
from api.core.broker import broker
from api.core.models import SessionSuspendModel, SessionResumeModel
from api.core.models import ControlPolicyMode
from api.core.telemetry import emit_operation_timing


router = APIRouter(tags=["lifecycle"])
session_transition_lock = asyncio.Lock()
shutdown_transition_lock = asyncio.Lock()
_shutdown_in_progress = False
_shutdown_mode = ""
_shutdown_started_at = 0.0
_SHUTDOWN_GUARD_TTL_SEC = 120.0


# --- Lifecycle Logic ---
def _validate_session_transition(
    current_state: Optional[str], target: str, session_mode: str
) -> None:
    state = (current_state or "active").strip().lower()
    if target == "suspend":
        if state in {"completed"}:
            raise HTTPException(
                status_code=409,
                detail="Cannot suspend a completed session",
            )
    elif target == "resume":
        if session_mode == "oneshot" and state == "completed":
            raise HTTPException(
                status_code=409,
                detail="One-shot session is completed and cannot be resumed",
            )
    else:
        raise HTTPException(status_code=400, detail=f"Unknown transition target: {target}")


def _require_active_session_or_conflict(target_dir: str) -> None:
    active_dir = read_session_dir()
    if active_dir != target_dir:
        raise HTTPException(
            status_code=409,
            detail="Target session is not active",
        )


def graceful_wine_shutdown(session_dir: Optional[str]) -> Dict[str, Any]:
    results = {}
    append_lifecycle_event(
        session_dir, "wine_shutdown_requested", "Requesting Wine shutdown", source="api"
    )
    wineboot = safe_command(["wineboot", "--shutdown"], timeout=10)
    results["wineboot"] = wineboot
    if wineboot.get("ok"):
        append_lifecycle_event(
            session_dir,
            "wine_shutdown_complete",
            "Wine shutdown complete",
            source="api",
        )
    else:
        append_lifecycle_event(
            session_dir,
            "wine_shutdown_failed",
            "Wine shutdown failed",
            source="api",
            extra=wineboot,
        )
    wineserver = safe_command(["wineserver", "-k"], timeout=5)
    results["wineserver"] = wineserver
    if wineserver.get("ok"):
        append_lifecycle_event(
            session_dir, "wineserver_killed", "wineserver -k completed", source="api"
        )
    else:
        append_lifecycle_event(
            session_dir,
            "wineserver_kill_failed",
            "wineserver -k failed",
            source="api",
            extra=wineserver,
        )
    return results


def graceful_component_shutdown(session_dir: Optional[str]) -> Dict[str, Any]:
    results = {}
    append_lifecycle_event(
        session_dir,
        "component_shutdown_requested",
        "Stopping UI/VNC components",
        source="api",
    )
    components = [
        ("novnc_proxy", ["pkill", "-TERM", "-f", "novnc_proxy"]),
        ("websockify", ["pkill", "-TERM", "-f", "websockify"]),
        ("x11vnc", ["pkill", "-TERM", "-x", "x11vnc"]),
        ("winedbg", ["pkill", "-TERM", "-x", "winedbg"]),
        ("gdb", ["pkill", "-TERM", "-x", "gdb"]),
        ("openbox", ["pkill", "-TERM", "-x", "openbox"]),
        ("wine_explorer", ["pkill", "-TERM", "-f", "explorer.exe"]),
        ("xvfb", ["pkill", "-TERM", "-x", "Xvfb"]),
    ]
    for name, cmd in components:
        result = safe_command(cmd, timeout=3)
        results[name] = result
        if result.get("ok"):
            append_lifecycle_event(
                session_dir, f"{name}_stopped", f"{name} stopped", source="api"
            )
        else:
            append_lifecycle_event(
                session_dir,
                f"{name}_stop_failed",
                f"{name} stop failed",
                source="api",
                extra=result,
            )
    return results


def _shutdown_process(
    session_dir: Optional[str], delay: float, sig: int = signal.SIGTERM
) -> None:
    time.sleep(delay)
    append_lifecycle_event(
        session_dir,
        "shutdown_signal",
        f"Sending signal {sig} to pid 1",
        source="api",
        extra={"signal": sig, "delay": delay},
    )
    try:
        os.kill(1, sig)
    except Exception as exc:
        append_lifecycle_event(
            session_dir,
            "shutdown_signal_failed",
            "Failed to signal pid 1",
            source="api",
            extra={"signal": sig, "error": str(exc)},
        )
        os._exit(0)


def schedule_shutdown(session_dir: Optional[str], delay: float, sig: int) -> None:
    append_lifecycle_event(
        session_dir,
        "shutdown_scheduled",
        "Shutdown scheduled",
        source="api",
        extra={"signal": sig, "delay": delay},
    )
    thread = threading.Thread(
        target=_shutdown_process, args=(session_dir, delay, sig), daemon=True
    )
    thread.start()


@router.get("/lifecycle/status")
async def lifecycle_status():
    """Detailed lifecycle status including process checks."""
    op_started = time.perf_counter()
    from api.routers.health import health_check

    # Base health
    status = health_check()

    # Process details
    processes = {
        "xvfb": {"ok": len(find_processes("Xvfb", exact=False)) > 0},
        "openbox": {"ok": len(find_processes("openbox", exact=False)) > 0},
        "x11vnc": {"ok": len(find_processes("x11vnc", exact=False)) > 0},
        "novnc": {
            "ok": len(find_processes("websockify")) > 0
        },  # Check websockify as proxy
        "wine_explorer": {"ok": len(find_processes("explorer.exe")) > 0},
        "wineserver": {"ok": len(find_processes("wineserver")) > 0},
    }

    session_dir = read_session_dir()
    session_state = read_session_state(session_dir) if session_dir else None
    session_mode = read_session_mode(session_dir) if session_dir else None
    session_control_mode = read_session_control_mode(session_dir) if session_dir else None
    instance_state = read_instance_state()
    control_state = broker.get_state()
    instance_state["control_mode"] = control_state.instance_control_mode.value

    payload = {
        **status,
        "session_id": os.path.basename(session_dir) if session_dir else None,
        "session_dir": session_dir,
        "session_state": session_state,
        "session_mode": session_mode,
        "session_control_mode": session_control_mode,
        "instance": instance_state,
        "control": {
            "active_controller": control_state.control_mode.value,
            "instance_mode": control_state.instance_control_mode.value,
            "session_mode": control_state.session_control_mode.value,
            "effective_mode": control_state.effective_control_mode.value,
        },
        "user_dir": os.getenv("WINEBOT_USER_DIR"),
        "processes": processes,
    }
    emit_operation_timing(
        session_dir,
        feature="lifecycle",
        capability="status",
        feature_set="session_lifecycle_management",
        operation="lifecycle_status",
        duration_ms=(time.perf_counter() - op_started) * 1000.0,
        result="ok",
        source="api",
        metric_name="lifecycle.status.latency",
    )
    return payload


@router.post("/openbox/reconfigure")
async def openbox_reconfigure():
    """Reload Openbox configuration."""
    safe_command(["openbox", "--reconfigure"])
    return {"status": "reconfigured"}


@router.post("/openbox/restart")
async def openbox_restart():
    """Restart Openbox."""
    safe_command(["openbox", "--restart"])
    return {"status": "restarted"}


@router.get("/lifecycle/events")
def lifecycle_events(limit: int = 100):
    """Return recent lifecycle events."""
    if limit < 1:
        raise HTTPException(status_code=400, detail="limit must be >= 1")
    session_dir = read_session_dir()
    if not session_dir:
        return {"events": []}
    path = lifecycle_log_path(session_dir)
    if not os.path.exists(path):
        return {"events": []}
    
    from api.utils.files import read_file_tail_lines
    raw_lines = read_file_tail_lines(path, limit=limit)
    events = []
    for line in raw_lines:
        try:
            events.append(json.loads(line))
        except json.JSONDecodeError:
            continue
    return {"events": events}


async def atomic_shutdown(session_dir: Optional[str], wine_shutdown: bool = True) -> Dict[str, Any]:
    """Coordinated shutdown ensuring data persistence."""
    results: Dict[str, Any] = {}
    
    # 1. Stop Recorder first (most critical for data)
    if session_dir and recorder_running(session_dir):
        append_lifecycle_event(session_dir, "shutdown_recorder_start", "Stopping recorder for cleanup")
        try:
            await stop_recording()
            results["recorder"] = "ok"
        except Exception as e:
            results["recorder"] = f"error: {str(e)}"

    # 2. Shutdown Wine
    if wine_shutdown:
        results["wine"] = graceful_wine_shutdown(session_dir)

    # 3. Shutdown UI Components
    results["components"] = graceful_component_shutdown(session_dir)
    
    return results


@router.post("/lifecycle/shutdown")
async def lifecycle_shutdown(
    delay: float = 0.5,
    wine_shutdown: bool = True,
    power_off: bool = False,
):
    """Gracefully stop components and terminate the container process."""
    global _shutdown_in_progress, _shutdown_mode, _shutdown_started_at
    op_started = time.perf_counter()
    session_dir = read_session_dir()
    async with shutdown_transition_lock:
        now = time.time()
        if _shutdown_in_progress and (now - _shutdown_started_at) <= _SHUTDOWN_GUARD_TTL_SEC:
            return {
                "status": "already_shutting_down",
                "mode": _shutdown_mode or "unknown",
            }
        _shutdown_in_progress = True
        _shutdown_mode = "power_off" if power_off else "graceful"
        _shutdown_started_at = now
    append_lifecycle_event(
        session_dir, "shutdown_requested", "Shutdown requested via API", source="api"
    )
    if power_off:
        write_instance_state("powering_off", reason="api_lifecycle_shutdown_power_off")
        append_lifecycle_event(
            session_dir, "power_off", "Immediate shutdown requested", source="api"
        )
        tail_kill = safe_command(["pkill", "-9", "-f", "tail -f /dev/null"])
        append_lifecycle_event(
            session_dir,
            "power_off_keepalive_kill",
            "Attempted to stop keepalive process",
            source="api",
            extra=tail_kill,
        )
        schedule_shutdown(session_dir, max(0.0, delay), signal.SIGKILL)
        emit_operation_timing(
            session_dir,
            feature="lifecycle",
            capability="shutdown",
            feature_set="session_lifecycle_management",
            operation="shutdown_power_off",
            duration_ms=(time.perf_counter() - op_started) * 1000.0,
            result="ok",
            source="api",
            metric_name="lifecycle.shutdown.latency",
        )
        return {"status": "powering_off", "delay_seconds": delay}

    write_instance_state("shutting_down", reason="api_lifecycle_shutdown")
    results = await atomic_shutdown(session_dir, wine_shutdown=wine_shutdown)
    schedule_shutdown(session_dir, delay, signal.SIGTERM)
    
    payload = {
        "status": "shutting_down",
        "delay_seconds": delay,
        "results": results
    }
    emit_operation_timing(
        session_dir,
        feature="lifecycle",
        capability="shutdown",
        feature_set="session_lifecycle_management",
        operation="shutdown_graceful",
        duration_ms=(time.perf_counter() - op_started) * 1000.0,
        result="ok",
        source="api",
        metric_name="lifecycle.shutdown.latency",
    )
    return payload


@router.post("/lifecycle/reset_workspace")
async def reset_workspace():
    """Force Wine desktop to be maximized and undecorated."""
    # Start explorer if missing
    if not find_processes("explorer"):
        subprocess.Popen(
            ["wine", "explorer.exe"],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            start_new_session=True,
        )
        await asyncio.sleep(3)

    # Force geometry update (mostly for windowed mode now)
    subprocess.run(
        ["xdotool", "search", "--class", "explorer", "windowmove", "0", "0"],
        capture_output=True,
    )

    return {"status": "ok", "message": "Workspace reset requested"}


@router.get("/sessions")
def list_sessions(root: Optional[str] = None, limit: int = 100):
    """List available sessions on disk."""
    if limit < 1:
        raise HTTPException(status_code=400, detail="limit must be >= 1")
    root_dir = root or os.getenv("WINEBOT_SESSION_ROOT") or "/artifacts/sessions"
    try:
        root_dir = validate_path(root_dir)
    except Exception as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    if not os.path.exists(root_dir):
        return {"root": root_dir, "sessions": []}

    current_session = read_session_dir()
    entries = []
    for name in os.listdir(root_dir):
        session_dir = os.path.join(root_dir, name)
        if not os.path.isdir(session_dir):
            continue
        session_json = os.path.join(session_dir, "session.json")
        data = {
            "session_id": name,
            "session_dir": session_dir,
            "active": session_dir == current_session,
            "state": read_session_state(session_dir),
            "mode": read_session_mode(session_dir),
            "control_mode": read_session_control_mode(session_dir),
            "has_session_json": os.path.exists(session_json),
            "last_modified_epoch": int(os.path.getmtime(session_dir)),
        }
        if data["has_session_json"]:
            try:
                with open(session_json, "r") as f:
                    data["manifest"] = json.load(f)
            except Exception:
                data["manifest"] = None
        entries.append(data)
    entries.sort(key=lambda item: item.get("last_modified_epoch", 0), reverse=True)
    return {"root": root_dir, "sessions": entries[:limit]}


@router.post("/sessions/suspend")
async def suspend_session(
    data: Optional[SessionSuspendModel] = Body(default=None),
    allow_inactive: bool = False,
):
    """Suspend a session without terminating the container."""
    op_started = time.perf_counter()
    if data is None:
        data = SessionSuspendModel()
    async with session_transition_lock:
        current_session = read_session_dir()
        try:
            session_id_part = data.session_id or data.session_dir
            session_dir = (
                resolve_session_dir(data.session_id, data.session_dir, data.session_root)
                if session_id_part
                else current_session
            )
        except Exception as exc:
            raise HTTPException(status_code=400, detail=str(exc))
        if not session_dir:
            raise HTTPException(status_code=404, detail="No active session to suspend")
        if not os.path.isdir(session_dir):
            raise HTTPException(status_code=404, detail="Session directory not found")
        if not allow_inactive:
            _require_active_session_or_conflict(session_dir)

        session_mode = read_session_mode(session_dir)
        _validate_session_transition(
            read_session_state(session_dir),
            "suspend",
            session_mode,
        )

        if (
            data.stop_recording
            and session_dir == current_session
            and recorder_running(session_dir)
        ):
            try:
                await stop_recording()
            except Exception as exc:
                raise HTTPException(
                    status_code=500,
                    detail=f"Failed to stop recording before suspend: {exc}",
                )
        wine_shutdown_result: Optional[Dict[str, Any]] = None
        if data.shutdown_wine:
            wine_shutdown_result = graceful_wine_shutdown(session_dir)
            failing_steps = [
                name for name, result in wine_shutdown_result.items() if not result.get("ok")
            ]
            if failing_steps:
                raise HTTPException(
                    status_code=500,
                    detail=(
                        "Session suspend aborted due to Wine shutdown failure. "
                        f"Failed steps: {', '.join(failing_steps)}"
                    ),
                )
        new_state = "completed" if session_mode == "oneshot" else "suspended"
        write_session_state(session_dir, new_state)
        append_lifecycle_event(
            session_dir,
            "session_suspended" if new_state == "suspended" else "session_completed",
            "Session suspended via API" if new_state == "suspended" else "One-shot session completed",
            source="api",
        )
        payload: Dict[str, Any] = {
            "status": new_state,
            "session_dir": session_dir,
            "session_id": os.path.basename(session_dir),
            "session_mode": session_mode,
        }
        if wine_shutdown_result is not None:
            payload["wine_shutdown"] = wine_shutdown_result
        emit_operation_timing(
            session_dir,
            feature="lifecycle",
            capability="session_transition",
            feature_set="session_lifecycle_management",
            operation="session_suspend",
            duration_ms=(time.perf_counter() - op_started) * 1000.0,
            result="ok",
            source="api",
            metric_name="lifecycle.session_suspend.latency",
            tags={"session_mode": session_mode, "status": new_state},
        )
        return payload


@router.post("/sessions/resume")
async def resume_session(data: Optional[SessionResumeModel] = Body(default=None)):
    """Resume an existing session directory."""
    op_started = time.perf_counter()
    if data is None:
        data = SessionResumeModel()
    async with session_transition_lock:
        current_session = read_session_dir()
        try:
            target_dir = resolve_session_dir(
                data.session_id, data.session_dir, data.session_root
            )
        except Exception as exc:
            raise HTTPException(status_code=400, detail=str(exc))
        if not os.path.isdir(target_dir):
            raise HTTPException(status_code=404, detail="Session directory not found")
        session_mode = read_session_mode(target_dir)
        _validate_session_transition(
            read_session_state(target_dir),
            "resume",
            session_mode,
        )
    
        # HARDENING: Verify artifact schema version compatibility
        session_json = os.path.join(target_dir, "session.json")
        if os.path.exists(session_json):
            try:
                with open(session_json, "r") as f:
                    manifest = json.load(f)
                    old_ver = manifest.get("schema_version", "1.0")
                    if float(old_ver) < float(ARTIFACT_SCHEMA_VERSION):
                        # We could implement migrations here, but for now we just warn or fail
                        pass
                    elif float(old_ver) > float(ARTIFACT_SCHEMA_VERSION):
                        raise HTTPException(
                            status_code=409, 
                            detail=f"Session version {old_ver} is newer than current build ({ARTIFACT_SCHEMA_VERSION})."
                        )
            except (ValueError, json.JSONDecodeError):
                pass

        # HARDENING: Force shutdown of current session before resume
        if current_session and current_session != target_dir:
            append_lifecycle_event(current_session, "handover_start", f"Handing over to {target_dir}")
            await atomic_shutdown(current_session, wine_shutdown=bool(data.restart_wine))

        session_json = os.path.join(target_dir, "session.json")
        if not os.path.exists(session_json):
            write_session_manifest(target_dir, os.path.basename(target_dir))
        ensure_session_subdirs(target_dir)
        write_session_control_mode(target_dir, read_session_control_mode(target_dir))
        user_dir = os.path.join(target_dir, "user")
        os.makedirs(user_dir, exist_ok=True)
        ensure_user_profile(user_dir)

        write_session_dir(target_dir)
        os.environ["WINEBOT_SESSION_DIR"] = target_dir
        os.environ["WINEBOT_SESSION_ID"] = os.path.basename(target_dir)
        os.environ["WINEBOT_USER_DIR"] = user_dir
        link_wine_user_dir(user_dir)
        write_session_state(target_dir, "active")
        append_lifecycle_event(
            target_dir, "session_resumed", "Session resumed via API", source="api"
        )

        if data.restart_wine:
            try:
                subprocess.Popen(["wine", "explorer"])
            except Exception:
                pass

        status = "resumed"
        if current_session == target_dir:
            status = "already_active"

        # Update broker
        interactive = os.getenv("MODE", "headless") == "interactive"
        session_control_mode = ControlPolicyMode(read_session_control_mode(target_dir))
        await broker.update_session(
            os.path.basename(target_dir),
            interactive,
            session_control_mode=session_control_mode,
        )

        payload = {
            "status": status,
            "session_dir": target_dir,
            "session_id": os.path.basename(target_dir),
            "previous_session": current_session,
        }
        emit_operation_timing(
            target_dir,
            feature="lifecycle",
            capability="session_transition",
            feature_set="session_lifecycle_management",
            operation="session_resume",
            duration_ms=(time.perf_counter() - op_started) * 1000.0,
            result="ok",
            source="api",
            metric_name="lifecycle.session_resume.latency",
            tags={"status": status},
        )
        return payload
