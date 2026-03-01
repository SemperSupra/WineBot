import asyncio
import os
import shutil
import subprocess
import time
import datetime
import random
import threading
from collections import deque
from typing import List, Dict, Any, Optional, Final, Set
from functools import lru_cache
from contextlib import asynccontextmanager
from api.core.session_context import get_current_session_dir

# Store strong references to Popen objects
process_store: Set[subprocess.Popen] = set()
process_store_lock = threading.Lock()

# Default timeout for safe_command and safe_async_command (can be overridden by WINEBOT_COMMAND_TIMEOUT)
DEFAULT_TIMEOUT: Final[int] = int(os.getenv("WINEBOT_COMMAND_TIMEOUT", "5"))
PROCESS_STORE_CAP: Final[int] = int(os.getenv("WINEBOT_MAX_DETACHED_PROCESSES", "500"))

_cmd_telemetry_lock = threading.Lock()
_cmd_telemetry_timestamps: deque[float] = deque()


class ProcessCapacityError(RuntimeError):
    """Raised when detached-process tracking capacity is exhausted."""


def _reap_finished_tracked_processes_locked() -> int:
    removed = 0
    for p in list(process_store):
        if p.poll() is not None:
            process_store.discard(p)
            removed += 1
    return removed


def reap_finished_tracked_processes() -> int:
    with process_store_lock:
        return _reap_finished_tracked_processes_locked()


def manage_process(proc: subprocess.Popen) -> None:
    """Track a detached process to ensure it is reaped later. Enforces safety cap."""
    with process_store_lock:
        if len(process_store) >= PROCESS_STORE_CAP:
            _reap_finished_tracked_processes_locked()
            # If still full, refuse to grow unbounded.
            if len(process_store) >= PROCESS_STORE_CAP:
                try:
                    proc.terminate()
                except Exception:
                    pass
                raise ProcessCapacityError(
                    f"Detached process tracking capacity reached ({PROCESS_STORE_CAP})."
                )
        process_store.add(proc)


def pid_running(pid: int) -> bool:
    try:
        os.kill(pid, 0)
        return True
    except ProcessLookupError:
        return False
    except PermissionError:
        return True


def _env_bool(name: str, default: bool) -> bool:
    raw = os.getenv(name)
    if raw is None:
        return default
    return raw.strip().lower() in {"1", "true", "yes", "on"}


def _env_float(name: str, default: float) -> float:
    raw = os.getenv(name)
    if raw is None or not raw.strip():
        return default
    try:
        value = float(raw)
    except Exception:
        return default
    return max(0.0, min(1.0, value))


def _env_int(name: str, default: int, minimum: int = 1) -> int:
    raw = os.getenv(name)
    if raw is None or not raw.strip():
        return default
    try:
        value = int(raw)
    except Exception:
        return default
    return max(minimum, value)


def _csv_set(value: Optional[str]) -> Set[str]:
    if not value:
        return set()
    return {item.strip() for item in value.split(",") if item.strip()}


def _allowlist_match(value: str, allowlist: Set[str]) -> bool:
    if not allowlist:
        return True
    return value in allowlist


def _rate_limit_ok(max_events_per_min: int) -> bool:
    now = time.time()
    window_start = now - 60.0
    with _cmd_telemetry_lock:
        while _cmd_telemetry_timestamps and _cmd_telemetry_timestamps[0] < window_start:
            _cmd_telemetry_timestamps.popleft()
        if len(_cmd_telemetry_timestamps) >= max_events_per_min:
            return False
        _cmd_telemetry_timestamps.append(now)
    return True


def _command_telemetry_enabled() -> bool:
    return _env_bool("WINEBOT_TELEMETRY", _env_bool("WINEBOT_PERF_METRICS", True))


