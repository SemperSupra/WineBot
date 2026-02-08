import os
import fcntl
import json
import time
import datetime
import platform
from typing import Dict, Any, Optional
from api.utils.process import pid_running

SESSION_FILE = "/tmp/winebot_current_session"
DEFAULT_SESSION_ROOT = "/artifacts/sessions"
ALLOWED_PREFIXES = ["/apps", "/wineprefix", "/tmp", "/artifacts"]

def validate_path(path: str):
    """Ensure path is within allowed directories to prevent traversal."""
    resolved = os.path.abspath(path)
    if not any(resolved.startswith(p) for p in ALLOWED_PREFIXES):
         raise Exception(f"Path not allowed. Must start with: {ALLOWED_PREFIXES}")
    return resolved

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

def read_pid(path: str) -> Optional[int]:
    try:
        with open(path, "r") as f:
            return int(f.read().strip())
    except (FileNotFoundError, ValueError):
        return None

def read_session_dir() -> Optional[str]:
    if not os.path.exists(SESSION_FILE):
        return None
    try:
        with open(SESSION_FILE, "r") as f:
            value = f.read().strip()
        return value or None
    except Exception:
        return None

def session_id_from_dir(session_dir: Optional[str]) -> Optional[str]:
    if not session_dir:
        return None
    return os.path.basename(session_dir)

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

def input_trace_log_path(session_dir: str) -> str:
    return os.path.join(session_dir, "logs", "input_events.jsonl")

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

def input_trace_x11_core_pid(session_dir: str) -> Optional[int]:
    return read_pid(os.path.join(session_dir, "input_trace_x11_core.pid"))

def input_trace_x11_core_running(session_dir: Optional[str]) -> bool:
    if not session_dir:
        return False
    pid = input_trace_x11_core_pid(session_dir)
    return pid is not None and pid_running(pid)

def input_trace_x11_core_state(session_dir: Optional[str]) -> Optional[str]:
    if not session_dir:
        return None
    try:
        with open(os.path.join(session_dir, "input_trace_x11_core.state"), "r") as f:
            return f.read().strip() or None
    except Exception:
        return None

def input_trace_x11_core_log_path(session_dir: str) -> str:
    return os.path.join(session_dir, "logs", "input_events_x11_core.jsonl")

def input_trace_x11_core_pid_path(session_dir: str) -> str:
    return os.path.join(session_dir, "input_trace_x11_core.pid")

def write_input_trace_x11_core_state(session_dir: str, state: str) -> None:
    try:
        with open(os.path.join(session_dir, "input_trace_x11_core.state"), "w") as f:
            f.write(state)
    except Exception:
        pass

def input_trace_network_pid(session_dir: str) -> Optional[int]:
    return read_pid(os.path.join(session_dir, "input_trace_network.pid"))

def input_trace_network_running(session_dir: Optional[str]) -> bool:
    if not session_dir:
        return False
    pid = input_trace_network_pid(session_dir)
    return pid is not None and pid_running(pid)

def input_trace_network_state(session_dir: Optional[str]) -> Optional[str]:
    if not session_dir:
        return None
    try:
        with open(os.path.join(session_dir, "input_trace_network.state"), "r") as f:
            return f.read().strip() or None
    except Exception:
        return None

def input_trace_network_log_path(session_dir: str) -> str:
    return os.path.join(session_dir, "logs", "input_events_network.jsonl")

def write_input_trace_network_state(session_dir: str, state: str) -> None:
    try:
        with open(os.path.join(session_dir, "input_trace_network.state"), "w") as f:
            f.write(state)
    except Exception:
        pass

def input_trace_client_enabled(session_dir: Optional[str]) -> bool:
    if not session_dir:
        return False
    try:
        with open(os.path.join(session_dir, "input_trace_client.state"), "r") as f:
            return f.read().strip() == "enabled"
    except Exception:
        return False

def input_trace_client_log_path(session_dir: str) -> str:
    return os.path.join(session_dir, "logs", "input_events_client.jsonl")

def write_input_trace_client_state(session_dir: str, enabled: bool) -> None:
    try:
        with open(os.path.join(session_dir, "input_trace_client.state"), "w") as f:
            f.write("enabled" if enabled else "disabled")
    except Exception:
        pass

def input_trace_windows_pid(session_dir: str) -> Optional[int]:
    return read_pid(os.path.join(session_dir, "input_trace_windows.pid"))

def input_trace_windows_running(session_dir: Optional[str]) -> bool:
    if not session_dir:
        return False
    pid = input_trace_windows_pid(session_dir)
    return pid is not None and pid_running(pid)

