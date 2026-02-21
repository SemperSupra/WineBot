import asyncio
import os
import time
from api.core.broker import broker
from api.core.models import RecorderState
from api.core.recorder import recording_status
from api.utils.files import read_session_dir, append_lifecycle_event

async def inactivity_monitor_task():
    """Monitor session inactivity and manage recording state."""
    print("--> Inactivity monitor task started.")
    
    while True:
        try:
            idle_pause_sec = int(os.getenv("WINEBOT_INACTIVITY_PAUSE_SECONDS", "0"))
            if idle_pause_sec <= 0:
                await asyncio.sleep(10)
                continue

            session_dir = read_session_dir()
            if not session_dir:
                await asyncio.sleep(5)
                continue

            enabled = os.getenv("WINEBOT_RECORD", "0") == "1"
            status = recording_status(session_dir, enabled)
            current_state = status["state"]
            
            now = time.time()
            idle_time = now - broker.last_activity
            
            # 1. Auto-pause logic
            if current_state == RecorderState.RECORDING.value and idle_time > idle_pause_sec:
                print(f"--> Inactivity detected ({int(idle_time)}s). Auto-pausing recording.")
                # Call recorder module directly to avoid circular dependency
                from api.utils.process import run_async_command
                cmd = ["python3", "-m", "automation.recorder", "pause", "--session-dir", session_dir]
                await run_async_command(cmd)
                
                # Annotate
                append_lifecycle_event(session_dir, "auto_pause", f"Inactivity pause after {int(idle_time)}s", source="monitor")
                
            # 2. Auto-resume logic
            elif current_state == RecorderState.PAUSED.value and idle_time < (idle_pause_sec / 2):
                # Resume if activity detected
                print("--> Activity detected. Auto-resuming recording.")
                from api.utils.process import run_async_command
                cmd = ["python3", "-m", "automation.recorder", "resume", "--session-dir", session_dir]
                await run_async_command(cmd)
                
                # Annotate
                append_lifecycle_event(session_dir, "auto_resume", "Activity detected, auto-resuming", source="monitor")

            # 3. Liveness / Heartbeat
            if current_state == RecorderState.RECORDING.value:
                # We could add more complex heartbeat logic here if needed
                pass

        except Exception as e:
            print(f"--> Inactivity monitor error: {e}")
            
        # Adjustable heartbeat interval
        heartbeat_interval = int(os.getenv("WINEBOT_MONITOR_HEARTBEAT_SECONDS", "5"))
        await asyncio.sleep(heartbeat_interval)
