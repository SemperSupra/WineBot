import os
import sys
from typing import Optional

from pydantic import BaseModel, Field, ValidationError

from api.core.constants import (
    CONTROL_MODE_AGENT_ONLY,
    CONTROL_MODE_HYBRID,
    LIFECYCLE_MODE_PERSISTENT,
    MODE_HEADLESS,
)


class WineBotConfig(BaseModel):
    MODE: str = MODE_HEADLESS
    BUILD_INTENT: str = "rel"

    # Core
    API_TOKEN: Optional[str] = None
    WINEBOT_LOG_LEVEL: str = Field(
        default="INFO", pattern="^(DEBUG|INFO|WARNING|ERROR|CRITICAL)$"
    )
    WINEBOT_COMMAND_TIMEOUT: int = 5
    API_PORT: int = 8000

    # Discovery (mDNS)
    WINEBOT_DISCOVERY_ALLOW_MULTIPLE: bool = True
    MDNS_SERVICE_TYPE: str = "_winebot-session._tcp.local."
    MDNS_UPDATE_INTERVAL_SEC: int = 30

    # Display & VNC
    DISPLAY: str = ":99"
    SCREEN_RESOLUTION: str = "1280x720x24"
    DEFAULT_FPS: int = 30
    VNC_PORT: int = 5900
    NOVNC_PORT: int = 6080

    # Resources and policy controls
    WINEBOT_SESSION_ROOT: str = "/artifacts/sessions"
    WINEBOT_MAX_SESSIONS: Optional[int] = None
    WINEBOT_SESSION_TTL_DAYS: Optional[int] = None
    WINEBOT_INSTANCE_MODE: str = LIFECYCLE_MODE_PERSISTENT
    WINEBOT_SESSION_MODE: str = LIFECYCLE_MODE_PERSISTENT
    WINEBOT_INSTANCE_CONTROL_MODE: str = CONTROL_MODE_HYBRID
    WINEBOT_SESSION_CONTROL_MODE: str = CONTROL_MODE_HYBRID
    WINEBOT_USE_CASE_PROFILE: str = ""
    WINEBOT_PERFORMANCE_PROFILE: str = ""
    WINEBOT_ALLOW_HEADLESS_HYBRID: bool = False
    WINEBOT_MAX_LOG_SIZE_MB: int = 500
    WINEBOT_MAX_SCREENSHOTS_PER_SESSION: int = 1000
    WINEBOT_MAX_TRACE_LOAD_MB: int = 100
    WINEBOT_MAX_DETACHED_PROCESSES: int = 500
    PROCESS_STORE_CAP: int = 500
    WINEBOT_MAX_EVENTS_QUERY: int = 2000
    WINEBOT_MAX_SESSIONS_QUERY: int = 1000
    WINEBOT_MAX_LOG_TAIL_LINES: int = 2000
    WINEBOT_MAX_LOG_FOLLOW_STREAMS: int = 8
    WINEBOT_LOG_FOLLOW_IDLE_TIMEOUT_SECONDS: int = 300
    WINEBOT_LOG_FOLLOW_ACQUIRE_TIMEOUT_SECONDS: float = 0.05
    WINEBOT_MAX_OPERATION_RECORDS: int = 500
    WINEBOT_OPERATION_RECORD_TTL_SECONDS: int = 86400
    WINEBOT_RESOURCE_MONITOR_INTERVAL_SECONDS: int = 5
    WINEBOT_SESSION_CLEANUP_INTERVAL_SECONDS: int = 60
    WINEBOT_SHUTDOWN_GUARD_TTL_SECONDS: int = 120

    # Inactivity
    WINEBOT_INACTIVITY_PAUSE_SECONDS: int = 180
    WINEBOT_INACTIVITY_PAUSE_SECONDS_HUMAN: Optional[int] = None
    WINEBOT_INACTIVITY_PAUSE_SECONDS_AGENT: Optional[int] = None
    WINEBOT_INACTIVITY_RESUME_ACTIVITY_SECONDS: int = 10
    WINEBOT_INACTIVITY_MIN_PAUSE_SECONDS: int = 15
    WINEBOT_INACTIVITY_RESUME_COOLDOWN_SECONDS: int = 10
    WINEBOT_MONITOR_HEARTBEAT_SECONDS: int = 5
    WINEBOT_PERF_METRICS: bool = True
    WINEBOT_PERF_METRICS_SAMPLE_SECONDS: int = 30
    WINEBOT_TELEMETRY: bool = True
    WINEBOT_TELEMETRY_LEVEL: str = "standard"
    WINEBOT_TELEMETRY_FEATURES: Optional[str] = None
    WINEBOT_TELEMETRY_CAPABILITIES: Optional[str] = None
    WINEBOT_TELEMETRY_FEATURE_SETS: Optional[str] = None
    WINEBOT_TELEMETRY_SAMPLE_RATE: float = 1.0
    WINEBOT_TELEMETRY_MAX_EVENTS_PER_MIN: int = 600

    # Temporal budgets and retries
    WINEBOT_TIMEOUT_AUTOMATION_APP_RUN_SECONDS: int = 30
    WINEBOT_TIMEOUT_AUTOMATION_SCRIPT_SECONDS: int = 30
    WINEBOT_TIMEOUT_RECORDING_CONTROL_SECONDS: int = 15
    WINEBOT_TIMEOUT_RECORDING_STOP_SECONDS: int = 20
    WINEBOT_TIMEOUT_LIFECYCLE_WINEBOOT_SECONDS: int = 10
    WINEBOT_TIMEOUT_LIFECYCLE_WINESERVER_SECONDS: int = 5
    WINEBOT_TIMEOUT_LIFECYCLE_COMPONENT_SECONDS: int = 3
    WINEBOT_TIMEOUT_LIFECYCLE_SESSION_HANDOVER_SECONDS: int = 60
    WINEBOT_RECORDER_HEARTBEAT_STALE_SECONDS: int = 30
    WINEBOT_RECORDER_HEARTBEAT_GRACE_SECONDS: int = 15
    WINEBOT_RECORDING_INCLUDE_INPUT_TRACES: bool = True
    WINEBOT_RECORDING_REDACT_SENSITIVE: bool = True
    WINEBOT_RECORDING_REDACT_FIELDS: str = (
        "key,keycode,text,raw,password,token,secret,clipboard"
    )
    WINEBOT_RECORDING_RETENTION_MAX_SEGMENTS: int = 0
    WINEBOT_RECORDING_RETENTION_MAX_AGE_DAYS: int = 0
    WINEBOT_RECORDING_RETENTION_MAX_BYTES: int = 0

    # Recorder (FFmpeg)
    RECORDER_PRESET: str = "ultrafast"
    RECORDER_CRF: int = 23
    RECORDER_PIX_FMT: str = "yuv420p"


