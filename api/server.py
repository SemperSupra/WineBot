from fastapi import FastAPI, HTTPException, BackgroundTasks, Security, Depends, Request, Body
from fastapi.security import APIKeyHeader
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel
from typing import Optional, List, Dict, Any
import subprocess
import os
import glob
import time
import datetime
import shlex
import shutil
import platform
import uuid
import json
import re
import fcntl
import signal
import threading

app = FastAPI(title="WineBot API", description="Internal API for controlling WineBot")
START_TIME = time.time()
UI_DIR = os.path.join(os.path.dirname(__file__), "ui")
UI_INDEX = os.path.join(UI_DIR, "index.html")
NOVNC_CORE_DIR = "/usr/share/novnc/core"
NOVNC_VENDOR_DIR = "/usr/share/novnc/vendor"
SESSION_FILE = "/tmp/winebot_current_session"
DEFAULT_SESSION_ROOT = "/artifacts/sessions"

if os.path.isdir(NOVNC_CORE_DIR):
    app.mount("/ui/core", StaticFiles(directory=NOVNC_CORE_DIR), name="novnc-core")
if os.path.isdir(NOVNC_VENDOR_DIR):
    app.mount("/ui/vendor", StaticFiles(directory=NOVNC_VENDOR_DIR), name="novnc-vendor")

# Security
api_key_header = APIKeyHeader(name="X-API-Key", auto_error=False)

async def verify_token(request: Request, api_key: str = Security(api_key_header)):
    if request.url.path.startswith("/ui"):
        return api_key
    expected_token = os.getenv("API_TOKEN")
    if expected_token:
        if not api_key or api_key != expected_token:
            raise HTTPException(status_code=403, detail="Invalid or missing API Token")
    return api_key

# Apply security globally
app.router.dependencies.append(Depends(verify_token))

@app.on_event("startup")
def log_api_startup() -> None:
    session_dir = read_session_dir()
    append_lifecycle_event(session_dir, "api_started", "API server started", source="api")

# Path Safety
ALLOWED_PREFIXES = ["/apps", "/wineprefix", "/tmp", "/artifacts"]

def validate_path(path: str):
    """Ensure path is within allowed directories to prevent traversal."""
    resolved = os.path.abspath(path)
    if not any(resolved.startswith(p) for p in ALLOWED_PREFIXES):
         raise HTTPException(status_code=400, detail=f"Path not allowed. Must start with: {ALLOWED_PREFIXES}")
    return resolved

# Models
class ClickModel(BaseModel):
    x: int
    y: int

class AHKModel(BaseModel):
    script: str
    focus_title: Optional[str] = None

class AutoItModel(BaseModel):
    script: str
    focus_title: Optional[str] = None

class PythonScriptModel(BaseModel):
    script: str

class AppRunModel(BaseModel):
    path: str
    args: Optional[str] = ""
    detach: bool = False

class WinedbgRunModel(BaseModel):
    path: str
    args: Optional[str] = ""
    detach: bool = False
    mode: Optional[str] = "gdb"
    port: Optional[int] = None
    no_start: bool = False
    command: Optional[str] = None
    script: Optional[str] = None

class InspectWindowModel(BaseModel):
    title: Optional[str] = None
    text: Optional[str] = ""
    handle: Optional[str] = None
    include_controls: bool = True
    max_controls: int = 200
    list_only: bool = False
    include_empty: bool = False

class FocusModel(BaseModel):
    window_id: str

class RecordingStartModel(BaseModel):
    session_label: Optional[str] = None
    session_root: Optional[str] = None
    display: Optional[str] = None
    resolution: Optional[str] = None
    fps: Optional[int] = 30
    new_session: Optional[bool] = False

class SessionResumeModel(BaseModel):
    session_id: Optional[str] = None
    session_dir: Optional[str] = None
    session_root: Optional[str] = None
    restart_wine: Optional[bool] = True
    stop_recording: Optional[bool] = True

class SessionSuspendModel(BaseModel):
    session_id: Optional[str] = None
    session_dir: Optional[str] = None
    session_root: Optional[str] = None
    shutdown_wine: Optional[bool] = True
    stop_recording: Optional[bool] = True

# Helpers
def run_command(cmd: List[str]):
    try:
        result = subprocess.run(cmd, capture_output=True, text=True, check=True)
        return result.stdout.strip()
    except subprocess.CalledProcessError as e:
        raise HTTPException(status_code=500, detail=f"Command failed: {e.stderr}")

def safe_command(cmd: List[str], timeout: int = 5) -> Dict[str, Any]:
    try:
        result = subprocess.run(cmd, capture_output=True, text=True, check=True, timeout=timeout)
        return {"ok": True, "stdout": result.stdout.strip(), "stderr": result.stderr.strip()}
    except FileNotFoundError:
        return {"ok": False, "error": "command not found"}
    except subprocess.TimeoutExpired:
        return {"ok": False, "error": "timeout"}
    except subprocess.CalledProcessError as e:
        return {"ok": False, "exit_code": e.returncode, "stdout": e.stdout.strip(), "stderr": e.stderr.strip()}

def check_binary(name: str) -> Dict[str, Any]:
    path = shutil.which(name)
    return {"present": path is not None, "path": path}

