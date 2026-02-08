from fastapi import FastAPI, HTTPException, BackgroundTasks, Security, Depends, Request, Body
from fastapi.security import APIKeyHeader
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel
from typing import Optional, List, Dict, Any
from contextlib import asynccontextmanager
import subprocess
import os
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
import asyncio
import hashlib
from enum import Enum
from functools import lru_cache

START_TIME = time.time()
UI_DIR = os.path.join(os.path.dirname(__file__), "ui")
UI_INDEX = os.path.join(UI_DIR, "index.html")
NOVNC_CORE_DIR = "/usr/share/novnc/core"
NOVNC_VENDOR_DIR = "/usr/share/novnc/vendor"
SESSION_FILE = "/tmp/winebot_current_session"
DEFAULT_SESSION_ROOT = "/artifacts/sessions"

def _load_version():
    try:
        with open("/VERSION", "r") as f:
            return f.read().strip()
    except Exception:
        return "v0.9.0-dev"

VERSION = _load_version()


class RecorderState(str, Enum):
    IDLE = "idle"
    RECORDING = "recording"
    PAUSED = "paused"
    STOPPING = "stopping"


class ControlMode(str, Enum):
    USER = "USER"
    AGENT = "AGENT"


class UserIntent(str, Enum):
    WAIT = "WAIT"
    SAFE_INTERRUPT = "SAFE_INTERRUPT"
    STOP_NOW = "STOP_NOW"


class AgentStatus(str, Enum):
    IDLE = "IDLE"
    RUNNING = "RUNNING"
    PAUSED = "PAUSED"
    STOPPING = "STOPPING"
    STOPPED = "STOPPED"


class ControlState(BaseModel):
    session_id: str
    interactive: bool
    control_mode: ControlMode
    lease_expiry: Optional[float] = None
    user_intent: UserIntent
    agent_status: AgentStatus


class GrantControlModel(BaseModel):
    lease_seconds: int


class UserIntentModel(BaseModel):
    intent: UserIntent


class InputBroker:
    def __init__(self):
        self._lock = asyncio.Lock()
        self.state = ControlState(
            session_id="unknown",
            interactive=False,
            control_mode=ControlMode.USER,
            user_intent=UserIntent.WAIT,
            agent_status=AgentStatus.IDLE
        )
        self.last_user_activity = 0.0

    async def update_session(self, session_id: str, interactive: bool):
        async with self._lock:
            self.state.session_id = session_id
            self.state.interactive = interactive
            # If not interactive, default to AGENT allowed, else USER
            if not interactive:
                self.state.control_mode = ControlMode.AGENT
            else:
                # If switching to interactive, revoke agent
                if self.state.control_mode == ControlMode.AGENT:
                    self.revoke_agent("session_became_interactive")
                self.state.control_mode = ControlMode.USER

    async def grant_agent(self, lease_seconds: int):
        async with self._lock:
            if not self.state.interactive:
                return  # Always implicit in non-interactive
            self.state.control_mode = ControlMode.AGENT
            self.state.lease_expiry = time.time() + lease_seconds
            self.state.user_intent = UserIntent.WAIT

    async def renew_agent(self, lease_seconds: int):
        async with self._lock:
            if self.state.control_mode != ControlMode.AGENT:
                raise HTTPException(status_code=403, detail="Agent does not hold control")
            if self.state.user_intent == UserIntent.STOP_NOW:
                raise HTTPException(status_code=403, detail="User requested STOP_NOW")
            self.state.lease_expiry = time.time() + lease_seconds

    def revoke_agent(self, reason: str):
        # Sync version for internal calls
        self.state.control_mode = ControlMode.USER
        self.state.lease_expiry = None
        self.state.agent_status = AgentStatus.STOPPING
        print(f"Broker: Agent revoked ({reason})")

    async def report_user_activity(self):
        self.last_user_activity = time.time()
        if self.state.control_mode == ControlMode.AGENT:
            async with self._lock:
                self.revoke_agent("user_input_override")

    async def set_user_intent(self, intent: UserIntent):
        async with self._lock:
            self.state.user_intent = intent
            if intent == UserIntent.STOP_NOW:
                self.revoke_agent("user_stop_now")

    async def check_access(self) -> bool:
        """Returns True if agent is allowed to execute."""
        if not self.state.interactive:
            return True
        
        async with self._lock:
            if self.state.control_mode != ControlMode.AGENT:
                return False
            if self.state.lease_expiry and time.time() > self.state.lease_expiry:
                self.revoke_agent("lease_expired")
                return False
            if self.state.user_intent == UserIntent.STOP_NOW:
                self.revoke_agent("user_stop_now")
                return False
            return True

    def get_state(self) -> ControlState:
        return self.state


broker = InputBroker()


# --- Concurrency & Resource Management ---
recorder_lock = asyncio.Lock()
# Store strong references to Popen objects to prevent them from being GC'd
# and to allow reaping zombies.
process_store = set()


def manage_process(proc: subprocess.Popen):
    """Track a detached process to ensure it is reaped later."""
    process_store.add(proc)


async def run_async_command(cmd: List[str]) -> Dict[str, Any]:
    """Run a command asynchronously without blocking the event loop."""
    try:
        proc = await asyncio.create_subprocess_exec(
            *cmd,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE
        )
        stdout, stderr = await proc.communicate()
        return {
            "returncode": proc.returncode,
            "stdout": stdout.decode().strip(),
            "stderr": stderr.decode().strip(),
            "ok": proc.returncode == 0
        }
    except Exception as e:
        return {"returncode": -1, "stdout": "", "stderr": str(e), "ok": False}


