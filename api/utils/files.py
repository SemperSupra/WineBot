import os
import fcntl
import json
import time
import asyncio
import datetime
import platform
from pathlib import Path
from typing import Dict, Any, Optional, List, Final
from api.core.versioning import ARTIFACT_SCHEMA_VERSION, EVENT_SCHEMA_VERSION
from api.core.session_context import set_current_session_dir
from api.utils.process import pid_running
from api.utils.config import config

SESSION_FILE: Final[str] = "/tmp/winebot_current_session"
INSTANCE_STATE_FILE: Final[str] = "/tmp/winebot_instance_state.json"
INSTANCE_CONTROL_MODE_FILE: Final[str] = "/wineprefix/winebot.instance_control_mode"
DEFAULT_SESSION_ROOT: Final[str] = "/artifacts/sessions"
ALLOWED_PREFIXES: Final[List[str]] = [
    "/apps",
    "/wineprefix",
    "/tmp",
    "/artifacts",
    "/opt/winebot",
    "/usr/bin",
]


def validate_path(path: str):
    """Ensure path is within allowed directories to prevent traversal."""
    resolved = str(Path(path).resolve())
    allowed = [str(Path(prefix).resolve()) for prefix in ALLOWED_PREFIXES]
    in_allowed = False
    for prefix in allowed:
        try:
            if os.path.commonpath([resolved, prefix]) == prefix:
                in_allowed = True
                break
        except ValueError:
            continue
    if not in_allowed:
        raise Exception(f"Path not allowed. Must be under one of: {ALLOWED_PREFIXES}")
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


def performance_metrics_log_path(session_dir: str) -> str:
    return os.path.join(session_dir, "logs", "perf_metrics.jsonl")


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
        "schema_version": EVENT_SCHEMA_VERSION,
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
    root = session_root or config.WINEBOT_SESSION_ROOT
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
        os.path.join(
            user_dir,
            "AppData",
            "Roaming",
            "Microsoft",
            "Windows",
            "Start Menu",
            "Programs",
        ),
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
    set_current_session_dir(path)


def write_session_manifest(session_dir: str, session_id: str) -> None:
    try:
        manifest = {
            "schema_version": ARTIFACT_SCHEMA_VERSION,
            "session_id": session_id,
            "start_time_epoch": time.time(),
            "start_time_iso": datetime.datetime.now(datetime.timezone.utc).isoformat(),
            "hostname": platform.node(),
            "display": os.getenv("DISPLAY", ":99"),
            "resolution": "1280x720",
            "fps": 30,
            "git_sha": None,
        }
        manifest_path = os.path.join(session_dir, "session.json")
        tmp_path = f"{manifest_path}.tmp"
        with open(tmp_path, "w") as f:
            json.dump(manifest, f, indent=2)
        os.rename(tmp_path, manifest_path)
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


def get_instance_mode() -> str:
    mode = (os.getenv("WINEBOT_INSTANCE_MODE") or "persistent").strip().lower()
    if mode not in {"persistent", "oneshot"}:
        return "persistent"
    return mode


def get_instance_control_mode() -> str:
    runtime_mode = (os.getenv("MODE") or "headless").strip().lower()
    default_mode = "agent-only" if runtime_mode == "headless" else "hybrid"
    mode = ""
    try:
        if os.path.exists(INSTANCE_CONTROL_MODE_FILE):
            with open(INSTANCE_CONTROL_MODE_FILE, "r") as f:
                mode = f.read().strip().lower()
    except Exception:
        mode = ""
    if not mode:
        mode = (os.getenv("WINEBOT_INSTANCE_CONTROL_MODE") or default_mode).strip().lower()
    if mode not in {"human-only", "agent-only", "hybrid"}:
        return default_mode
    return mode


def write_instance_control_mode(mode: str) -> str:
    normalized = (mode or "").strip().lower()
    if normalized not in {"human-only", "agent-only", "hybrid"}:
        normalized = "hybrid"
    try:
        os.makedirs(os.path.dirname(INSTANCE_CONTROL_MODE_FILE), exist_ok=True)
        with open(INSTANCE_CONTROL_MODE_FILE, "w") as f:
            f.write(normalized)
    except Exception:
        pass
    return normalized


def get_session_mode_default() -> str:
    mode = (os.getenv("WINEBOT_SESSION_MODE") or "persistent").strip().lower()
    if mode not in {"persistent", "oneshot"}:
        return "persistent"
    return mode


def get_session_control_mode_default() -> str:
    runtime_mode = (os.getenv("MODE") or "headless").strip().lower()
    default_mode = "agent-only" if runtime_mode == "headless" else "hybrid"
    mode = (os.getenv("WINEBOT_SESSION_CONTROL_MODE") or default_mode).strip().lower()
    if mode not in {"human-only", "agent-only", "hybrid"}:
        return default_mode
    return mode