def _command_telemetry_allowed() -> bool:
    if not _command_telemetry_enabled():
        return False
    feature = "runtime"
    capability = "command_substrate"
    feature_set = "runtime_foundation"
    features = _csv_set(os.getenv("WINEBOT_TELEMETRY_FEATURES", ""))
    capabilities = _csv_set(os.getenv("WINEBOT_TELEMETRY_CAPABILITIES", ""))
    feature_sets = _csv_set(os.getenv("WINEBOT_TELEMETRY_FEATURE_SETS", ""))
    if not _allowlist_match(feature, features):
        return False
    if not _allowlist_match(capability, capabilities):
        return False
    if not _allowlist_match(feature_set, feature_sets):
        return False
    sample_rate = _env_float("WINEBOT_TELEMETRY_SAMPLE_RATE", 1.0)
    if random.random() > sample_rate:
        return False
    max_events_per_min = _env_int("WINEBOT_TELEMETRY_MAX_EVENTS_PER_MIN", 600, minimum=1)
    return _rate_limit_ok(max_events_per_min)


def _command_telemetry_path() -> Optional[str]:
    session_dir = get_current_session_dir() or os.getenv("WINEBOT_SESSION_DIR", "").strip()
    if not session_dir:
        return None
    return os.path.join(session_dir, "logs", "perf_metrics.jsonl")


def _emit_command_telemetry(
    operation: str,
    command_name: str,
    duration_ms: float,
    result: str,
    error_class: str = "",
    exit_code: Optional[int] = None,
) -> None:
    if not _command_telemetry_allowed():
        return
    path = _command_telemetry_path()
    if not path:
        return
    payload: Dict[str, Any] = {
        "schema_version": "1.0",
        "timestamp_utc": datetime.datetime.now(datetime.timezone.utc).isoformat(),
        "timestamp_epoch_ms": int(time.time() * 1000),
        "event": "performance_metric",
        "metric": f"command.{operation}.latency",
        "value_ms": round(float(duration_ms), 3),
        "duration_ms": round(float(duration_ms), 3),
        "feature": "runtime",
        "capability": "command_substrate",
        "feature_set": "runtime_foundation",
        "operation": operation,
        "result": result,
        "source": "process",
        "telemetry_level": os.getenv("WINEBOT_TELEMETRY_LEVEL", "standard"),
        "build_intent": os.getenv("BUILD_INTENT", ""),
        "runtime_mode": os.getenv("MODE", ""),
        "tags": {
            "command_name": command_name,
            "error_class": error_class,
        },
    }
    if exit_code is not None:
        payload["tags"]["exit_code"] = exit_code
    try:
        # Reuse bounded writer path to enforce global log size caps.
        from api.utils.files import append_trace_event

        append_trace_event(path, payload)
    except Exception:
        pass


async def run_async_command(cmd: List[str], timeout: Optional[int] = None) -> Dict[str, Any]:
    """Run a command asynchronously without blocking the event loop. Uses DEFAULT_TIMEOUT if timeout is not provided."""
    to = timeout if timeout is not None else DEFAULT_TIMEOUT
    return await safe_async_command(cmd, timeout=to)


def find_processes(pattern: str, exact: bool = False) -> List[int]:
    """Find PIDs of processes matching a name or command line pattern (pure Python pgrep)."""
    pids = []
    try:
        for pid_str in os.listdir("/proc"):
            if not pid_str.isdigit():
                continue
            pid = int(pid_str)
            try:
                if exact:
                    matched = False
                    with open(f"/proc/{pid}/comm", "r") as f:
                        comm = f.read().strip()
                        if comm == pattern:
                            matched = True
                    if not matched:
                        with open(f"/proc/{pid}/cmdline", "rb") as f:
                            cmd_bytes = f.read()
                            argv0 = (
                                cmd_bytes.split(b"\0", 1)[0]
                                .decode("utf-8", errors="ignore")
                                .strip()
                            )
                            if os.path.basename(argv0) == pattern:
                                matched = True
                    if matched:
                        pids.append(pid)
                    # exact mode should not fallback to broad substring matching.
                    continue
                with open(f"/proc/{pid}/cmdline", "rb") as f:
                    cmd_bytes = f.read()
                    cmd = (
                        cmd_bytes.replace(b"\0", b" ")
                        .decode("utf-8", errors="ignore")
                        .strip()
                    )
                    if pattern in cmd:
                        pids.append(pid)
            except (FileNotFoundError, ProcessLookupError, PermissionError):
                continue
    except Exception:
        pass
    return pids


def run_command(cmd: List[str]):
    try:
        result = subprocess.run(cmd, capture_output=True, text=True, check=True, timeout=DEFAULT_TIMEOUT)
        return result.stdout.strip()
    except subprocess.CalledProcessError as e:
        raise Exception(f"Command failed: {e.stderr}")


