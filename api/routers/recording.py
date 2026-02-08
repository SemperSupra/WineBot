from fastapi import APIRouter, HTTPException, Body
from typing import Optional
import os
import subprocess
import time
import datetime
import uuid
import json
from api.core.models import RecordingStartModel, RecorderState
from api.core.recorder import recorder_lock, recorder_running, recorder_state, write_recorder_state
from api.utils.files import read_session_dir, session_id_from_dir, resolve_session_dir, ensure_session_subdirs, write_session_dir, write_session_manifest, next_segment_index, read_pid, recorder_pid, append_lifecycle_event
from api.utils.process import manage_process, run_async_command, pid_running

router = APIRouter(prefix="/recording", tags=["recording"])

DEFAULT_SESSION_ROOT = "/artifacts/sessions"

def parse_resolution(screen: str) -> str:
    if not screen:
        return "1920x1080"
    parts = screen.split("x")
    if len(parts) >= 2:
        return f"{parts[0]}x{parts[1]}"
    return screen

def generate_session_id(label: Optional[str]) -> str:
    ts = int(time.time())
    date_prefix = time.strftime("%Y-%m-%d", time.gmtime(ts))
    rand = uuid.uuid4().hex[:6]
    session_id = f"session-{date_prefix}-{ts}-{rand}"
    if label:
        import re
        safe = re.sub(r"[^a-zA-Z0-9._-]+", "-", label).strip("-")
        if safe:
            session_id = f"{session_id}-{safe}"
    return session_id

@router.post("/start")
async def start_recording(data: Optional[RecordingStartModel] = Body(default=None)):
    """Start a recording session."""
    if os.getenv("WINEBOT_RECORD", "0") != "1":
        raise HTTPException(status_code=400, detail="Recording is disabled by configuration.")

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

@router.post("/stop")
async def stop_recording_endpoint():
    """Stop the active recording session."""
    if os.getenv("WINEBOT_RECORD", "0") != "1":
        raise HTTPException(status_code=400, detail="Recording is disabled by configuration.")

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

@router.post("/pause")
async def pause_recording():
    """Pause the active recording session."""
    if os.getenv("WINEBOT_RECORD", "0") != "1":
        raise HTTPException(status_code=400, detail="Recording is disabled by configuration.")

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

@router.post("/resume")
async def resume_recording():
    """Resume the active recording session."""
    if os.getenv("WINEBOT_RECORD", "0") != "1":
        raise HTTPException(status_code=400, detail="Recording is disabled by configuration.")

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
