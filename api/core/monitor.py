import asyncio
import os
import time

from api.core.broker import broker
from api.core.models import ControlMode, RecorderState
from api.core.recorder import recorder_lock, recording_status
from api.core.session_context import bind_session_dir
from api.core.telemetry import emit_operation_timing
from api.utils.files import (
    append_lifecycle_event,
    read_session_dir,
)
from api.utils.process import run_async_command


def _env_int(name: str, default: int, minimum: int = 0) -> int:
    raw = os.getenv(name)
    if raw is None or not raw.strip():
        return default
    try:
        value = int(raw)
    except Exception:
        return default
    return max(minimum, value)


def _performance_metrics_enabled() -> bool:
    return (os.getenv("WINEBOT_TELEMETRY", os.getenv("WINEBOT_PERF_METRICS", "1")) or "1").strip().lower() in {
        "1",
        "true",
        "yes",
        "on",
    }


def resolve_inactivity_pause_seconds() -> int:
    state = broker.get_state()
    # Conservative default to avoid aggressive pause/resume churn.
    base = _env_int("WINEBOT_INACTIVITY_PAUSE_SECONDS", 180, minimum=0)
    if state.control_mode == ControlMode.USER:
        return _env_int("WINEBOT_INACTIVITY_PAUSE_SECONDS_HUMAN", base, minimum=0)
    if state.control_mode == ControlMode.AGENT:
        return _env_int("WINEBOT_INACTIVITY_PAUSE_SECONDS_AGENT", base, minimum=0)
    return base