def safe_command(cmd: List[str], timeout: Optional[int] = None) -> Dict[str, Any]:
    to = timeout if timeout is not None else DEFAULT_TIMEOUT
    started = time.perf_counter()
    command_name = (cmd[0] if cmd else "unknown").strip()
    try:
        result = subprocess.run(
            cmd, capture_output=True, text=True, check=True, timeout=to
        )
        payload = {
            "ok": True,
            "stdout": result.stdout.strip(),
            "stderr": result.stderr.strip(),
        }
        _emit_command_telemetry(
            "safe_command",
            command_name,
            (time.perf_counter() - started) * 1000.0,
            result="ok",
            exit_code=0,
        )
        return payload
    except FileNotFoundError:
        _emit_command_telemetry(
            "safe_command",
            command_name,
            (time.perf_counter() - started) * 1000.0,
            result="error",
            error_class="command_not_found",
        )
        return {"ok": False, "error": "command not found"}
    except subprocess.TimeoutExpired:
        _emit_command_telemetry(
            "safe_command",
            command_name,
            (time.perf_counter() - started) * 1000.0,
            result="error",
            error_class="timeout",
        )
        return {"ok": False, "error": "timeout"}
    except subprocess.CalledProcessError as e:
        _emit_command_telemetry(
            "safe_command",
            command_name,
            (time.perf_counter() - started) * 1000.0,
            result="error",
            error_class="nonzero_exit",
            exit_code=e.returncode,
        )
        return {
            "ok": False,
            "exit_code": e.returncode,
            "stdout": e.stdout.strip(),
            "stderr": e.stderr.strip(),
        }


@lru_cache(maxsize=None)
def check_binary(name: str) -> Dict[str, Any]:
    path = shutil.which(name)
    return {"present": path is not None, "path": path}


@asynccontextmanager
async def async_subprocess_context(cmd: List[str], timeout: Optional[int] = None):
    """Context manager to ensure a subprocess is reaped even on error or cancellation."""
    proc = await asyncio.create_subprocess_exec(
        *cmd, stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE
    )
    try:
        yield proc
    finally:
        if proc.returncode is None:
            try:
                proc.terminate()
                await asyncio.wait_for(proc.wait(), timeout=1.0)
            except (asyncio.TimeoutError, ProcessLookupError):
                try:
                    proc.kill()
                    await proc.wait()
                except ProcessLookupError:
                    pass


async def safe_async_command(cmd: List[str], timeout: Optional[int] = None) -> Dict[str, Any]:
    to = timeout if timeout is not None else DEFAULT_TIMEOUT
    started = time.perf_counter()
    command_name = (cmd[0] if cmd else "unknown").strip()
    try:
        async with async_subprocess_context(cmd, timeout=to) as proc:
            try:
                stdout, stderr = await asyncio.wait_for(proc.communicate(), timeout=to)
                payload = {
                    "ok": proc.returncode == 0,
                    "stdout": stdout.decode().strip(),
                    "stderr": stderr.decode().strip(),
                }
                _emit_command_telemetry(
                    "safe_async_command",
                    command_name,
                    (time.perf_counter() - started) * 1000.0,
                    result="ok" if proc.returncode == 0 else "error",
                    error_class="" if proc.returncode == 0 else "nonzero_exit",
                    exit_code=proc.returncode,
                )
                return payload
            except asyncio.TimeoutError:
                _emit_command_telemetry(
                    "safe_async_command",
                    command_name,
                    (time.perf_counter() - started) * 1000.0,
                    result="error",
                    error_class="timeout",
                )
                return {"ok": False, "error": "timeout"}
    except FileNotFoundError:
        _emit_command_telemetry(
            "safe_async_command",
            command_name,
            (time.perf_counter() - started) * 1000.0,
            result="error",
            error_class="command_not_found",
        )
        return {"ok": False, "error": "command not found"}
    except Exception as e:
        _emit_command_telemetry(
            "safe_async_command",
            command_name,
            (time.perf_counter() - started) * 1000.0,
            result="error",
            error_class="exception",
        )
        return {"ok": False, "error": str(e)}
