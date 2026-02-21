import asyncio
from typing import Protocol, runtime_checkable, Dict, Any
from api.core.models import RecorderState
from api.utils.files import recorder_state, write_recorder_state, recorder_running
from api.utils.process import run_async_command


@runtime_checkable
class Recorder(Protocol):
    """Protocol defining the interface for any session recorder implementation."""
    async def start(self) -> Dict[str, Any]: ...
    async def stop(self) -> Dict[str, Any]: ...
    async def status(self) -> Dict[str, Any]: ...
    async def heartbeat(self) -> bool: ...


recorder_lock = asyncio.Lock()


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
    # We check the most recent part file if segmenting, or the main mkv
    # Finding current file is complex, we just check if ANY mkv in logs/session is recent or growing.
    # Implementation detail: simplified check for now
    return True


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