def statvfs_info(path: str) -> Dict[str, Any]:
    try:
        st = os.statvfs(path)
        return {
            "path": path,
            "ok": True,
            "total_bytes": st.f_frsize * st.f_blocks,
            "free_bytes": st.f_frsize * st.f_bfree,
            "avail_bytes": st.f_frsize * st.f_bavail,
            "writable": os.access(path, os.W_OK),
        }
    except FileNotFoundError:
        return {"path": path, "ok": False, "error": "not found"}

def meminfo_summary() -> Dict[str, Any]:
    data: Dict[str, Any] = {}
    try:
        with open("/proc/meminfo", "r") as f:
            for line in f:
                if line.startswith("MemTotal:"):
                    data["mem_total_kb"] = int(line.split()[1])
                elif line.startswith("MemAvailable:"):
                    data["mem_available_kb"] = int(line.split()[1])
    except Exception:
        pass
    return data

def parse_resolution(screen: str) -> str:
    if not screen:
        return "1920x1080"
    parts = screen.split("x")
    if len(parts) >= 2:
        return f"{parts[0]}x{parts[1]}"
    return screen

def read_session_dir() -> Optional[str]:
    if not os.path.exists(SESSION_FILE):
        return None
    try:
        with open(SESSION_FILE, "r") as f:
            value = f.read().strip()
        return value or None
    except Exception:
        return None

def write_session_dir(path: str) -> None:
    with open(SESSION_FILE, "w") as f:
        f.write(path)

def read_pid(path: str) -> Optional[int]:
    try:
        with open(path, "r") as f:
            return int(f.read().strip())
    except (FileNotFoundError, ValueError):
        return None

def pid_running(pid: int) -> bool:
    try:
        os.kill(pid, 0)
        return True
    except ProcessLookupError:
        return False
    except PermissionError:
        return True

def recorder_pid(session_dir: str) -> Optional[int]:
    return read_pid(os.path.join(session_dir, "recorder.pid"))

def recorder_running(session_dir: Optional[str]) -> bool:
    if not session_dir:
        return False
    pid = recorder_pid(session_dir)
    return pid is not None and pid_running(pid)

def recorder_state(session_dir: Optional[str]) -> Optional[str]:
    if not session_dir:
        return None
    state_file = os.path.join(session_dir, "recorder.state")
    try:
        with open(state_file, "r") as f:
            return f.read().strip() or None
    except Exception:
        return None

def write_recorder_state(session_dir: str, state: str) -> None:
    try:
        with open(os.path.join(session_dir, "recorder.state"), "w") as f:
            f.write(state)
    except Exception:
        pass

def recording_status(session_dir: Optional[str], enabled: bool) -> Dict[str, Any]:
    if not enabled:
        return {"state": "disabled", "running": False}
    if not session_dir:
        return {"state": "idle", "running": False}
    state = recorder_state(session_dir)
    running = recorder_running(session_dir)
    if running:
        if state == "paused":
            return {"state": "paused", "running": True}
        if state == "stopping":
            return {"state": "stopping", "running": True}
        return {"state": "recording", "running": True}
    if state == "stopping":
        return {"state": "stopping", "running": False}
    return {"state": "idle", "running": False}

def generate_session_id(label: Optional[str]) -> str:
    ts = int(time.time())
    date_prefix = time.strftime("%Y-%m-%d", time.gmtime(ts))
    rand = uuid.uuid4().hex[:6]
    session_id = f"session-{date_prefix}-{ts}-{rand}"
    if label:
        safe = re.sub(r"[^a-zA-Z0-9._-]+", "-", label).strip("-")
        if safe:
            session_id = f"{session_id}-{safe}"
    return session_id

def write_session_manifest(session_dir: str, session_id: str) -> None:
    try:
        manifest = {
            "session_id": session_id,
            "start_time_epoch": time.time(),
            "start_time_iso": datetime.datetime.now(datetime.timezone.utc).isoformat(),
            "hostname": platform.node(),
            "display": os.getenv("DISPLAY", ":99"),
            "resolution": parse_resolution(os.getenv("SCREEN", "1920x1080")),
            "fps": 30,
            "git_sha": None,
        }
        with open(os.path.join(session_dir, "session.json"), "w") as f:
            json.dump(manifest, f, indent=2)
    except Exception:
        pass

def ensure_session_subdirs(session_dir: str) -> None:
    for subdir in ("logs", "screenshots", "scripts", "user"):
        try:
            os.makedirs(os.path.join(session_dir, subdir), exist_ok=True)
        except Exception:
            pass

def session_state_path(session_dir: str) -> str:
    return os.path.join(session_dir, "session.state")

def read_session_state(session_dir: str) -> Optional[str]:
    try:
        with open(session_state_path(session_dir), "r") as f:
            return f.read().strip() or None
    except Exception:
        return None

def write_session_state(session_dir: str, state: str) -> None:
    try:
        with open(session_state_path(session_dir), "w") as f:
            f.write(state)
    except Exception:
        pass

