from fastapi import APIRouter, HTTPException, BackgroundTasks, Body
from typing import Dict, Any, Optional
import os
import signal
import threading
import time
import subprocess
from api.utils.files import (read_session_dir, session_id_from_dir, lifecycle_log_path, append_lifecycle_event, 
                             resolve_session_dir, ensure_session_subdirs, ensure_user_profile, write_session_dir,
                             write_session_manifest, link_wine_user_dir, write_session_state, recorder_running,
                             read_session_state)
from api.utils.process import safe_command, find_processes
from api.core.recorder import stop_recording
from api.core.broker import broker
from api.core.models import SessionSuspendModel, SessionResumeModel

router = APIRouter(tags=["lifecycle"])

# --- Lifecycle Logic ---

def graceful_wine_shutdown(session_dir: Optional[str]) -> Dict[str, Any]:
    results = {}
    append_lifecycle_event(session_dir, "wine_shutdown_requested", "Requesting Wine shutdown", source="api")
    wineboot = safe_command(["wineboot", "--shutdown"], timeout=10)
    results["wineboot"] = wineboot
    if wineboot.get("ok"):
        append_lifecycle_event(session_dir, "wine_shutdown_complete", "Wine shutdown complete", source="api")
    else:
        append_lifecycle_event(session_dir, "wine_shutdown_failed", "Wine shutdown failed", source="api", extra=wineboot)
    wineserver = safe_command(["wineserver", "-k"], timeout=5)
    results["wineserver"] = wineserver
    if wineserver.get("ok"):
        append_lifecycle_event(session_dir, "wineserver_killed", "wineserver -k completed", source="api")
    else:
        append_lifecycle_event(session_dir, "wineserver_kill_failed", "wineserver -k failed", source="api", extra=wineserver)
    return results

def graceful_component_shutdown(session_dir: Optional[str]) -> Dict[str, Any]:
    results = {}
    append_lifecycle_event(session_dir, "component_shutdown_requested", "Stopping UI/VNC components", source="api")
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
            append_lifecycle_event(session_dir, f"{name}_stopped", f"{name} stopped", source="api")
        else:
            append_lifecycle_event(session_dir, f"{name}_stop_failed", f"{name} stop failed", source="api", extra=result)
    return results

def _shutdown_process(session_dir: Optional[str], delay: float, sig: int = signal.SIGTERM) -> None:
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
    thread = threading.Thread(target=_shutdown_process, args=(session_dir, delay, sig), daemon=True)
    thread.start()
    try:
        subprocess.Popen(
            ["/bin/sh", "-c", f"sleep {max(0.0, delay)}; kill -{int(sig)} 1"],
            start_new_session=True,
        )
    except Exception:
        pass

@router.get("/lifecycle/status")
async def lifecycle_status():
    """Alias for high-level health."""
    from api.routers.health import health_check
    return health_check()

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
    events = []
    try:
        with open(path, "r") as f:
            lines = f.read().splitlines()
        for line in lines[-limit:]:
            try:
                events.append(json.loads(line))
            except json.JSONDecodeError:
                continue
    except Exception:
        pass
    return {"events": events}

@router.post("/lifecycle/shutdown")
async def lifecycle_shutdown(
    background_tasks: BackgroundTasks,
    delay: float = 0.5,
    wine_shutdown: bool = True,
    power_off: bool = False,
):
    """Gracefully stop components and terminate the container process."""
    session_dir = read_session_dir()
    append_lifecycle_event(session_dir, "shutdown_requested", "Shutdown requested via API", source="api")
    if power_off:
        append_lifecycle_event(session_dir, "power_off", "Immediate shutdown requested", source="api")
        tail_kill = safe_command(["pkill", "-9", "-f", "tail -f /dev/null"])
        append_lifecycle_event(
            session_dir,
            "power_off_keepalive_kill",
            "Attempted to stop keepalive process",
            source="api",
            extra=tail_kill,
        )
        schedule_shutdown(session_dir, max(0.0, delay), signal.SIGKILL)
        return {"status": "powering_off", "delay_seconds": delay}

    wine_result = None
    component_result = None
    if wine_shutdown:
        wine_result = graceful_wine_shutdown(session_dir)
    if session_dir and recorder_running(session_dir):
        try:
            await stop_recording()
        except Exception:
            pass
    component_result = graceful_component_shutdown(session_dir)
    schedule_shutdown(session_dir, delay, signal.SIGTERM)
    response: Dict[str, Any] = {"status": "shutting_down", "delay_seconds": delay}
    if wine_shutdown:
        response["wine_shutdown"] = wine_result
    response["component_shutdown"] = component_result
    return response