def find_processes(pattern: str, exact: bool = False) -> List[int]:
    """Find PIDs of processes matching a name or command line pattern (pure Python pgrep)."""
    pids = []
    try:
        for pid_str in os.listdir('/proc'):
            if not pid_str.isdigit():
                continue
            pid = int(pid_str)
            try:
                # Check comm (short name) for exact match
                if exact:
                    with open(f'/proc/{pid}/comm', 'r') as f:
                        comm = f.read().strip()
                        if comm == pattern:
                            pids.append(pid)
                            continue

                # Check cmdline for full match
                with open(f'/proc/{pid}/cmdline', 'rb') as f:
                    # cmdline is null-separated
                    cmd_bytes = f.read()
                    cmd = cmd_bytes.replace(b'\0', b' ').decode('utf-8', errors='ignore').strip()
                    if pattern in cmd:
                        pids.append(pid)
            except (FileNotFoundError, ProcessLookupError, PermissionError):
                continue
    except Exception:
        pass
    return pids


async def resource_monitor_task():
    """Background task to reap zombies and monitor disk usage."""
    while True:
        # 1. Reap zombie processes
        # We iterate a copy because we might remove items
        for proc in list(process_store):
            if proc.poll() is not None:
                # Process finished, returncode is set, zombie reaped.
                process_store.discard(proc)

        # 2. Disk Space Watchdog
        # If recording is active and disk is low (< 300MB), stop recording.
        session_dir = read_session_dir()
        if session_dir and recorder_running(session_dir):
            try:
                st = os.statvfs(session_dir)
                free_mb = (st.f_bavail * st.f_frsize) / (1024 * 1024)
                if free_mb < 300:
                    print(f"WARNING: Low disk space ({free_mb:.1f}MB). Stopping recorder.")
                    append_lifecycle_event(session_dir, "recorder_force_stop", f"Low disk space ({free_mb:.1f}MB)", source="api_watchdog")
                    write_recorder_state(session_dir, RecorderState.STOPPING.value)
                    # We can't await inside this sync-ish loop structure easily for subprocess if using run_async_command
                    # because we are in an async def, so we CAN await.
                    # But we need to import command properly.
                    await run_async_command(["python3", "-m", "automation.recorder", "stop", "--session-dir", session_dir])
            except Exception:
                pass

        await asyncio.sleep(5)


@asynccontextmanager
async def lifespan(app: FastAPI):
    session_dir = read_session_dir()
    append_lifecycle_event(session_dir, "api_started", "API server started", source="api")

    # Start background monitor
    monitor = asyncio.create_task(resource_monitor_task())

    try:
        yield
    finally:
        monitor.cancel()
        session_dir = read_session_dir()
        append_lifecycle_event(session_dir, "api_stopped", "API server stopping", source="api")


app = FastAPI(title="WineBot API", description="Internal API for controlling WineBot", lifespan=lifespan)

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

class InputTraceStartModel(BaseModel):
    session_id: Optional[str] = None
    session_dir: Optional[str] = None
    session_root: Optional[str] = None
    include_raw: Optional[bool] = False
    motion_sample_ms: Optional[int] = 0

class InputTraceX11CoreStartModel(BaseModel):
    session_id: Optional[str] = None
    session_dir: Optional[str] = None
    session_root: Optional[str] = None
    motion_sample_ms: Optional[int] = 0

class InputTraceX11CoreStopModel(BaseModel):
    session_id: Optional[str] = None
    session_dir: Optional[str] = None
    session_root: Optional[str] = None

class InputTraceStopModel(BaseModel):
    session_id: Optional[str] = None
    session_dir: Optional[str] = None
    session_root: Optional[str] = None

class InputTraceClientStartModel(BaseModel):
    session_id: Optional[str] = None
    session_dir: Optional[str] = None
    session_root: Optional[str] = None

class InputTraceClientStopModel(BaseModel):
    session_id: Optional[str] = None
    session_dir: Optional[str] = None
    session_root: Optional[str] = None

class InputTraceWindowsStartModel(BaseModel):
    session_id: Optional[str] = None
    session_dir: Optional[str] = None
    session_root: Optional[str] = None
    motion_sample_ms: Optional[int] = 10
    debug_keys: Optional[List[str]] = None
    debug_keys_csv: Optional[str] = None
    debug_sample_ms: Optional[int] = 200
    backend: Optional[str] = None

class InputTraceWindowsStopModel(BaseModel):
    session_id: Optional[str] = None
    session_dir: Optional[str] = None
    session_root: Optional[str] = None

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

@lru_cache(maxsize=None)
def check_binary(name: str) -> Dict[str, Any]:
    path = shutil.which(name)
    return {"present": path is not None, "path": path}


async def safe_async_command(cmd: List[str], timeout: int = 5) -> Dict[str, Any]:
    try:
        # Use run_async_command logic but adapted for the 'safe_command' return signature
        proc = await asyncio.create_subprocess_exec(
            *cmd,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE
        )
        try:
            stdout, stderr = await asyncio.wait_for(proc.communicate(), timeout=timeout)
            return {"ok": proc.returncode == 0, "stdout": stdout.decode().strip(), "stderr": stderr.decode().strip()}
        except asyncio.TimeoutError:
            try:
                proc.kill()
            except ProcessLookupError:
                pass
            return {"ok": False, "error": "timeout"}
    except FileNotFoundError:
        return {"ok": False, "error": "command not found"}
    except Exception as e:
        return {"ok": False, "error": str(e)}


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
        return {"state": RecorderState.IDLE.value, "running": False}
    state = recorder_state(session_dir)
    running = recorder_running(session_dir)
    if running:
        if state == RecorderState.PAUSED.value:
            return {"state": RecorderState.PAUSED.value, "running": True}
        if state == RecorderState.STOPPING.value:
            return {"state": RecorderState.STOPPING.value, "running": True}
        return {"state": RecorderState.RECORDING.value, "running": True}
    if state == RecorderState.STOPPING.value:
        return {"state": RecorderState.STOPPING.value, "running": False}
    return {"state": RecorderState.IDLE.value, "running": False}