def ensure_user_profile(user_dir: str) -> None:
    paths = [
        os.path.join(user_dir, "AppData", "Roaming"),
        os.path.join(user_dir, "AppData", "Local"),
        os.path.join(user_dir, "AppData", "LocalLow"),
        os.path.join(user_dir, "AppData", "Roaming", "Microsoft", "Windows", "Start Menu", "Programs"),
        os.path.join(user_dir, "Desktop"),
        os.path.join(user_dir, "Documents"),
        os.path.join(user_dir, "Downloads"),
        os.path.join(user_dir, "Music"),
        os.path.join(user_dir, "Pictures"),
        os.path.join(user_dir, "Videos"),
        os.path.join(user_dir, "Contacts"),
        os.path.join(user_dir, "Favorites"),
        os.path.join(user_dir, "Links"),
        os.path.join(user_dir, "Saved Games"),
        os.path.join(user_dir, "Searches"),
        os.path.join(user_dir, "Temp"),
    ]
    for path in paths:
        try:
            if os.path.islink(path):
                os.unlink(path)
            os.makedirs(path, exist_ok=True)
        except Exception:
            pass

def link_wine_user_dir(user_dir: str) -> None:
    wineprefix = os.getenv("WINEPREFIX", "/wineprefix")
    base_dir = os.path.join(wineprefix, "drive_c", "users")
    os.makedirs(base_dir, exist_ok=True)
    wine_user_dir = os.path.join(base_dir, "winebot")
    try:
        if os.path.islink(wine_user_dir):
            os.unlink(wine_user_dir)
        elif os.path.exists(wine_user_dir):
            backup = f"{wine_user_dir}.bak.{int(time.time())}"
            shutil.move(wine_user_dir, backup)
        os.symlink(user_dir, wine_user_dir)
    except Exception:
        pass

def ensure_session_dir(session_root: Optional[str] = None) -> Optional[str]:
    session_dir = read_session_dir()
    if not isinstance(session_dir, str) or not session_dir:
        session_dir = None
    if session_dir and os.path.isdir(session_dir):
        ensure_session_subdirs(session_dir)
        return session_dir
    root = session_root or os.getenv("WINEBOT_SESSION_ROOT", DEFAULT_SESSION_ROOT)
    safe_root = validate_path(root)
    os.makedirs(safe_root, exist_ok=True)
    session_id = generate_session_id(None)
    session_dir = os.path.join(safe_root, session_id)
    os.makedirs(session_dir, exist_ok=True)
    write_session_dir(session_dir)
    write_session_manifest(session_dir, session_id)
    ensure_session_subdirs(session_dir)
    return session_dir

def session_id_from_dir(session_dir: Optional[str]) -> Optional[str]:
    if not session_dir:
        return None
    return os.path.basename(session_dir)

def resolve_session_dir(
    session_id: Optional[str],
    session_dir: Optional[str],
    session_root: Optional[str],
) -> str:
    if session_dir:
        return validate_path(session_dir)
    if not session_id:
        raise HTTPException(status_code=400, detail="Provide session_id or session_dir")
    if "/" in session_id or os.path.sep in session_id or ".." in session_id:
        raise HTTPException(status_code=400, detail="Invalid session_id")
    root = session_root or os.getenv("WINEBOT_SESSION_ROOT", DEFAULT_SESSION_ROOT)
    safe_root = validate_path(root)
    return os.path.join(safe_root, session_id)

def lifecycle_log_path(session_dir: str) -> str:
    return os.path.join(session_dir, "logs", "lifecycle.jsonl")

def append_lifecycle_event(
    session_dir: Optional[str],
    kind: str,
    message: str,
    source: str = "api",
    extra: Optional[Dict[str, Any]] = None,
) -> None:
    if not session_dir:
        return
    event = {
        "timestamp_utc": datetime.datetime.now(datetime.timezone.utc).isoformat(),
        "timestamp_epoch_ms": int(time.time() * 1000),
        "session_id": session_id_from_dir(session_dir),
        "kind": kind,
        "message": message,
        "source": source,
    }
    if extra:
        event["extra"] = extra
    try:
        os.makedirs(os.path.join(session_dir, "logs"), exist_ok=True)
        with open(lifecycle_log_path(session_dir), "a") as f:
            f.write(json.dumps(event) + "\n")
    except Exception:
        pass

def next_segment_index(session_dir: str) -> int:
    index_path = os.path.join(session_dir, "segment_index.txt")
    lock_path = os.path.join(session_dir, "segment_index.lock")
    current = None
    os.makedirs(session_dir, exist_ok=True)
    with open(lock_path, "w") as lock_file:
        try:
            fcntl.flock(lock_file, fcntl.LOCK_EX)
        except Exception:
            pass
        if os.path.exists(index_path):
            try:
                with open(index_path, "r") as f:
                    current = int(f.read().strip())
            except Exception:
                current = None
        if current is None:
            max_idx = 0
            for name in os.listdir(session_dir):
                if name.startswith("video_") and name.endswith(".mkv"):
                    try:
                        idx = int(name.split("_", 1)[1].split(".", 1)[0])
                        max_idx = max(max_idx, idx)
                    except Exception:
                        continue
            current = max_idx + 1
        next_value = current + 1
        try:
            with open(index_path, "w") as f:
                f.write(str(next_value))
        except Exception:
            pass
        try:
            fcntl.flock(lock_file, fcntl.LOCK_UN)
        except Exception:
            pass
    return current

