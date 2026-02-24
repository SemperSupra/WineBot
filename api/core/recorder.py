import asyncio
import glob
import os
import time
from typing import Protocol, runtime_checkable, Dict, Any
from api.core.models import RecorderState
from api.utils.files import recorder_state, write_recorder_state, recorder_running
from api.utils.process import run_async_command
from api.utils.config import config


@runtime_checkable
class Recorder(Protocol):
    """Protocol defining the interface for any session recorder implementation."""
    async def start(self) -> Dict[str, Any]: ...
    async def stop(self) -> Dict[str, Any]: ...
    async def status(self) -> Dict[str, Any]: ...
    async def heartbeat(self) -> bool: ...


recorder_lock = asyncio.Lock()
_heartbeat_cache: Dict[str, Dict[str, Any]] = {}


def recording_status(session_dir: str | None, enabled: bool) -> dict:
    if not enabled:
        return {"state": "disabled", "running": False}
    if not session_dir:
        return {"state": RecorderState.IDLE.value, "running": False}
    state = recorder_state(session_dir)
    running = recorder_running(session_dir)
    
    # Heartbeat check if supposedly recording
    heartbeat_ok = True
    if running and state == RecorderState.RECORDING.value:
        heartbeat_ok = recorder_heartbeat_check(session_dir)

    if running:
        if not heartbeat_ok:
            return {"state": "stalled", "running": True, "error": "No file growth detected"}
        if state == RecorderState.PAUSED.value:
            return {"state": RecorderState.PAUSED.value, "running": True}
        if state == RecorderState.STOPPING.value:
            return {"state": RecorderState.STOPPING.value, "running": True}
        return {"state": RecorderState.RECORDING.value, "running": True}
    if state == RecorderState.STOPPING.value:
        return {"state": RecorderState.STOPPING.value, "running": False}
    return {"state": RecorderState.IDLE.value, "running": False}


def recorder_heartbeat_check(session_dir: str) -> bool:
    """Verifies that the recorder is actually writing data by checking file growth."""
    stale_seconds = max(5, int(config.WINEBOT_RECORDER_HEARTBEAT_STALE_SECONDS))
    grace_seconds = max(1, int(config.WINEBOT_RECORDER_HEARTBEAT_GRACE_SECONDS))
    now = time.time()

    try:
        candidates = glob.glob(os.path.join(session_dir, "video*.mkv"))
        if not candidates:
            pid_path = os.path.join(session_dir, "ffmpeg.pid")
            if os.path.exists(pid_path):
                pid_age = now - os.path.getmtime(pid_path)
                return pid_age <= grace_seconds
            return False
        latest = max(candidates, key=lambda path: os.path.getmtime(path))
        stat = os.stat(latest)
        size = int(stat.st_size)
        mtime = float(stat.st_mtime)
    except Exception:
        return False

    entry = _heartbeat_cache.get(session_dir)
    if not entry or entry.get("path") != latest:
        _heartbeat_cache[session_dir] = {
            "path": latest,
            "size": size,
            "last_growth": now,
        }
        return True

    last_size = int(entry.get("size", 0))
    last_growth = float(entry.get("last_growth", now))
    if size > last_size:
        _heartbeat_cache[session_dir] = {
            "path": latest,
            "size": size,
            "last_growth": now,
        }
        return True

    # If file timestamp changed recently, treat as healthy even if size is stable.
    if (now - mtime) <= grace_seconds:
        return True

    return (now - last_growth) <= stale_seconds


async def stop_recording():
    # Import locally to avoid circular dependency
    from api.utils.files import read_session_dir

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
        # Log error? raise?
        pass

    for _ in range(10):
        if not recorder_running(session_dir):
            write_recorder_state(session_dir, RecorderState.IDLE.value)
            break
        await asyncio.sleep(0.2)

    return {"status": "stopped", "session_dir": session_dir}