def input_trace_pid(session_dir: str) -> Optional[int]:
    return read_pid(os.path.join(session_dir, "input_trace.pid"))


def input_trace_running(session_dir: Optional[str]) -> bool:
    if not session_dir:
        return False
    pid = input_trace_pid(session_dir)
    return pid is not None and pid_running(pid)


def input_trace_state(session_dir: Optional[str]) -> Optional[str]:
    if not session_dir:
        return None
    state_file = os.path.join(session_dir, "input_trace.state")
    try:
        with open(state_file, "r") as f:
            return f.read().strip() or None
    except Exception:
        return None


def input_trace_log_path(session_dir: str) -> str:
    return os.path.join(session_dir, "logs", "input_events.jsonl")

def input_trace_x11_core_log_path(session_dir: str) -> str:
    return os.path.join(session_dir, "logs", "input_events_x11_core.jsonl")


def input_trace_client_log_path(session_dir: str) -> str:
    return os.path.join(session_dir, "logs", "input_events_client.jsonl")


def input_trace_client_state_path(session_dir: str) -> str:
    return os.path.join(session_dir, "input_trace_client.state")


def input_trace_windows_log_path(session_dir: str) -> str:
    return os.path.join(session_dir, "logs", "input_events_windows.jsonl")


def input_trace_windows_pid_path(session_dir: str) -> str:
    return os.path.join(session_dir, "input_trace_windows.pid")

def input_trace_x11_core_pid_path(session_dir: str) -> str:
    return os.path.join(session_dir, "input_trace_x11_core.pid")

def input_trace_x11_core_state_path(session_dir: str) -> str:
    return os.path.join(session_dir, "input_trace_x11_core.state")

def input_trace_network_log_path(session_dir: str) -> str:
    return os.path.join(session_dir, "logs", "input_events_network.jsonl")


def input_trace_network_pid_path(session_dir: str) -> str:
    return os.path.join(session_dir, "input_trace_network.pid")


def input_trace_network_state_path(session_dir: str) -> str:
    return os.path.join(session_dir, "input_trace_network.state")


def input_trace_windows_state_path(session_dir: str) -> str:
    return os.path.join(session_dir, "input_trace_windows.state")

def input_trace_windows_backend_path(session_dir: str) -> str:
    return os.path.join(session_dir, "input_trace_windows.backend")


def append_trace_event(path: str, payload: Dict[str, Any]) -> None:
    try:
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(path, "a") as f:
            try:
                fcntl.flock(f, fcntl.LOCK_EX)
            except Exception:
                pass
            f.write(json.dumps(payload) + "\n")
            f.flush()
            try:
                fcntl.flock(f, fcntl.LOCK_UN)
            except Exception:
                pass
    except Exception:
        pass


def truncate_text(value: Optional[str], limit: int = 4000) -> str:
    if not value:
        return ""
    if len(value) <= limit:
        return value
    suffix = f"\n...[truncated {len(value) - limit} chars]"
    return value[:limit] + suffix


def read_file_tail(path: str, max_bytes: int = 4096) -> str:
    try:
        with open(path, "rb") as f:
            f.seek(0, os.SEEK_END)
            size = f.tell()
            if size <= max_bytes:
                f.seek(0)
            else:
                f.seek(size - max_bytes)
            data = f.read()
        try:
            return data.decode("utf-8", errors="replace")
        except Exception:
            return data.decode(errors="replace")
    except Exception:
        return ""


def append_input_event(session_dir: Optional[str], event: Dict[str, Any]) -> None:
    if not session_dir:
        return
    payload = dict(event)
    payload.setdefault("timestamp_utc", datetime.datetime.now(datetime.timezone.utc).isoformat())
    payload.setdefault("timestamp_epoch_ms", int(time.time() * 1000))
    payload.setdefault("session_id", session_id_from_dir(session_dir))
    append_trace_event(input_trace_log_path(session_dir), payload)


def input_trace_client_enabled(session_dir: Optional[str]) -> bool:
    if not session_dir:
        return False
    try:
        with open(input_trace_client_state_path(session_dir), "r") as f:
            return f.read().strip() == "enabled"
    except Exception:
        return False


def write_input_trace_client_state(session_dir: str, enabled: bool) -> None:
    try:
        with open(input_trace_client_state_path(session_dir), "w") as f:
            f.write("enabled" if enabled else "disabled")
    except Exception:
        pass


def input_trace_windows_pid(session_dir: str) -> Optional[int]:
    return read_pid(input_trace_windows_pid_path(session_dir))


def input_trace_windows_running(session_dir: Optional[str]) -> bool:
    if not session_dir:
        return False
    pid = input_trace_windows_pid(session_dir)
    return pid is not None and pid_running(pid)


def input_trace_windows_state(session_dir: Optional[str]) -> Optional[str]:
    if not session_dir:
        return None
    try:
        with open(input_trace_windows_state_path(session_dir), "r") as f:
            return f.read().strip() or None
    except Exception:
        return None