@app.get("/health")
def health_check():
    """High-level health summary."""
    x11 = safe_command(["xdpyinfo"])
    wineprefix = os.getenv("WINEPREFIX", "/wineprefix")
    prefix_ok = os.path.isdir(wineprefix) and os.path.exists(os.path.join(wineprefix, "system.reg"))

    required_tools = ["winedbg", "gdb", "ffmpeg", "xdotool", "wmctrl", "xdpyinfo", "Xvfb"]
    missing = [t for t in required_tools if not check_binary(t)["present"]]

    storage_paths = ["/wineprefix", "/artifacts", "/tmp"]
    storage = [statvfs_info(p) for p in storage_paths]
    storage_ok = all(s.get("ok") and s.get("writable", False) for s in storage)

    status = "ok"
    if not x11.get("ok") or not prefix_ok or missing or not storage_ok:
        status = "degraded"

    return {
        "status": status,
        "x11": "connected" if x11.get("ok") else "unavailable",
        "wineprefix": "ready" if prefix_ok else "missing",
        "tools_ok": len(missing) == 0,
        "missing_tools": missing,
        "storage_ok": storage_ok,
        "uptime_seconds": int(time.time() - START_TIME),
    }

@app.get("/health/system")
def health_system():
    """System-level health details."""
    info = {
        "hostname": platform.node(),
        "pid": os.getpid(),
        "uptime_seconds": int(time.time() - START_TIME),
        "cpu_count": os.cpu_count(),
    }
    try:
        info["loadavg"] = os.getloadavg()
    except OSError:
        pass
    info.update(meminfo_summary())
    return info

@app.get("/health/x11")
def health_x11():
    """X11 health details."""
    x11 = safe_command(["xdpyinfo"])
    wm = safe_command(["pgrep", "-x", "openbox"])
    active = safe_command(["/automation/x11.sh", "active-window"])
    return {
        "display": os.getenv("DISPLAY"),
        "screen": os.getenv("SCREEN"),
        "connected": x11.get("ok", False),
        "xdpyinfo_error": x11.get("error") or x11.get("stderr"),
        "window_manager": {"name": "openbox", "running": wm.get("ok", False)},
        "active_window": active.get("stdout") if active.get("ok") else None,
        "active_window_error": None if active.get("ok") else (active.get("error") or active.get("stderr")),
    }

@app.get("/health/windows")
def health_windows():
    """Window list and active window details."""
    listing = safe_command(["/automation/x11.sh", "list-windows"])
    active = safe_command(["/automation/x11.sh", "active-window"])
    windows = []
    if listing.get("ok") and listing.get("stdout"):
        for line in listing["stdout"].splitlines():
            parts = line.strip().split(" ", 1)
            if len(parts) == 2:
                windows.append({"id": parts[0], "title": parts[1]})
    return {
        "count": len(windows),
        "windows": windows,
        "active_window": active.get("stdout") if active.get("ok") else None,
        "error": None if listing.get("ok") else (listing.get("error") or listing.get("stderr")),
    }

@app.get("/health/wine")
def health_wine():
    """Wine prefix and binary details."""
    wineprefix = os.getenv("WINEPREFIX", "/wineprefix")
    prefix_exists = os.path.isdir(wineprefix)
    system_reg = os.path.join(wineprefix, "system.reg")
    system_reg_exists = os.path.exists(system_reg)
    owner_uid = None
    try:
        owner_uid = os.stat(wineprefix).st_uid
    except Exception:
        pass
    wine_version = safe_command(["wine", "--version"])
    return {
        "wineprefix": wineprefix,
        "prefix_exists": prefix_exists,
        "system_reg_exists": system_reg_exists,
        "prefix_owner_uid": owner_uid,
        "current_uid": os.getuid(),
        "wine_version": wine_version.get("stdout") if wine_version.get("ok") else None,
        "wine_version_error": None if wine_version.get("ok") else (wine_version.get("error") or wine_version.get("stderr")),
        "winearch": os.getenv("WINEARCH"),
    }

@app.get("/health/tools")
def health_tools():
    """Presence and paths of key tooling."""
    tools = ["winedbg", "gdb", "ffmpeg", "xdotool", "wmctrl", "xdpyinfo", "Xvfb", "x11vnc", "websockify"]
    details = {name: check_binary(name) for name in tools}
    missing = [name for name, info in details.items() if not info["present"]]
    return {"ok": len(missing) == 0, "missing": missing, "tools": details}

@app.get("/health/storage")
def health_storage():
    """Disk space and writeability for key paths."""
    paths = ["/wineprefix", "/artifacts", "/tmp"]
    details = [statvfs_info(p) for p in paths]
    ok = all(d.get("ok") and d.get("writable", False) for d in details)
    return {"ok": ok, "paths": details}

@app.get("/health/recording")
def health_recording():
    """Recorder status and current session."""
    session_dir = read_session_dir()
    recorder = safe_command(["pgrep", "-f", "automation.recorder start"])
    enabled = os.getenv("WINEBOT_RECORD", "0") == "1"
    status = recording_status(session_dir, enabled)
    return {
        "enabled": enabled,
        "session_dir": session_dir,
        "session_dir_exists": os.path.isdir(session_dir) if session_dir else False,
        "recorder_running": recorder.get("ok", False),
        "recorder_pids": recorder.get("stdout").splitlines() if recorder.get("ok") and recorder.get("stdout") else [],
        "state": status["state"],
    }