def read_instance_state() -> Dict[str, Any]:
    default_state = {
        "mode": get_instance_mode(),
        "state": "unknown",
        "control_mode": get_instance_control_mode(),
        "timestamp_utc": datetime.datetime.now(datetime.timezone.utc).isoformat(),
    }
    try:
        with open(INSTANCE_STATE_FILE, "r") as f:
            data = json.load(f)
        if not isinstance(data, dict):
            return default_state
        mode = str(data.get("mode", get_instance_mode())).lower()
        if mode not in {"persistent", "oneshot"}:
            mode = get_instance_mode()
        state = str(data.get("state", "unknown"))
        return {
            "mode": mode,
            "state": state,
            "control_mode": str(data.get("control_mode", get_instance_control_mode())),
            "timestamp_utc": str(
                data.get(
                    "timestamp_utc",
                    datetime.datetime.now(datetime.timezone.utc).isoformat(),
                )
            ),
            "reason": str(data.get("reason", "")),
        }
    except Exception:
        return default_state


def write_instance_state(state: str, reason: str = "") -> Dict[str, Any]:
    payload = {
        "mode": get_instance_mode(),
        "control_mode": get_instance_control_mode(),
        "state": state,
        "reason": reason,
        "timestamp_utc": datetime.datetime.now(datetime.timezone.utc).isoformat(),
        "timestamp_epoch_ms": int(time.time() * 1000),
    }
    try:
        with open(INSTANCE_STATE_FILE, "w") as f:
            json.dump(payload, f)
    except Exception:
        pass
    return payload


def _session_mode_path(session_dir: str) -> str:
    return os.path.join(session_dir, "session.mode")


def _session_control_mode_path(session_dir: str) -> str:
    return os.path.join(session_dir, "session.control_mode")


def write_session_mode(session_dir: str, mode: str) -> None:
    normalized = (mode or "").strip().lower()
    if normalized not in {"persistent", "oneshot"}:
        normalized = "persistent"
    try:
        with open(_session_mode_path(session_dir), "w") as f:
            f.write(normalized)
    except Exception:
        pass


def read_session_mode(session_dir: str) -> str:
    try:
        with open(_session_mode_path(session_dir), "r") as f:
            mode = f.read().strip().lower()
        if mode in {"persistent", "oneshot"}:
            return mode
    except Exception:
        pass
    return get_session_mode_default()


def write_session_control_mode(session_dir: str, mode: str) -> None:
    normalized = (mode or "").strip().lower()
    if normalized not in {"human-only", "agent-only", "hybrid"}:
        normalized = "hybrid"
    try:
        with open(_session_control_mode_path(session_dir), "w") as f:
            f.write(normalized)
    except Exception:
        pass


def read_session_control_mode(session_dir: str) -> str:
    try:
        with open(_session_control_mode_path(session_dir), "r") as f:
            mode = f.read().strip().lower()
        if mode in {"human-only", "agent-only", "hybrid"}:
            return mode
    except Exception:
        pass
    return get_session_control_mode_default()


def ensure_session_dir(session_root: Optional[str] = None) -> Optional[str]:
    session_dir = read_session_dir()
    if not isinstance(session_dir, str) or not session_dir:
        session_dir = None
    if session_dir and os.path.isdir(session_dir):
        ensure_session_subdirs(session_dir)
        # Initialize missing mode marker for older sessions.
        if not os.path.exists(_session_mode_path(session_dir)):
            write_session_mode(session_dir, get_session_mode_default())
        if not os.path.exists(_session_control_mode_path(session_dir)):
            write_session_control_mode(session_dir, get_session_control_mode_default())
        # In one-shot mode, completed sessions are terminal and should not be reused.
        if read_session_mode(session_dir) == "oneshot" and read_session_state(session_dir) == "completed":
            session_dir = None
        else:
            return session_dir
    if session_dir is None:
        pass
    root = session_root or config.WINEBOT_SESSION_ROOT
    safe_root = validate_path(root)
    os.makedirs(safe_root, exist_ok=True)
    import uuid

    session_id = f"session-{int(time.time())}-{uuid.uuid4().hex[:6]}"
    session_dir = os.path.join(safe_root, session_id)
    temp_dir = f"{session_dir}.tmp"

    try:
        os.makedirs(temp_dir, exist_ok=True)
        # Initialize structure in temp dir
        ensure_session_subdirs(temp_dir)
        write_session_manifest(temp_dir, session_id)
        write_session_mode(temp_dir, get_session_mode_default())
        write_session_control_mode(temp_dir, get_session_control_mode_default())
        write_session_state(temp_dir, "active")

        # Atomic commit
        os.rename(temp_dir, session_dir)

        # Post-commit: Update global pointer
        write_session_dir(session_dir)
    except Exception:
        # Cleanup on failure
        import shutil

        if os.path.exists(temp_dir):
            shutil.rmtree(temp_dir)
        raise

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
        # Prevent unbounded log growth per session
        if os.path.exists(path) and os.path.getsize(path) > (config.WINEBOT_MAX_LOG_SIZE_MB * 1024 * 1024):
            return

        payload_with_version = dict(payload)
        payload_with_version.setdefault("schema_version", EVENT_SCHEMA_VERSION)
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(path, "a") as f:
            try:
                fcntl.flock(f, fcntl.LOCK_EX)
            except Exception:
                pass
            f.write(json.dumps(payload_with_version) + "\n")
            f.flush()
            try:
                fcntl.flock(f, fcntl.LOCK_UN)
            except Exception:
                pass
    except Exception:
        pass