def input_trace_windows_backend(session_dir: Optional[str]) -> Optional[str]:
    if not session_dir:
        return None
    try:
        with open(input_trace_windows_backend_path(session_dir), "r") as f:
            return f.read().strip() or None
    except Exception:
        return None


def write_input_trace_windows_state(session_dir: str, state: str) -> None:
    try:
        with open(input_trace_windows_state_path(session_dir), "w") as f:
            f.write(state)
    except Exception:
        pass

def write_input_trace_windows_backend(session_dir: str, backend: str) -> None:
    try:
        with open(input_trace_windows_backend_path(session_dir), "w") as f:
            f.write(backend)
    except Exception:
        pass


def input_trace_x11_core_pid(session_dir: str) -> Optional[int]:
    return read_pid(input_trace_x11_core_pid_path(session_dir))


def input_trace_x11_core_running(session_dir: Optional[str]) -> bool:
    if not session_dir:
        return False
    pid = input_trace_x11_core_pid(session_dir)
    return pid is not None and pid_running(pid)


def input_trace_x11_core_state(session_dir: Optional[str]) -> Optional[str]:
    if not session_dir:
        return None
    try:
        with open(input_trace_x11_core_state_path(session_dir), "r") as f:
            return f.read().strip() or None
    except Exception:
        return None


def write_input_trace_x11_core_state(session_dir: str, state: str) -> None:
    try:
        with open(input_trace_x11_core_state_path(session_dir), "w") as f:
            f.write(state)
    except Exception:
        pass


def input_trace_network_pid(session_dir: str) -> Optional[int]:
    return read_pid(input_trace_network_pid_path(session_dir))


def input_trace_network_running(session_dir: Optional[str]) -> bool:
    if not session_dir:
        return False
    pid = input_trace_network_pid(session_dir)
    return pid is not None and pid_running(pid)


def input_trace_network_state(session_dir: Optional[str]) -> Optional[str]:
    if not session_dir:
        return None
    try:
        with open(input_trace_network_state_path(session_dir), "r") as f:
            return f.read().strip() or None
    except Exception:
        return None


def write_input_trace_network_state(session_dir: str, state: str) -> None:
    try:
        with open(input_trace_network_state_path(session_dir), "w") as f:
            f.write(state)
    except Exception:
        pass


def to_wine_path(path: str) -> str:
    return "Z:" + path.replace("/", "\\")

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

@app.get("/version")
def get_version():
    """Return the WineBot version."""
    return {"version": VERSION}

@app.get("/health/environment")
async def health_environment():
    """Deep validation of the X11 and Wine driver environment."""
    x11 = await safe_async_command(["xdpyinfo"])
    
    # Wine driver check: This verifies if winex11.drv can actually initialize
    wine_driver = await safe_async_command(["wine", "cmd", "/c", "echo Driver Check"])
    
    # Process checks
    wm_pids = find_processes("openbox", exact=True)
    xvfb_pids = find_processes("Xvfb", exact=True)
    explorer_pids = find_processes("explorer.exe")
    
    # Driver capability details
    driver_ok = wine_driver.get("ok", False)
    nodrv_detected = "nodrv_CreateWindow" in wine_driver.get("stderr", "")
    
    status = "ok"
    if not x11.get("ok") or not driver_ok or len(xvfb_pids) == 0:
        status = "error"
    elif len(wm_pids) == 0 or len(explorer_pids) == 0:
        status = "degraded"

    return {
        "status": status,
        "x11": {
            "ok": x11.get("ok"),
            "display": os.getenv("DISPLAY"),
            "xvfb_running": len(xvfb_pids) > 0,
            "wm_running": len(wm_pids) > 0,
        },
        "wine": {
            "driver_ok": driver_ok,
            "nodrv_detected": nodrv_detected,
            "explorer_running": len(explorer_pids) > 0,
            "stderr": wine_driver.get("stderr") if not driver_ok else None,
        }
    }

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
async def health_x11():
    """X11 health details."""
    x11 = await safe_async_command(["xdpyinfo"])
    # Use native process check for speed
    wm_pids = find_processes("openbox", exact=True)
    active = await safe_async_command(["/automation/x11.sh", "active-window"])
    return {
        "display": os.getenv("DISPLAY"),
        "screen": os.getenv("SCREEN"),
        "connected": x11.get("ok", False),
        "xdpyinfo_error": x11.get("error") or x11.get("stderr"),
        "window_manager": {"name": "openbox", "running": len(wm_pids) > 0},
        "active_window": active.get("stdout") if active.get("ok") else None,
        "active_window_error": None if active.get("ok") else (active.get("error") or active.get("stderr")),
    }

@app.get("/health/windows")
async def health_windows():
    """Window list and active window details."""
    listing = await safe_async_command(["/automation/x11.sh", "list-windows"])
    active = await safe_async_command(["/automation/x11.sh", "active-window"])
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
    tools = ["winedbg", "gdb", "ffmpeg", "xdotool", "wmctrl", "xdpyinfo", "Xvfb", "x11vnc", "websockify", "xinput"]
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
async def health_recording():
    """Recorder status and current session."""
    session_dir = read_session_dir()
    # Use native process check
    recorder_pids = find_processes("automation.recorder start")
    trace_pid = input_trace_pid(session_dir) if session_dir else None
    trace_x11_core_pid = input_trace_x11_core_pid(session_dir) if session_dir else None
    trace_windows_pid = input_trace_windows_pid(session_dir) if session_dir else None
    trace_network_pid = input_trace_network_pid(session_dir) if session_dir else None
    enabled = os.getenv("WINEBOT_RECORD", "0") == "1"
    status = recording_status(session_dir, enabled)
    return {
        "enabled": enabled,
        "session_dir": session_dir,
        "session_dir_exists": os.path.isdir(session_dir) if session_dir else False,
        "recorder_running": len(recorder_pids) > 0,
        "recorder_pids": [str(p) for p in recorder_pids],
        "state": status["state"],
    }