async def inactivity_monitor_task():
    """Monitor session inactivity and manage recording state."""
    print("--> Inactivity monitor task started.")

    last_session_dir = ""
    last_auto_pause_at = 0.0
    paused_since = 0.0
    last_sample_at = 0.0

    while True:
        try:
            idle_pause_sec = resolve_inactivity_pause_seconds()
            if idle_pause_sec <= 0:
                await asyncio.sleep(10)
                continue

            session_dir = read_session_dir()
            if not session_dir:
                await asyncio.sleep(5)
                continue

            if session_dir != last_session_dir:
                last_session_dir = session_dir
                last_auto_pause_at = 0.0
                paused_since = 0.0
                last_sample_at = 0.0

            enabled = os.getenv("WINEBOT_RECORD", "0") == "1"
            status = recording_status(session_dir, enabled)
            current_state = status["state"]

            now = time.time()
            idle_time = now - broker.last_activity
            control_mode = broker.get_state().control_mode.value
            resume_activity_window_sec = _env_int(
                "WINEBOT_INACTIVITY_RESUME_ACTIVITY_SECONDS", 10, minimum=1
            )
            min_pause_dwell_sec = _env_int(
                "WINEBOT_INACTIVITY_MIN_PAUSE_SECONDS", 15, minimum=0
            )
            resume_cooldown_sec = _env_int(
                "WINEBOT_INACTIVITY_RESUME_COOLDOWN_SECONDS", 10, minimum=0
            )
            sample_period_sec = _env_int(
                "WINEBOT_PERF_METRICS_SAMPLE_SECONDS", 30, minimum=5
            )

            if _performance_metrics_enabled() and now - last_sample_at >= sample_period_sec:
                emit_operation_timing(
                    session_dir,
                    feature="recording",
                    capability="inactivity_monitor",
                    feature_set="recording_and_artifacts",
                    operation="sample",
                    duration_ms=0.0,
                    result="ok",
                    source="monitor",
                    metric_name="inactivity.monitor_sample",
                    tags={
                        "state": current_state,
                        "idle_time_sec": round(idle_time, 3),
                        "idle_pause_threshold_sec": idle_pause_sec,
                        "resume_activity_window_sec": resume_activity_window_sec,
                        "min_pause_dwell_sec": min_pause_dwell_sec,
                        "resume_cooldown_sec": resume_cooldown_sec,
                        "control_mode": control_mode,
                    },
                )
                last_sample_at = now

            # 1. Auto-pause logic
            if current_state == RecorderState.RECORDING.value and idle_time >= idle_pause_sec:
                print(f"--> Inactivity detected ({int(idle_time)}s). Auto-pausing recording.")
                started = time.perf_counter()
                with bind_session_dir(session_dir):
                    async with recorder_lock:
                        result = await run_async_command(
                            [
                                "python3",
                                "-m",
                                "automation.recorder",
                                "pause",
                                "--session-dir",
                                session_dir,
                            ]
                        )
                elapsed_ms = (time.perf_counter() - started) * 1000.0
                if result.get("ok"):
                    append_lifecycle_event(
                        session_dir,
                        "auto_pause",
                        f"Inactivity pause after {int(idle_time)}s",
                        source="monitor",
                    )
                    paused_since = now
                    last_auto_pause_at = now
                else:
                    append_lifecycle_event(
                        session_dir,
                        "auto_pause_failed",
                        "Inactivity auto-pause failed",
                        source="monitor",
                        extra=result,
                    )
                emit_operation_timing(
                    session_dir,
                    feature="recording",
                    capability="pause_resume",
                    feature_set="recording_and_artifacts",
                    operation="auto_pause",
                    duration_ms=elapsed_ms,
                    result="ok" if bool(result.get("ok")) else "error",
                    source="monitor",
                    metric_name="recording.auto_pause.latency",
                    tags={
                        "ok": bool(result.get("ok")),
                        "idle_time_sec": round(idle_time, 3),
                        "threshold_sec": idle_pause_sec,
                        "control_mode": control_mode,
                    },
                )

            # 2. Auto-resume logic with dwell+cooldown+hysteresis
            elif current_state == RecorderState.PAUSED.value:
                if paused_since <= 0.0:
                    paused_since = now

                pause_dwell_sec = now - paused_since
                can_resume = (
                    idle_time <= resume_activity_window_sec
                    and pause_dwell_sec >= min_pause_dwell_sec
                    and (now - last_auto_pause_at) >= resume_cooldown_sec
                )
                if can_resume:
                    print("--> Activity detected. Auto-resuming recording.")
                    started = time.perf_counter()
                    with bind_session_dir(session_dir):
                        async with recorder_lock:
                            result = await run_async_command(
                                [
                                    "python3",
                                    "-m",
                                    "automation.recorder",
                                    "resume",
                                    "--session-dir",
                                    session_dir,
                                ]
                            )
                    elapsed_ms = (time.perf_counter() - started) * 1000.0
                    if result.get("ok"):
                        append_lifecycle_event(
                            session_dir,
                            "auto_resume",
                            "Activity detected, auto-resuming",
                            source="monitor",
                        )
                        paused_since = 0.0
                    else:
                        append_lifecycle_event(
                            session_dir,
                            "auto_resume_failed",
                            "Activity-triggered auto-resume failed",
                            source="monitor",
                            extra=result,
                        )
                    emit_operation_timing(
                        session_dir,
                        feature="recording",
                        capability="pause_resume",
                        feature_set="recording_and_artifacts",
                        operation="auto_resume",
                        duration_ms=elapsed_ms,
                        result="ok" if bool(result.get("ok")) else "error",
                        source="monitor",
                        metric_name="recording.auto_resume.latency",
                        tags={
                            "ok": bool(result.get("ok")),
                            "idle_time_sec": round(idle_time, 3),
                            "resume_activity_window_sec": resume_activity_window_sec,
                            "pause_dwell_sec": round(pause_dwell_sec, 3),
                            "control_mode": control_mode,
                        },
                    )
            else:
                paused_since = 0.0

        except Exception as e:
            print(f"--> Inactivity monitor error: {e}")

        # Adjustable heartbeat interval
        heartbeat_interval = _env_int("WINEBOT_MONITOR_HEARTBEAT_SECONDS", 5, minimum=1)
        await asyncio.sleep(heartbeat_interval)