def _parse_int(key: str, default: int) -> int:
    value = os.getenv(key)
    if value is None or not value.strip():
        return default
    try:
        return int(value)
    except ValueError as exc:
        raise ValueError(f"{key} must be an integer") from exc


def _parse_optional_int(key: str) -> Optional[int]:
    value = os.getenv(key)
    if value is None or not value.strip():
        return None
    try:
        return int(value)
    except ValueError as exc:
        raise ValueError(f"{key} must be an integer") from exc


def _parse_bool(key: str, default: bool) -> bool:
    value = os.getenv(key)
    if value is None or not value.strip():
        return default
    normalized = value.strip().lower()
    if normalized in {"1", "true", "yes", "on"}:
        return True
    if normalized in {"0", "false", "no", "off"}:
        return False
    raise ValueError(f"{key} must be a boolean (true/false/1/0/yes/no/on/off)")


def _parse_float(key: str, default: float) -> float:
    value = os.getenv(key)
    if value is None or not value.strip():
        return default
    try:
        return float(value)
    except ValueError as exc:
        raise ValueError(f"{key} must be a number") from exc


def validate_config() -> WineBotConfig:
    """Validate environment variables against the schema (fail closed)."""
    try:
        runtime_mode = os.getenv("MODE", MODE_HEADLESS)
        runtime_default_control = (
            CONTROL_MODE_AGENT_ONLY
            if runtime_mode.strip().lower() == MODE_HEADLESS
            else CONTROL_MODE_HYBRID
        )
        data = {
            "MODE": runtime_mode,
            "BUILD_INTENT": os.getenv("BUILD_INTENT", "rel"),
            "API_TOKEN": os.getenv("API_TOKEN"),
            "WINEBOT_LOG_LEVEL": os.getenv("WINEBOT_LOG_LEVEL", "INFO"),
            "WINEBOT_COMMAND_TIMEOUT": _parse_int("WINEBOT_COMMAND_TIMEOUT", 5),
            "API_PORT": _parse_int("API_PORT", 8000),
            "WINEBOT_DISCOVERY_ALLOW_MULTIPLE": _parse_bool(
                "WINEBOT_DISCOVERY_ALLOW_MULTIPLE", True
            ),
            "WINEBOT_SESSION_ROOT": os.getenv(
                "WINEBOT_SESSION_ROOT", "/artifacts/sessions"
            ),
            "WINEBOT_MAX_SESSIONS": _parse_optional_int("WINEBOT_MAX_SESSIONS"),
            "WINEBOT_SESSION_TTL_DAYS": _parse_optional_int("WINEBOT_SESSION_TTL_DAYS"),
            "WINEBOT_INSTANCE_MODE": os.getenv(
                "WINEBOT_INSTANCE_MODE", LIFECYCLE_MODE_PERSISTENT
            ),
            "WINEBOT_SESSION_MODE": os.getenv(
                "WINEBOT_SESSION_MODE", LIFECYCLE_MODE_PERSISTENT
            ),
            "WINEBOT_INSTANCE_CONTROL_MODE": os.getenv(
                "WINEBOT_INSTANCE_CONTROL_MODE", runtime_default_control
            ),
            "WINEBOT_SESSION_CONTROL_MODE": os.getenv(
                "WINEBOT_SESSION_CONTROL_MODE", runtime_default_control
            ),
            "WINEBOT_USE_CASE_PROFILE": os.getenv("WINEBOT_USE_CASE_PROFILE", ""),
            "WINEBOT_PERFORMANCE_PROFILE": os.getenv(
                "WINEBOT_PERFORMANCE_PROFILE", ""
            ),
            "WINEBOT_ALLOW_HEADLESS_HYBRID": _parse_bool(
                "WINEBOT_ALLOW_HEADLESS_HYBRID", False
            ),
            "WINEBOT_MAX_LOG_SIZE_MB": _parse_int("WINEBOT_MAX_LOG_SIZE_MB", 500),
            "WINEBOT_MAX_SCREENSHOTS_PER_SESSION": _parse_int(
                "WINEBOT_MAX_SCREENSHOTS_PER_SESSION", 1000
            ),
            "WINEBOT_MAX_TRACE_LOAD_MB": _parse_int("WINEBOT_MAX_TRACE_LOAD_MB", 100),
            "WINEBOT_MAX_DETACHED_PROCESSES": _parse_int(
                "WINEBOT_MAX_DETACHED_PROCESSES", 500
            ),
            "PROCESS_STORE_CAP": _parse_int("WINEBOT_MAX_DETACHED_PROCESSES", 500),
            "WINEBOT_MAX_EVENTS_QUERY": _parse_int("WINEBOT_MAX_EVENTS_QUERY", 2000),
            "WINEBOT_MAX_SESSIONS_QUERY": _parse_int(
                "WINEBOT_MAX_SESSIONS_QUERY", 1000
            ),
            "WINEBOT_MAX_LOG_TAIL_LINES": _parse_int(
                "WINEBOT_MAX_LOG_TAIL_LINES", 2000
            ),
            "WINEBOT_MAX_LOG_FOLLOW_STREAMS": _parse_int(
                "WINEBOT_MAX_LOG_FOLLOW_STREAMS", 8
            ),
            "WINEBOT_LOG_FOLLOW_IDLE_TIMEOUT_SECONDS": _parse_int(
                "WINEBOT_LOG_FOLLOW_IDLE_TIMEOUT_SECONDS", 300
            ),
            "WINEBOT_LOG_FOLLOW_ACQUIRE_TIMEOUT_SECONDS": _parse_float(
                "WINEBOT_LOG_FOLLOW_ACQUIRE_TIMEOUT_SECONDS", 0.05
            ),
            "WINEBOT_MAX_OPERATION_RECORDS": _parse_int(
                "WINEBOT_MAX_OPERATION_RECORDS", 500
            ),
            "WINEBOT_OPERATION_RECORD_TTL_SECONDS": _parse_int(
                "WINEBOT_OPERATION_RECORD_TTL_SECONDS", 86400
            ),
            "WINEBOT_RESOURCE_MONITOR_INTERVAL_SECONDS": _parse_int(
                "WINEBOT_RESOURCE_MONITOR_INTERVAL_SECONDS", 5
            ),
            "WINEBOT_SESSION_CLEANUP_INTERVAL_SECONDS": _parse_int(
                "WINEBOT_SESSION_CLEANUP_INTERVAL_SECONDS", 60
            ),
            "WINEBOT_SHUTDOWN_GUARD_TTL_SECONDS": _parse_int(
                "WINEBOT_SHUTDOWN_GUARD_TTL_SECONDS", 120
            ),
            "WINEBOT_INACTIVITY_PAUSE_SECONDS": _parse_int(
                "WINEBOT_INACTIVITY_PAUSE_SECONDS", 180
            ),
            "WINEBOT_INACTIVITY_PAUSE_SECONDS_HUMAN": _parse_optional_int(
                "WINEBOT_INACTIVITY_PAUSE_SECONDS_HUMAN"
            ),
            "WINEBOT_INACTIVITY_PAUSE_SECONDS_AGENT": _parse_optional_int(
                "WINEBOT_INACTIVITY_PAUSE_SECONDS_AGENT"
            ),
            "WINEBOT_INACTIVITY_RESUME_ACTIVITY_SECONDS": _parse_int(
                "WINEBOT_INACTIVITY_RESUME_ACTIVITY_SECONDS", 10
            ),
            "WINEBOT_INACTIVITY_MIN_PAUSE_SECONDS": _parse_int(
                "WINEBOT_INACTIVITY_MIN_PAUSE_SECONDS", 15
            ),
            "WINEBOT_INACTIVITY_RESUME_COOLDOWN_SECONDS": _parse_int(
                "WINEBOT_INACTIVITY_RESUME_COOLDOWN_SECONDS", 10
            ),
            "WINEBOT_MONITOR_HEARTBEAT_SECONDS": _parse_int(
                "WINEBOT_MONITOR_HEARTBEAT_SECONDS", 5
            ),
            "WINEBOT_PERF_METRICS": _parse_bool("WINEBOT_PERF_METRICS", True),
            "WINEBOT_PERF_METRICS_SAMPLE_SECONDS": _parse_int(
                "WINEBOT_PERF_METRICS_SAMPLE_SECONDS", 30
            ),
            "WINEBOT_TELEMETRY": _parse_bool("WINEBOT_TELEMETRY", True),
            "WINEBOT_TELEMETRY_LEVEL": os.getenv("WINEBOT_TELEMETRY_LEVEL", "standard"),
            "WINEBOT_TELEMETRY_FEATURES": os.getenv("WINEBOT_TELEMETRY_FEATURES"),
            "WINEBOT_TELEMETRY_CAPABILITIES": os.getenv("WINEBOT_TELEMETRY_CAPABILITIES"),
            "WINEBOT_TELEMETRY_FEATURE_SETS": os.getenv("WINEBOT_TELEMETRY_FEATURE_SETS"),
            "WINEBOT_TELEMETRY_SAMPLE_RATE": _parse_float(
                "WINEBOT_TELEMETRY_SAMPLE_RATE", 1.0
            ),
            "WINEBOT_TELEMETRY_MAX_EVENTS_PER_MIN": _parse_int(
                "WINEBOT_TELEMETRY_MAX_EVENTS_PER_MIN", 600
            ),
            "WINEBOT_TIMEOUT_AUTOMATION_APP_RUN_SECONDS": _parse_int(
                "WINEBOT_TIMEOUT_AUTOMATION_APP_RUN_SECONDS", 30
            ),
            "WINEBOT_TIMEOUT_AUTOMATION_SCRIPT_SECONDS": _parse_int(
                "WINEBOT_TIMEOUT_AUTOMATION_SCRIPT_SECONDS", 30
            ),
            "WINEBOT_TIMEOUT_RECORDING_CONTROL_SECONDS": _parse_int(
                "WINEBOT_TIMEOUT_RECORDING_CONTROL_SECONDS", 15
            ),
            "WINEBOT_TIMEOUT_RECORDING_STOP_SECONDS": _parse_int(
                "WINEBOT_TIMEOUT_RECORDING_STOP_SECONDS", 20
            ),
            "WINEBOT_TIMEOUT_LIFECYCLE_WINEBOOT_SECONDS": _parse_int(
                "WINEBOT_TIMEOUT_LIFECYCLE_WINEBOOT_SECONDS", 10
            ),
            "WINEBOT_TIMEOUT_LIFECYCLE_WINESERVER_SECONDS": _parse_int(
                "WINEBOT_TIMEOUT_LIFECYCLE_WINESERVER_SECONDS", 5
            ),
            "WINEBOT_TIMEOUT_LIFECYCLE_COMPONENT_SECONDS": _parse_int(
                "WINEBOT_TIMEOUT_LIFECYCLE_COMPONENT_SECONDS", 3
            ),
            "WINEBOT_TIMEOUT_LIFECYCLE_SESSION_HANDOVER_SECONDS": _parse_int(
                "WINEBOT_TIMEOUT_LIFECYCLE_SESSION_HANDOVER_SECONDS", 60
            ),
            "WINEBOT_RECORDER_HEARTBEAT_STALE_SECONDS": _parse_int(
                "WINEBOT_RECORDER_HEARTBEAT_STALE_SECONDS", 30
            ),
            "WINEBOT_RECORDER_HEARTBEAT_GRACE_SECONDS": _parse_int(
                "WINEBOT_RECORDER_HEARTBEAT_GRACE_SECONDS", 15
            ),
            "WINEBOT_RECORDING_INCLUDE_INPUT_TRACES": _parse_bool(
                "WINEBOT_RECORDING_INCLUDE_INPUT_TRACES", True
            ),
            "WINEBOT_RECORDING_REDACT_SENSITIVE": _parse_bool(
                "WINEBOT_RECORDING_REDACT_SENSITIVE", True
            ),
            "WINEBOT_RECORDING_REDACT_FIELDS": os.getenv(
                "WINEBOT_RECORDING_REDACT_FIELDS",
                "key,keycode,text,raw,password,token,secret,clipboard",
            ),
            "WINEBOT_RECORDING_RETENTION_MAX_SEGMENTS": _parse_int(
                "WINEBOT_RECORDING_RETENTION_MAX_SEGMENTS", 0
            ),
            "WINEBOT_RECORDING_RETENTION_MAX_AGE_DAYS": _parse_int(
                "WINEBOT_RECORDING_RETENTION_MAX_AGE_DAYS", 0
            ),
            "WINEBOT_RECORDING_RETENTION_MAX_BYTES": _parse_int(
                "WINEBOT_RECORDING_RETENTION_MAX_BYTES", 0
            ),
            "DISPLAY": os.getenv("DISPLAY", ":99"),
            "SCREEN_RESOLUTION": os.getenv("SCREEN", "1280x720x24"),
        }
        return WineBotConfig(**data)  # type: ignore[arg-type]
    except (ValidationError, ValueError) as exc:
        print(f"--> [FATAL] Configuration validation failed: {exc}")
        sys.exit(1)


config = validate_config()