@app.get("/lifecycle/status")
async def lifecycle_status():
    """Status for core WineBot components."""
    session_dir = read_session_dir()
    session_id = session_id_from_dir(session_dir)
    wineprefix = os.getenv("WINEPREFIX", "/wineprefix")
    user_dir = os.getenv("WINEBOT_USER_DIR")

    # Pure Python process checks (fast)
    xvfb_pids = find_processes("Xvfb", exact=True)
    openbox_pids = find_processes("openbox", exact=True)
    wine_pids = find_processes("explorer")
    x11vnc_pids = find_processes("x11vnc", exact=True)
    novnc_pids = find_processes("websockify") + find_processes("novnc_proxy")
    recorder_pids = find_processes("automation.recorder start")

    enabled = os.getenv("WINEBOT_RECORD", "0") == "1"
    record_status = recording_status(session_dir, enabled)

    return {
        "session_id": session_id,
        "session_dir": session_dir,
        "user_dir": user_dir,
        "wine_user_dir": os.path.join(wineprefix, "drive_c", "users", "winebot"),
        "lifecycle_log": lifecycle_log_path(session_dir) if session_dir else None,
        "processes": {
            "xvfb": {"ok": len(xvfb_pids) > 0, "stdout": "\n".join(map(str, xvfb_pids))},
            "openbox": {"ok": len(openbox_pids) > 0, "stdout": "\n".join(map(str, openbox_pids))},
            "wine_explorer": {"ok": len(wine_pids) > 0, "stdout": "\n".join(map(str, wine_pids))},
            "x11vnc": {"ok": len(x11vnc_pids) > 0, "stdout": "\n".join(map(str, x11vnc_pids))},
            "novnc": {"ok": len(novnc_pids) > 0, "stdout": "\n".join(map(str, novnc_pids))},
            "api_pid": os.getpid(),
            "recorder": {
                "enabled": enabled,
                "state": record_status["state"],
                "running": len(recorder_pids) > 0,
                "pids": [str(p) for p in recorder_pids],
            },
            "input_trace": {
                "state": input_trace_state(session_dir),
                "running": input_trace_running(session_dir),
                "pid": str(input_trace_pid(session_dir)) if session_dir and input_trace_pid(session_dir) else None,
                "log": input_trace_log_path(session_dir) if session_dir else None,
            },
            "input_trace_x11_core": {
                "state": input_trace_x11_core_state(session_dir),
                "running": input_trace_x11_core_running(session_dir),
                "pid": str(input_trace_x11_core_pid(session_dir)) if session_dir and input_trace_x11_core_pid(session_dir) else None,
                "log": input_trace_x11_core_log_path(session_dir) if session_dir else None,
            },
            "input_trace_windows": {
                "state": input_trace_windows_state(session_dir),
                "running": input_trace_windows_running(session_dir),
                "pid": str(input_trace_windows_pid(session_dir)) if session_dir and input_trace_windows_pid(session_dir) else None,
                "backend": input_trace_windows_backend(session_dir),
                "log": input_trace_windows_log_path(session_dir) if session_dir else None,
            },
            "input_trace_network": {
                "state": input_trace_network_state(session_dir),
                "running": input_trace_network_running(session_dir),
                "pid": str(input_trace_network_pid(session_dir)) if session_dir and input_trace_network_pid(session_dir) else None,
                "log": input_trace_network_log_path(session_dir) if session_dir else None,
            },
            "input_trace_client": {
                "enabled": input_trace_client_enabled(session_dir),
                "log": input_trace_client_log_path(session_dir) if session_dir else None,
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

def openbox_control(action: str) -> Dict[str, Any]:
    """Run an Openbox control action and log lifecycle events."""
    session_dir = read_session_dir()
    cmd = ["openbox", f"--{action}"]
    append_lifecycle_event(session_dir, f"openbox_{action}_requested", f"Openbox {action} requested", source="api")
    result = safe_command(cmd, timeout=3)
    if result.get("ok"):
        append_lifecycle_event(session_dir, f"openbox_{action}_ok", f"Openbox {action} completed", source="api")
    else:
        append_lifecycle_event(
            session_dir,
            f"openbox_{action}_failed",
            f"Openbox {action} failed",
            source="api",
            extra=result,
        )
    return {"status": "ok" if result.get("ok") else "error", "action": action, "result": result}

@app.post("/openbox/reconfigure")
def openbox_reconfigure():
    """Reload the Openbox configuration."""
    return openbox_control("reconfigure")

@app.post("/openbox/restart")
def openbox_restart():
    """Restart the Openbox window manager."""
    return openbox_control("restart")

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
    
    # Update broker
    interactive = os.getenv("MODE", "headless") == "interactive"
    await broker.update_session(os.path.basename(target_dir), interactive)

    return {
        "status": status,
        "session_dir": target_dir,
        "session_id": os.path.basename(target_dir),
        "previous_session": current_session,
    }

@app.get("/sessions/{session_id}/control")
def get_control_state(session_id: str):
    """Get the current interactive control state."""
    state = broker.get_state()
    # Simple validation that session matches if strict
    return state

@app.post("/sessions/{session_id}/control/grant")
async def grant_control(session_id: str, data: GrantControlModel):
    """User grants control to the agent for N seconds."""
    await broker.grant_agent(data.lease_seconds)
    return broker.get_state()

@app.post("/sessions/{session_id}/control/renew")
async def renew_control(session_id: str, data: GrantControlModel):
    """Agent requests lease renewal."""
    await broker.renew_agent(data.lease_seconds)
    return broker.get_state()

@app.post("/sessions/{session_id}/user_intent")
async def set_user_intent(session_id: str, data: UserIntentModel):
    """User sets intent (WAIT, SAFE_INTERRUPT, STOP_NOW)."""
    await broker.set_user_intent(data.intent)
    return broker.get_state()

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

@app.post("/lifecycle/reset_workspace")
async def reset_workspace():
    """Force Wine desktop to be maximized and undecorated."""
    screen = os.environ.get("SCREEN", "1920x1080x24").split("x")
    w, h = screen[0], screen[1]
    
    # Start explorer if missing
    if not find_processes("explorer"):
        subprocess.Popen(["wine", "explorer.exe", f"/desktop=Default,{w}x{h}"], 
                         stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                         start_new_session=True)
        await asyncio.sleep(3)

    # Try to maximize and resize
    for title in ["Desktop", "Wine Desktop"]:
        subprocess.run(["wmctrl", "-r", title, "-b", "add,undecorated"], capture_output=True)
        subprocess.run(["xdotool", "search", "--name", title, "windowmove", "0", "0", "windowsize", w, h], capture_output=True)
    
    # Also force focus to first Wine window found
    subprocess.run(["xdotool", "search", "--class", "explorer"], capture_output=True)
    subprocess.run(["xdotool", "search", "--name", "Desktop", "windowactivate"], capture_output=True)
    subprocess.run(["xdotool", "search", "--name", "Wine Desktop", "windowactivate"], capture_output=True)
    
    return {"status": "ok", "message": f"Workspace reset to {w}x{h}"}

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
            proc = subprocess.Popen(cmd)
            manage_process(proc)
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
async def run_python(data: PythonScriptModel):
    """Run a script using Windows Python (winpy)."""
    if not await broker.check_access():
        raise HTTPException(status_code=423, detail="Agent control denied by policy")

    session_dir = ensure_session_dir()
    script_dir = os.path.join(session_dir, "scripts") if session_dir else "/tmp"
    log_dir = os.path.join(session_dir, "logs") if session_dir else "/tmp"
    os.makedirs(script_dir, exist_ok=True)
    os.makedirs(log_dir, exist_ok=True)
    script_path = os.path.join(script_dir, f"api_script_{int(time.time())}.py")
    log_path = os.path.join(log_dir, f"{os.path.basename(script_path)}.log")
    
    with open(script_path, "w") as f:
        f.write(data.script)

    trace_id = uuid.uuid4().hex
    script_hash = hashlib.sha256(data.script.encode("utf-8")).hexdigest()
    append_input_event(session_dir, {
        "event": "agent_script",
        "phase": "start",
        "origin": "agent",
        "source": "api",
        "tool": "api:/run/python",
        "script_type": "python",
        "script_path": script_path,
        "script_sha256": script_hash,
        "script_length": len(data.script),
        "trace_id": trace_id,
    })

    # Run using winpy wrapper
    cmd = ["winpy", script_path]
    
    try:
        result = subprocess.run(cmd, capture_output=True, text=True, check=True)
        with open(log_path, "w") as f:
            f.write(result.stdout or "")
            if result.stderr:
                f.write("\n--- stderr ---\n")
                f.write(result.stderr)
        append_input_event(session_dir, {
            "event": "agent_script",
            "phase": "complete",
            "origin": "agent",
            "source": "api",
            "tool": "api:/run/python",
            "script_type": "python",
            "script_path": script_path,
            "script_sha256": script_hash,
            "script_length": len(data.script),
            "trace_id": trace_id,
            "status": "success",
        })
        return {"status": "success", "stdout": result.stdout, "stderr": result.stderr, "log_path": log_path, "trace_id": trace_id}
    except subprocess.CalledProcessError as e:
        with open(log_path, "w") as f:
            f.write(e.stdout or "")
            if e.stderr:
                f.write("\n--- stderr ---\n")
                f.write(e.stderr)
        append_input_event(session_dir, {
            "event": "agent_script",
            "phase": "complete",
            "origin": "agent",
            "source": "api",
            "tool": "api:/run/python",
            "script_type": "python",
            "script_path": script_path,
            "script_sha256": script_hash,
            "script_length": len(data.script),
            "trace_id": trace_id,
            "status": "error",
            "exit_code": e.returncode,
        })
        return {"status": "error", "exit_code": e.returncode, "stdout": e.stdout, "stderr": e.stderr, "log_path": log_path, "trace_id": trace_id}

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
async def start_recording(data: Optional[RecordingStartModel] = Body(default=None)):
    """Start a recording session."""
    async with recorder_lock:
        if data is None:
            data = RecordingStartModel()
        current_session = read_session_dir()
        if recorder_running(current_session):
            if recorder_state(current_session) == RecorderState.PAUSED.value:
                cmd = ["python3", "-m", "automation.recorder", "resume", "--session-dir", current_session]
                result = await run_async_command(cmd)
                if not result["ok"]:
                    raise HTTPException(status_code=500, detail=(result["stderr"] or "Failed to resume recorder"))
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
        proc = subprocess.Popen(cmd)
        manage_process(proc)

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
async def stop_recording():
    """Stop the active recording session."""
    async with recorder_lock:
        session_dir = read_session_dir()
        if not session_dir:
            return {"status": "already_stopped"}
        if not recorder_running(session_dir):
            write_recorder_state(session_dir, RecorderState.IDLE.value)
            return {"status": "already_stopped", "session_dir": session_dir}

        write_recorder_state(session_dir, RecorderState.STOPPING.value)
        cmd = ["python3", "-m", "automation.recorder", "stop", "--session-dir", session_dir]
        result = await run_async_command(cmd)
        if not result["ok"]:
            raise HTTPException(status_code=500, detail=(result["stderr"] or "Failed to stop recorder"))

        for _ in range(10):
            if not recorder_running(session_dir):
                write_recorder_state(session_dir, RecorderState.IDLE.value)
                break
            time.sleep(0.2)

        return {"status": "stopped", "session_dir": session_dir}

@app.post("/recording/pause")
async def pause_recording():
    """Pause the active recording session."""
    async with recorder_lock:
        session_dir = read_session_dir()
        if not session_dir:
            return {"status": RecorderState.IDLE.value}
        if not recorder_running(session_dir):
            return {"status": "already_paused", "session_dir": session_dir}
        if recorder_state(session_dir) == RecorderState.PAUSED.value:
            return {"status": "already_paused", "session_dir": session_dir}
        cmd = ["python3", "-m", "automation.recorder", "pause", "--session-dir", session_dir]
        result = await run_async_command(cmd)
        if not result["ok"]:
            raise HTTPException(status_code=500, detail=(result["stderr"] or "Failed to pause recorder"))
        return {"status": "paused", "session_dir": session_dir}

@app.post("/recording/resume")
async def resume_recording():
    """Resume the active recording session."""
    async with recorder_lock:
        session_dir = read_session_dir()
        if not session_dir:
            return {"status": RecorderState.IDLE.value}
        if not recorder_running(session_dir):
            return {"status": RecorderState.IDLE.value, "session_dir": session_dir}
        if recorder_state(session_dir) != RecorderState.PAUSED.value:
            return {"status": "already_recording", "session_dir": session_dir}
        cmd = ["python3", "-m", "automation.recorder", "resume", "--session-dir", session_dir]
        result = await run_async_command(cmd)
        if not result["ok"]:
            raise HTTPException(status_code=500, detail=(result["stderr"] or "Failed to resume recorder"))
        return {"status": "resumed", "session_dir": session_dir}

@app.get("/input/trace/status")
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

@app.post("/input/trace/start")
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

@app.post("/input/trace/stop")
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

@app.get("/input/trace/x11core/status")
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

@app.post("/input/trace/x11core/start")
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

@app.post("/input/trace/x11core/stop")
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

@app.get("/input/trace/client/status")
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

@app.post("/input/trace/client/start")
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

@app.post("/input/trace/client/stop")
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

@app.post("/input/client/event")
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

@app.get("/input/trace/windows/status")
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

@app.post("/input/trace/windows/start")
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
    debug_keys: List[str] = []
    if data.debug_keys:
        debug_keys = [k for k in data.debug_keys if k]
    elif data.debug_keys_csv:
        debug_keys = [k.strip() for k in data.debug_keys_csv.split(",") if k.strip()]

    warnings: List[str] = []

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

    proc: Optional[subprocess.Popen] = None
    backend_used: Optional[str] = None

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

@app.post("/input/trace/windows/stop")
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

@app.get("/input/trace/network/status")
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

@app.post("/input/trace/network/start")
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

@app.post("/input/trace/network/stop")
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

@app.get("/input/events")
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
    events: List[Dict[str, Any]] = []
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

@app.get("/sessions/{session_id}/artifacts")
def list_session_artifacts(session_id: str, session_root: Optional[str] = None):
    """List all files in a session directory."""
    target_dir = resolve_session_dir(session_id, None, session_root)
    if not os.path.isdir(target_dir):
        raise HTTPException(status_code=404, detail="Session directory not found")
    
    files = []
    for root, _, filenames in os.walk(target_dir):
        for f in filenames:
            rel_path = os.path.relpath(os.path.join(root, f), target_dir)
            files.append({
                "path": rel_path,
                "size": os.path.getsize(os.path.join(root, f)),
                "mtime": os.path.getmtime(os.path.join(root, f))
            })
    return {"session_id": session_id, "artifacts": files}

@app.get("/sessions/{session_id}/artifacts/{file_path:path}")
def get_session_artifact(session_id: str, file_path: str, session_root: Optional[str] = None):
    """Serve a file from a session directory."""
    target_dir = resolve_session_dir(session_id, None, session_root)
    full_path = os.path.join(target_dir, file_path)
    safe_path = validate_path(full_path)
    if not os.path.isfile(safe_path):
        raise HTTPException(status_code=404, detail="Artifact not found")
    
    media_type = "video/x-matroska" if safe_path.endswith(".mkv") else "application/octet-stream"
    if safe_path.endswith(".png"):
        media_type = "image/png"
    elif safe_path.endswith(".json") or safe_path.endswith(".jsonl"):
        media_type = "application/json"
    elif safe_path.endswith(".log") or safe_path.endswith(".txt"):
        media_type = "text/plain"

    return FileResponse(safe_path, media_type=media_type)

@app.post("/input/mouse/click")
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
    # Log to X11 layer
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

@app.post("/run/ahk")
async def run_ahk(data: AHKModel):
    """Run an AutoHotkey script."""
    if not await broker.check_access():
        raise HTTPException(status_code=423, detail="Agent control denied by policy")

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

    trace_id = uuid.uuid4().hex
    script_hash = hashlib.sha256(data.script.encode("utf-8")).hexdigest()
    append_input_event(session_dir, {
        "event": "agent_script",
        "phase": "start",
        "origin": "agent",
        "source": "api",
        "tool": "api:/run/ahk",
        "script_type": "ahk",
        "script_path": script_path,
        "script_sha256": script_hash,
        "script_length": len(data.script),
        "focus_title": data.focus_title,
        "trace_id": trace_id,
    })

    cmd = ["/scripts/run-ahk.sh", script_path, "--log", log_path]
    if data.focus_title:
        cmd.extend(["--focus-title", data.focus_title])
    if os.geteuid() == 0 and shutil.which("gosu"):
        cmd = ["gosu", "winebot"] + cmd
    env = os.environ.copy()
    env["WINEBOT_SUPPRESS_DEPRECATION"] = "1"
        
    try:
        result = subprocess.run(cmd, check=True, capture_output=True, text=True, env=env)
        stdout = result.stdout or ""
        stderr = result.stderr or ""
        log_tail = read_file_tail(log_path, 4096) if os.path.exists(log_path) else ""
        log_bytes = os.path.getsize(log_path) if os.path.exists(log_path) else 0
        append_input_event(session_dir, {
            "event": "agent_script",
            "phase": "complete",
            "origin": "agent",
            "source": "api",
            "tool": "api:/run/ahk",
            "script_type": "ahk",
            "script_path": script_path,
            "script_sha256": script_hash,
            "script_length": len(data.script),
            "trace_id": trace_id,
            "status": "success",
            "exit_code": result.returncode,
            "stdout_len": len(stdout),
            "stderr_len": len(stderr),
            "stdout": truncate_text(stdout, 4000),
            "stderr": truncate_text(stderr, 4000),
            "log_path": log_path,
            "log_bytes": log_bytes,
            "log_tail": truncate_text(log_tail, 4000),
        })
        return {
            "status": "success",
            "trace_id": trace_id,
            "exit_code": result.returncode,
            "stdout": truncate_text(stdout, 4000),
            "stderr": truncate_text(stderr, 4000),
            "log_path": log_path,
            "log_tail": truncate_text(log_tail, 4000),
        }
    except subprocess.CalledProcessError as e:
        stdout = e.stdout or ""
        stderr = e.stderr or ""
        log_tail = read_file_tail(log_path, 4096) if os.path.exists(log_path) else ""
        log_bytes = os.path.getsize(log_path) if os.path.exists(log_path) else 0
        append_input_event(session_dir, {
            "event": "agent_script",
            "phase": "complete",
            "origin": "agent",
            "source": "api",
            "tool": "api:/run/ahk",
            "script_type": "ahk",
            "script_path": script_path,
            "script_sha256": script_hash,
            "script_length": len(data.script),
            "trace_id": trace_id,
            "status": "error",
            "exit_code": e.returncode,
            "stdout_len": len(stdout),
            "stderr_len": len(stderr),
            "stdout": truncate_text(stdout, 4000),
            "stderr": truncate_text(stderr, 4000),
            "log_path": log_path,
            "log_bytes": log_bytes,
            "log_tail": truncate_text(log_tail, 4000),
        })
        return {
            "status": "error",
            "exit_code": e.returncode,
            "trace_id": trace_id,
            "stdout": truncate_text(stdout, 4000),
            "stderr": truncate_text(stderr, 4000),
            "log_path": log_path,
            "log_tail": truncate_text(log_tail, 4000),
        }

@app.post("/run/autoit")
async def run_autoit(data: AutoItModel):
    """Run an AutoIt script."""
    if not await broker.check_access():
        raise HTTPException(status_code=423, detail="Agent control denied by policy")

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

    trace_id = uuid.uuid4().hex
    script_hash = hashlib.sha256(data.script.encode("utf-8")).hexdigest()
    append_input_event(session_dir, {
        "event": "agent_script",
        "phase": "start",
        "origin": "agent",
        "source": "api",
        "tool": "api:/run/autoit",
        "script_type": "autoit",
        "script_path": script_path,
        "script_sha256": script_hash,
        "script_length": len(data.script),
        "focus_title": data.focus_title,
        "trace_id": trace_id,
    })

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
        append_input_event(session_dir, {
            "event": "agent_script",
            "phase": "complete",
            "origin": "agent",
            "source": "api",
            "tool": "api:/run/autoit",
            "script_type": "autoit",
            "script_path": script_path,
            "script_sha256": script_hash,
            "script_length": len(data.script),
            "trace_id": trace_id,
            "status": "success",
        })
        return {"status": "success", "log": log_content, "trace_id": trace_id}
    except subprocess.CalledProcessError as e:
        # Read log even on failure
        log_content = ""
        if os.path.exists(log_path):
            with open(log_path, "r") as f:
                log_content = f.read()
        append_input_event(session_dir, {
            "event": "agent_script",
            "phase": "complete",
            "origin": "agent",
            "source": "api",
            "tool": "api:/run/autoit",
            "script_type": "autoit",
            "script_path": script_path,
            "script_sha256": script_hash,
            "script_length": len(data.script),
            "trace_id": trace_id,
            "status": "error",
            "exit_code": e.returncode,
        })
        return {"status": "error", "exit_code": e.returncode, "stderr": e.stderr, "log": log_content, "trace_id": trace_id}

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