def input_trace_windows_state(session_dir: Optional[str]) -> Optional[str]:
    if not session_dir:
        return None
    try:
        with open(os.path.join(session_dir, "input_trace_windows.state"), "r") as f:
            return f.read().strip() or None
    except Exception:
        return None

def input_trace_windows_backend(session_dir: Optional[str]) -> Optional[str]:
    if not session_dir:
        return None
    try:
        with open(os.path.join(session_dir, "input_trace_windows.backend"), "r") as f:
            return f.read().strip() or None
    except Exception:
        return None

def input_trace_windows_log_path(session_dir: str) -> str:
    return os.path.join(session_dir, "logs", "input_events_windows.jsonl")

def input_trace_windows_pid_path(session_dir: str) -> str:
    return os.path.join(session_dir, "input_trace_windows.pid")

def write_input_trace_windows_state(session_dir: str, state: str) -> None:
    try:
        with open(os.path.join(session_dir, "input_trace_windows.state"), "w") as f:
            f.write(state)
    except Exception:
        pass

def write_input_trace_windows_backend(session_dir: str, backend: str) -> None:
    try:
        with open(os.path.join(session_dir, "input_trace_windows.backend"), "w") as f:
            f.write(backend)
    except Exception:
        pass

def to_wine_path(path: str) -> str:
    return "Z:" + path.replace("/", "\\")

def resolve_session_dir(
    session_id: Optional[str],
    session_dir: Optional[str],
    session_root: Optional[str],
) -> str:
    if session_dir:
        return validate_path(session_dir)
    if not session_id:
        raise Exception("Provide session_id or session_dir")
    if "/" in session_id or os.path.sep in session_id or ".." in session_id:
        raise Exception("Invalid session_id")
    root = session_root or os.getenv("WINEBOT_SESSION_ROOT", DEFAULT_SESSION_ROOT)
    safe_root = validate_path(root)
    return os.path.join(safe_root, session_id)

def ensure_session_subdirs(session_dir: str) -> None:
    for subdir in ("logs", "screenshots", "scripts", "user"):
        try:
            os.makedirs(os.path.join(session_dir, subdir), exist_ok=True)
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

def write_session_dir(path: str) -> None:
    with open(SESSION_FILE, "w") as f:
        f.write(path)

def write_session_manifest(session_dir: str, session_id: str) -> None:
    try:
        manifest = {
            "session_id": session_id,
            "start_time_epoch": time.time(),
            "start_time_iso": datetime.datetime.now(datetime.timezone.utc).isoformat(),
            "hostname": platform.node(),
            "display": os.getenv("DISPLAY", ":99"),
            "resolution": "1280x720",
            "fps": 30,
            "git_sha": None,
        }
        with open(os.path.join(session_dir, "session.json"), "w") as f:
            json.dump(manifest, f, indent=2)
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
            import shutil
            backup = f"{wine_user_dir}.bak.{int(time.time())}"
            shutil.move(wine_user_dir, backup)
        os.symlink(user_dir, wine_user_dir)
    except Exception:
        pass

def write_session_state(session_dir: str, state: str) -> None:
    try:
        with open(os.path.join(session_dir, "session.state"), "w") as f:
            f.write(state)
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
    import uuid
    session_id = f"session-{int(time.time())}-{uuid.uuid4().hex[:6]}"
    session_dir = os.path.join(safe_root, session_id)
    os.makedirs(session_dir, exist_ok=True)
    write_session_dir(session_dir)
    write_session_manifest(session_dir, session_id)
    ensure_session_subdirs(session_dir)
    return session_dir

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

def read_session_state(session_dir: str) -> Optional[str]:
    try:
        with open(os.path.join(session_dir, "session.state"), "r") as f:
            return f.read().strip() or None
    except Exception:
        return None

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

def append_input_event(session_dir: Optional[str], event: Dict[str, Any]) -> None:
    if not session_dir:
        return
    payload = dict(event)
    payload.setdefault("timestamp_utc", datetime.datetime.now(datetime.timezone.utc).isoformat())
    payload.setdefault("timestamp_epoch_ms", int(time.time() * 1000))
    payload.setdefault("session_id", session_id_from_dir(session_dir))
    append_trace_event(input_trace_log_path(session_dir), payload)

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

def truncate_text(value: Optional[str], limit: int = 4000) -> str:
    if not value:
        return ""
    if len(value) <= limit:
        return value
    suffix = f"\n...[truncated {len(value) - limit} chars]"
    return value[:limit] + suffix

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