@router.post("/lifecycle/reset_workspace")
async def reset_workspace():
    """Force Wine desktop to be maximized and undecorated."""
    screen = os.environ.get("SCREEN", "1280x720x24").split("x")
    w, h = screen[0], screen[1]
    
    # Start explorer if missing
    if not find_processes("explorer"):
        subprocess.Popen(["wine", "explorer.exe"], 
                         stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                         start_new_session=True)
        await asyncio.sleep(3)

    # Force geometry update (mostly for windowed mode now)
    subprocess.run(["xdotool", "search", "--class", "explorer", "windowmove", "0", "0"], capture_output=True)
    
    return {"status": "ok", "message": f"Workspace reset requested"}

@router.get("/sessions")
def list_sessions(root: Optional[str] = None, limit: int = 100):
    """List available sessions on disk."""
    if limit < 1:
        raise HTTPException(status_code=400, detail="limit must be >= 1")
    root_dir = root or os.getenv("WINEBOT_SESSION_ROOT", "/artifacts/sessions")
    # safe_root validation logic moved to files.py if needed, or inline here
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
async def suspend_session(data: Optional[SessionSuspendModel] = Body(default=None)):
    """Suspend a session without terminating the container."""
    if data is None:
        data = SessionSuspendModel()
    current_session = read_session_dir()
    session_dir = resolve_session_dir(data.session_id, data.session_dir, data.session_root) if (
        data.session_id or data.session_dir
    ) else current_session
    if not session_dir:
        raise HTTPException(status_code=404, detail="No active session to suspend")
    if not os.path.isdir(session_dir):
        raise HTTPException(status_code=404, detail="Session directory not found")

    if data.stop_recording and session_dir == current_session and recorder_running(session_dir):
        try:
            await stop_recording()
        except Exception:
            pass
    if data.shutdown_wine:
        graceful_wine_shutdown(session_dir)
    write_session_state(session_dir, "suspended")
    append_lifecycle_event(session_dir, "session_suspended", "Session suspended via API", source="api")
    return {"status": "suspended", "session_dir": session_dir, "session_id": os.path.basename(session_dir)}

@router.post("/sessions/resume")
async def resume_session(data: Optional[SessionResumeModel] = Body(default=None)):
    """Resume an existing session directory."""
    if data is None:
        data = SessionResumeModel()
    current_session = read_session_dir()
    target_dir = resolve_session_dir(data.session_id, data.session_dir, data.session_root)
    if not os.path.isdir(target_dir):
        raise HTTPException(status_code=404, detail="Session directory not found")
    session_json = os.path.join(target_dir, "session.json")
    if not os.path.exists(session_json):
        write_session_manifest(target_dir, os.path.basename(target_dir))
    ensure_session_subdirs(target_dir)
    user_dir = os.path.join(target_dir, "user")
    os.makedirs(user_dir, exist_ok=True)
    ensure_user_profile(user_dir)

    if current_session and current_session != target_dir:
        if data.stop_recording and recorder_running(current_session):
            try:
                await stop_recording()
            except Exception:
                pass
        write_session_state(current_session, "suspended")
        append_lifecycle_event(current_session, "session_suspended", "Session suspended via API", source="api")
        if data.restart_wine:
            graceful_wine_shutdown(current_session)

    write_session_dir(target_dir)
    os.environ["WINEBOT_SESSION_DIR"] = target_dir
    os.environ["WINEBOT_SESSION_ID"] = os.path.basename(target_dir)
    os.environ["WINEBOT_USER_DIR"] = user_dir
    link_wine_user_dir(user_dir)
    write_session_state(target_dir, "active")
    append_lifecycle_event(target_dir, "session_resumed", "Session resumed via API", source="api")

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
    await broker.update_session(os.path.basename(target_dir), interactive)

    return {
        "status": status,
        "session_dir": target_dir,
        "session_id": os.path.basename(target_dir),
        "previous_session": current_session,
    }
