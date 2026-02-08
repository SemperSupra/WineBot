import asyncio
import os
from api.core.models import RecorderState
from api.utils.files import read_pid, recorder_pid, recorder_state, write_recorder_state, recorder_running
from api.utils.process import run_async_command

recorder_lock = asyncio.Lock()

def recording_status(session_dir: str | None, enabled: bool) -> dict:
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

async def stop_recording():
    from api.utils.files import read_session_dir # Import locally to avoid circular dependency if files imports recorder (it doesn't currently, but safe)
    
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