@app.get("/lifecycle/status")
def lifecycle_status():
    """Status for core WineBot components."""
    session_dir = read_session_dir()
    session_id = session_id_from_dir(session_dir)
    wineprefix = os.getenv("WINEPREFIX", "/wineprefix")
    user_dir = os.getenv("WINEBOT_USER_DIR")
    recorder = safe_command(["pgrep", "-f", "automation.recorder start"])
    enabled = os.getenv("WINEBOT_RECORD", "0") == "1"
    record_status = recording_status(session_dir, enabled)
    return {
        "session_id": session_id,
        "session_dir": session_dir,
        "user_dir": user_dir,
        "wine_user_dir": os.path.join(wineprefix, "drive_c", "users", "winebot"),
        "lifecycle_log": lifecycle_log_path(session_dir) if session_dir else None,
        "processes": {
            "xvfb": safe_command(["pgrep", "-x", "Xvfb"]),
            "openbox": safe_command(["pgrep", "-x", "openbox"]),
            "wine_explorer": safe_command(["pgrep", "-f", "explorer.exe"]),
            "x11vnc": safe_command(["pgrep", "-x", "x11vnc"]),
            "novnc": safe_command(["pgrep", "-f", "websockify|novnc_proxy"]),
            "api_pid": os.getpid(),
            "recorder": {
                "enabled": enabled,
                "state": record_status["state"],
                "running": recorder.get("ok", False),
                "pids": recorder.get("stdout").splitlines() if recorder.get("ok") and recorder.get("stdout") else [],
            },
        },
        "can_shutdown": True,
    }

@app.get("/lifecycle/events")
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
    events: List[Dict[str, Any]] = []
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