def append_performance_metric(
    session_dir: Optional[str],
    metric: str,
    value_ms: float,
    source: str = "api",
    extra: Optional[Dict[str, Any]] = None,
) -> None:
    if not session_dir:
        return
    payload: Dict[str, Any] = {
        "schema_version": EVENT_SCHEMA_VERSION,
        "timestamp_utc": datetime.datetime.now(datetime.timezone.utc).isoformat(),
        "timestamp_epoch_ms": int(time.time() * 1000),
        "event": "performance_metric",
        "metric": metric,
        "value_ms": round(float(value_ms), 3),
        "source": source,
        "session_id": session_id_from_dir(session_dir),
    }
    if extra:
        payload["extra"] = extra
    append_trace_event(performance_metrics_log_path(session_dir), payload)


def append_input_event(session_dir: Optional[str], event: Dict[str, Any]) -> None:
    if not session_dir:
        return
    payload = dict(event)
    payload.setdefault("schema_version", EVENT_SCHEMA_VERSION)
    payload.setdefault(
        "timestamp_utc", datetime.datetime.now(datetime.timezone.utc).isoformat()
    )
    payload.setdefault("timestamp_epoch_ms", int(time.time() * 1000))
    payload.setdefault("session_id", session_id_from_dir(session_dir))
    append_trace_event(input_trace_log_path(session_dir), payload)


def read_file_tail_lines(path: str, limit: int = 200, chunk_size: int = 4096) -> List[str]:
    """Efficiently read the last N lines of a file by seeking backwards."""
    if not os.path.exists(path):
        return []
    
    lines: List[str] = []
    with open(path, "rb") as f:
        f.seek(0, os.SEEK_END)
        file_size = f.tell()
        buffer = b""
        pointer = file_size
        
        while len(lines) <= limit and pointer > 0:
            step = min(pointer, chunk_size)
            pointer -= step
            f.seek(pointer)
            chunk = f.read(step)
            buffer = chunk + buffer
            
            # Count lines in current buffer
            current_lines = buffer.split(b"\n")
            if len(current_lines) > limit + 1:
                # We found enough lines
                lines = [line.decode("utf-8", errors="replace") for line in current_lines[-(limit+1):]]
                break
            
            if pointer == 0:
                # Reached start of file
                lines = [line.decode("utf-8", errors="replace") for line in current_lines]
                break
                
    return [line for line in lines if line.strip()][-limit:]


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


async def follow_file(path: str, sleep_sec: float = 0.5):
    """Asynchronous generator that yields new lines appended to a file."""
    with open(path, "r", errors="replace") as f:
        # Go to the end of the file
        f.seek(0, os.SEEK_END)
        while True:
            line = f.readline()
            if not line:
                await asyncio.sleep(sleep_sec)
                continue
            yield line.rstrip("\n")


def cleanup_old_sessions(
    max_sessions: Optional[int] = None, ttl_days: Optional[int] = None
) -> int:
    """Delete old sessions based on count and/or age."""
    import shutil

    root = config.WINEBOT_SESSION_ROOT
    if not os.path.isdir(root):
        return 0

    current_session = read_session_dir()
    sessions: List[Dict[str, Any]] = []
    for name in os.listdir(root):
        if not name.startswith("session-"):
            continue
        path = os.path.join(root, name)
        if not os.path.isdir(path):
            continue
        if current_session and os.path.abspath(path) == os.path.abspath(
            current_session
        ):
            continue
        sessions.append({"path": path, "mtime": os.path.getmtime(path)})

    # Sort by mtime (newest first)
    sessions.sort(key=lambda s: s["mtime"], reverse=True)

    deleted_count = 0
    now = time.time()

    for i, s in enumerate(sessions):
        should_delete = False

        # 1. TTL Check
        if ttl_days is not None:
            age_days = (now - s["mtime"]) / 86400
            if age_days > ttl_days:
                should_delete = True

        # 2. Max Sessions Check (Index starts at 0, so i=10 means it's the 11th session)
        if max_sessions is not None and i >= max_sessions:
            should_delete = True

        if should_delete:
            try:
                shutil.rmtree(s["path"])
                deleted_count += 1
            except Exception:
                pass

    return deleted_count