@app.get("/sessions")
def list_sessions(root: Optional[str] = None, limit: int = 100):
    """List available sessions on disk."""
    if limit < 1:
        raise HTTPException(status_code=400, detail="limit must be >= 1")
    root_dir = root or os.getenv("WINEBOT_SESSION_ROOT", DEFAULT_SESSION_ROOT)
    safe_root = validate_path(root_dir)
    if not os.path.isdir(safe_root):
        return {"root": safe_root, "sessions": []}
    current_session = read_session_dir()
    entries: List[Dict[str, Any]] = []
    for name in os.listdir(safe_root):
        session_dir = os.path.join(safe_root, name)
        if not os.path.isdir(session_dir):
            continue
        session_json = os.path.join(session_dir, "session.json")
        data: Dict[str, Any] = {
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
    return {"root": safe_root, "sessions": entries[:limit]}

@app.post("/sessions/suspend")
def suspend_session(data: Optional[SessionSuspendModel] = Body(default=None)):
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
            stop_recording()
        except Exception:
            pass
    if data.shutdown_wine:
        graceful_wine_shutdown(session_dir)
    write_session_state(session_dir, "suspended")
    append_lifecycle_event(session_dir, "session_suspended", "Session suspended via API", source="api")
    return {"status": "suspended", "session_dir": session_dir, "session_id": os.path.basename(session_dir)}

@app.post("/sessions/resume")
def resume_session(data: Optional[SessionResumeModel] = Body(default=None)):
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
                stop_recording()
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
    return {
        "status": status,
        "session_dir": target_dir,
        "session_id": os.path.basename(target_dir),
        "previous_session": current_session,
    }

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

def graceful_wine_shutdown(session_dir: Optional[str]) -> Dict[str, Any]:
    results: Dict[str, Any] = {}
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
    results: Dict[str, Any] = {}
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

@app.post("/lifecycle/shutdown")
def lifecycle_shutdown(
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
            stop_recording()
        except Exception:
            pass
    component_result = graceful_component_shutdown(session_dir)
    schedule_shutdown(session_dir, delay, signal.SIGTERM)
    response: Dict[str, Any] = {"status": "shutting_down", "delay_seconds": delay}
    if wine_shutdown:
        response["wine_shutdown"] = wine_result
    response["component_shutdown"] = component_result
    return response

@app.get("/ui")
@app.get("/ui/")
def dashboard():
    """Serve the dashboard UI."""
    if not os.path.exists(UI_INDEX):
        raise HTTPException(status_code=404, detail="Dashboard not available")
    return FileResponse(UI_INDEX, media_type="text/html")

@app.get("/windows")
def list_windows():
    """List visible windows."""
    try:
        output = run_command(["/automation/x11.sh", "list-windows"])
        windows = []
        if output:
            for line in output.split("\n"):
                parts = line.strip().split(" ", 1)
                if len(parts) == 2:
                    windows.append({"id": parts[0], "title": parts[1]})
        return {"windows": windows}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/windows/active")
def get_active_window():
    """Get the active window ID."""
    output = run_command(["/automation/x11.sh", "active-window"])
    return {"id": output}

@app.get("/windows/search")
def search_windows(name: str):
    """Search for windows by name pattern."""
    try:
        output = run_command(["/automation/x11.sh", "search", "--name", name])
        ids = output.splitlines() if output else []
        return {"matches": ids}
    except Exception:
        # Search might fail if no windows found? xdotool usually just returns empty
        return {"matches": []}

@app.post("/windows/focus")
def focus_window(data: FocusModel):
    """Focus a window by ID."""
    run_command(["/automation/x11.sh", "focus", data.window_id])
    return {"status": "focused", "id": data.window_id}

@app.get("/apps")
def list_apps(pattern: Optional[str] = None):
    """List installed applications in the Wine prefix."""
    cmd = ["/scripts/list-installed-apps.sh"]
    if pattern:
        cmd.extend(["--pattern", pattern])
    
    try:
        output = run_command(cmd)
        apps = output.splitlines() if output else []
        return {"apps": apps}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/apps/run")
def run_app(data: AppRunModel):
    """Run a Windows application."""
    safe_path = validate_path(data.path)
    
    cmd = ["/scripts/run-app.sh", safe_path]
    if data.detach:
        cmd.append("--detach")
    
    if data.args:
        cmd.extend(["--args", data.args])

    run_command(cmd)
    return {"status": "launched", "path": safe_path}

@app.post("/run/winedbg")
def run_winedbg(data: WinedbgRunModel):
    """Run a Windows application under winedbg."""
    safe_path = validate_path(data.path)

    mode = data.mode or "gdb"
    if mode not in ("gdb", "default"):
        raise HTTPException(status_code=400, detail="Invalid winedbg mode (expected 'gdb' or 'default').")
    if data.command and data.script:
        raise HTTPException(status_code=400, detail="Provide either 'command' or 'script', not both.")
    if (data.command or data.script) and mode != "default":
        raise HTTPException(status_code=400, detail="winedbg command/script requires mode 'default'.")
    if data.port is not None and data.port < 0:
        raise HTTPException(status_code=400, detail="winedbg port must be >= 0.")

    if shutil.which("winedbg"):
        cmd = ["winedbg"]
        if mode == "gdb":
            cmd.append("--gdb")
        if data.port is not None:
            cmd.extend(["--port", str(data.port)])
        if data.no_start:
            cmd.append("--no-start")
        if data.command:
            cmd.extend(["--command", data.command])
        if data.script:
            raise HTTPException(status_code=400, detail="winedbg script files are not supported in direct mode; use command instead.")
        cmd.append(safe_path)
        if data.args:
            cmd.extend(shlex.split(data.args))
        if data.detach:
            subprocess.Popen(cmd)
            return {"status": "launched", "path": safe_path, "mode": mode, "detached": True}
        run_command(cmd)
        return {"status": "launched", "path": safe_path, "mode": mode}

    cmd = ["/scripts/run-app.sh", safe_path, "--winedbg", "--winedbg-mode", mode]
    if data.detach:
        cmd.append("--detach")
    if data.args:
        cmd.extend(["--args", data.args])
    if data.port is not None:
        cmd.extend(["--winedbg-port", str(data.port)])
    if data.no_start:
        cmd.append("--winedbg-no-start")
    if data.command:
        cmd.extend(["--winedbg-command", data.command])
    if data.script:
        cmd.extend(["--winedbg-script", data.script])

    run_command(cmd)
    return {"status": "launched", "path": safe_path, "mode": mode}

@app.post("/run/python")
def run_python(data: PythonScriptModel):
    """Run a script using Windows Python (winpy)."""
    session_dir = ensure_session_dir()
    script_dir = os.path.join(session_dir, "scripts") if session_dir else "/tmp"
    log_dir = os.path.join(session_dir, "logs") if session_dir else "/tmp"
    os.makedirs(script_dir, exist_ok=True)
    os.makedirs(log_dir, exist_ok=True)
    script_path = os.path.join(script_dir, f"api_script_{int(time.time())}.py")
    log_path = os.path.join(log_dir, f"{os.path.basename(script_path)}.log")
    
    with open(script_path, "w") as f:
        f.write(data.script)
    
    # Run using winpy wrapper
    cmd = ["winpy", script_path]
    
    try:
        result = subprocess.run(cmd, capture_output=True, text=True, check=True)
        with open(log_path, "w") as f:
            f.write(result.stdout or "")
            if result.stderr:
                f.write("\n--- stderr ---\n")
                f.write(result.stderr)
        return {"status": "success", "stdout": result.stdout, "stderr": result.stderr, "log_path": log_path}
    except subprocess.CalledProcessError as e:
        with open(log_path, "w") as f:
            f.write(e.stdout or "")
            if e.stderr:
                f.write("\n--- stderr ---\n")
                f.write(e.stderr)
        return {"status": "error", "exit_code": e.returncode, "stdout": e.stdout, "stderr": e.stderr, "log_path": log_path}

@app.get("/screenshot")
def get_screenshot(
    window_id: str = "root",
    delay: int = 0,
    label: Optional[str] = None,
    tag: Optional[str] = None,
    output_dir: Optional[str] = None,
    session_root: Optional[str] = None,
):
    """Take a screenshot and return the image."""
    request_id = uuid.uuid4().hex
    filename = f"screenshot_{int(time.time())}.png"
    session_dir = None
    if output_dir is None:
        session_dir = ensure_session_dir(session_root)

    if output_dir:
        target_dir = output_dir
    elif session_dir:
        target_dir = os.path.join(session_dir, "screenshots")
    else:
        target_dir = "/tmp"

    safe_dir = validate_path(target_dir)
    os.makedirs(safe_dir, exist_ok=True)
    filepath = os.path.join(safe_dir, filename)
    
    cmd = ["/automation/screenshot.sh", "--window", window_id, "--delay", str(delay)]
    if label:
        cmd.extend(["--label", label])
    cmd.extend(["--request-id", request_id])
    if tag:
        cmd.extend(["--tag", tag])
    cmd.append(filepath)
    
    run_command(cmd)
    
    if not os.path.exists(filepath):
        raise HTTPException(status_code=500, detail="Screenshot failed to generate")

    return FileResponse(
        filepath,
        media_type="image/png",
        headers={
            "X-Request-Id": request_id,
            "X-Screenshot-Path": filepath,
            "X-Screenshot-Metadata-Path": f"{filepath}.json",
        },
    )

@app.post("/recording/start")
def start_recording(data: Optional[RecordingStartModel] = Body(default=None)):
    """Start a recording session."""
    if data is None:
        data = RecordingStartModel()
    current_session = read_session_dir()
    if recorder_running(current_session):
        if recorder_state(current_session) == "paused":
            cmd = ["python3", "-m", "automation.recorder", "resume", "--session-dir", current_session]
            result = subprocess.run(cmd, capture_output=True, text=True)
            if result.returncode != 0:
                raise HTTPException(status_code=500, detail=(result.stderr or "Failed to resume recorder"))
            return {"status": "resumed", "session_dir": current_session}
        return {"status": "already_recording", "session_dir": current_session}

    session_dir = None
    if not data.new_session and current_session and os.path.isdir(current_session):
        session_json = os.path.join(current_session, "session.json")
        if os.path.exists(session_json):
            session_dir = current_session

    if session_dir is None:
        session_root = data.session_root or os.getenv("WINEBOT_SESSION_ROOT", DEFAULT_SESSION_ROOT)
        os.makedirs(session_root, exist_ok=True)
        session_id = generate_session_id(data.session_label)
        session_dir = os.path.join(session_root, session_id)
        os.makedirs(session_dir, exist_ok=True)
        write_session_dir(session_dir)
        write_session_manifest(session_dir, session_id)
        ensure_session_subdirs(session_dir)
    else:
        session_id = os.path.basename(session_dir)
        ensure_session_subdirs(session_dir)

    display = data.display or os.getenv("DISPLAY", ":99")
    screen = data.resolution or os.getenv("SCREEN", "1920x1080")
    resolution = parse_resolution(screen)
    fps = data.fps or 30
    segment = next_segment_index(session_dir)
    segment_suffix = f"{segment:03d}"
    output_file = os.path.join(session_dir, f"video_{segment_suffix}.mkv")
    events_file = os.path.join(session_dir, f"events_{segment_suffix}.jsonl")

    cmd = [
        "python3", "-m", "automation.recorder", "start",
        "--session-dir", session_dir,
        "--display", display,
        "--resolution", resolution,
        "--fps", str(fps),
        "--segment", str(segment),
    ]
    subprocess.Popen(cmd)

    pid = None
    pid_file = os.path.join(session_dir, "recorder.pid")
    for _ in range(10):
        pid = read_pid(pid_file)
        if pid:
            break
        time.sleep(0.1)

    return {
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

@app.post("/recording/stop")
def stop_recording():
    """Stop the active recording session."""
    session_dir = read_session_dir()
    if not session_dir:
        return {"status": "already_stopped"}
    if not recorder_running(session_dir):
        write_recorder_state(session_dir, "idle")
        return {"status": "already_stopped", "session_dir": session_dir}

    write_recorder_state(session_dir, "stopping")
    cmd = ["python3", "-m", "automation.recorder", "stop", "--session-dir", session_dir]
    result = subprocess.run(cmd, capture_output=True, text=True)
    if result.returncode != 0:
        raise HTTPException(status_code=500, detail=(result.stderr or "Failed to stop recorder"))

    for _ in range(10):
        if not recorder_running(session_dir):
            write_recorder_state(session_dir, "idle")
            break
        time.sleep(0.2)

    return {"status": "stopped", "session_dir": session_dir}

@app.post("/recording/pause")
def pause_recording():
    """Pause the active recording session."""
    session_dir = read_session_dir()
    if not session_dir:
        return {"status": "idle"}
    if not recorder_running(session_dir):
        return {"status": "already_paused", "session_dir": session_dir}
    if recorder_state(session_dir) == "paused":
        return {"status": "already_paused", "session_dir": session_dir}
    cmd = ["python3", "-m", "automation.recorder", "pause", "--session-dir", session_dir]
    result = subprocess.run(cmd, capture_output=True, text=True)
    if result.returncode != 0:
        raise HTTPException(status_code=500, detail=(result.stderr or "Failed to pause recorder"))
    return {"status": "paused", "session_dir": session_dir}

@app.post("/recording/resume")
def resume_recording():
    """Resume the active recording session."""
    session_dir = read_session_dir()
    if not session_dir:
        return {"status": "idle"}
    if not recorder_running(session_dir):
        return {"status": "idle", "session_dir": session_dir}
    if recorder_state(session_dir) != "paused":
        return {"status": "already_recording", "session_dir": session_dir}
    cmd = ["python3", "-m", "automation.recorder", "resume", "--session-dir", session_dir]
    result = subprocess.run(cmd, capture_output=True, text=True)
    if result.returncode != 0:
        raise HTTPException(status_code=500, detail=(result.stderr or "Failed to resume recorder"))
    return {"status": "resumed", "session_dir": session_dir}

@app.post("/input/mouse/click")
def click_at(data: ClickModel):
    """Click at coordinates (x, y)."""
    run_command(["/automation/x11.sh", "click-at", str(data.x), str(data.y)])
    return {"status": "clicked", "x": data.x, "y": data.y}

@app.post("/run/ahk")
def run_ahk(data: AHKModel):
    """Run an AutoHotkey script."""
    # Write script to temp file
    session_dir = ensure_session_dir()
    script_dir = os.path.join(session_dir, "scripts") if session_dir else "/tmp"
    log_dir = os.path.join(session_dir, "logs") if session_dir else "/tmp"
    os.makedirs(script_dir, exist_ok=True)
    os.makedirs(log_dir, exist_ok=True)
    script_path = os.path.join(script_dir, f"api_script_{int(time.time())}.ahk")
    log_path = os.path.join(log_dir, f"{os.path.basename(script_path)}.log")
    
    with open(script_path, "w") as f:
        f.write(data.script)
        
    cmd = ["/scripts/run-ahk.sh", script_path, "--log", log_path]
    if data.focus_title:
        cmd.extend(["--focus-title", data.focus_title])
        
    try:
        subprocess.run(cmd, check=True, capture_output=True, text=True)
        # Read log
        log_content = ""
        if os.path.exists(log_path):
            with open(log_path, "r") as f:
                log_content = f.read()
        return {"status": "success", "log": log_content}
    except subprocess.CalledProcessError as e:
        # Read log even on failure
        log_content = ""
        if os.path.exists(log_path):
            with open(log_path, "r") as f:
                log_content = f.read()
        return {"status": "error", "exit_code": e.returncode, "stderr": e.stderr, "log": log_content}

@app.post("/run/autoit")
def run_autoit(data: AutoItModel):
    """Run an AutoIt script."""
    # Write script to temp file
    session_dir = ensure_session_dir()
    script_dir = os.path.join(session_dir, "scripts") if session_dir else "/tmp"
    log_dir = os.path.join(session_dir, "logs") if session_dir else "/tmp"
    os.makedirs(script_dir, exist_ok=True)
    os.makedirs(log_dir, exist_ok=True)
    script_path = os.path.join(script_dir, f"api_script_{int(time.time())}.au3")
    log_path = os.path.join(log_dir, f"{os.path.basename(script_path)}.log")
    
    with open(script_path, "w") as f:
        f.write(data.script)
        
    cmd = ["/scripts/run-autoit.sh", script_path, "--log", log_path]
    if data.focus_title:
        cmd.extend(["--focus-title", data.focus_title])
        
    try:
        subprocess.run(cmd, check=True, capture_output=True, text=True)
        # Read log
        log_content = ""
        if os.path.exists(log_path):
            with open(log_path, "r") as f:
                log_content = f.read()
        return {"status": "success", "log": log_content}
    except subprocess.CalledProcessError as e:
        # Read log even on failure
        log_content = ""
        if os.path.exists(log_path):
            with open(log_path, "r") as f:
                log_content = f.read()
        return {"status": "error", "exit_code": e.returncode, "stderr": e.stderr, "log": log_content}

@app.post("/inspect/window")
def inspect_window(data: InspectWindowModel):
    """Inspect a Windows window and its controls (WinSpy-style)."""
    if not data.list_only and not data.title and not data.handle:
        raise HTTPException(status_code=400, detail="Provide 'title' or 'handle', or set list_only=true.")

    script_path = "/automation/inspect_window.au3"
    session_dir = ensure_session_dir()
    log_dir = os.path.join(session_dir, "logs") if session_dir else "/tmp"
    os.makedirs(log_dir, exist_ok=True)
    log_path = os.path.join(log_dir, f"api_inspect_{int(time.time())}.log")

    cmd = ["/scripts/run-autoit.sh", script_path, "--log", log_path]
    if data.list_only:
        cmd.append("--list")
    if data.include_empty:
        cmd.append("--include-empty")
    if data.title:
        cmd.extend(["--title", data.title])
    if data.text:
        cmd.extend(["--text", data.text])
    if data.handle:
        cmd.extend(["--handle", data.handle])
    if not data.include_controls:
        cmd.append("--no-controls")
    if data.max_controls is not None:
        cmd.extend(["--max-controls", str(data.max_controls)])

    try:
        subprocess.run(cmd, check=True, capture_output=True, text=True)
    except subprocess.CalledProcessError as e:
        log_content = ""
        if os.path.exists(log_path):
            with open(log_path, "r") as f:
                log_content = f.read()
        return {"status": "error", "exit_code": e.returncode, "stderr": e.stderr, "log": log_content}

    if not os.path.exists(log_path):
        raise HTTPException(status_code=500, detail="Inspect log not found.")

    with open(log_path, "r") as f:
        log_content = f.read().strip()
    if not log_content:
        return {"status": "error", "log": ""}

    try:
        payload = json.loads(log_content)
    except json.JSONDecodeError:
        return {"status": "error", "log": log_content}

    return {"status": "success", "result": payload}
