import os
from typing import Optional
from pydantic import BaseModel, Field, ValidationError

class WineBotConfig(BaseModel):
    # Core
    API_TOKEN: Optional[str] = None
    WINEBOT_LOG_LEVEL: str = Field(default="INFO", pattern="^(DEBUG|INFO|WARNING|ERROR|CRITICAL)$")
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
    
    # Resources
    WINEBOT_SESSION_ROOT: str = "/artifacts/sessions"
    WINEBOT_MAX_SESSIONS: Optional[int] = None
    WINEBOT_SESSION_TTL_DAYS: Optional[int] = None
    WINEBOT_MAX_LOG_SIZE_MB: int = 500
    WINEBOT_MAX_SCREENSHOTS_PER_SESSION: int = 1000
    WINEBOT_MAX_TRACE_LOAD_MB: int = 100
    PROCESS_STORE_CAP: int = 500
    WINEBOT_MAX_EVENTS_QUERY: int = 2000
    WINEBOT_MAX_SESSIONS_QUERY: int = 1000
    WINEBOT_MAX_LOG_TAIL_LINES: int = 2000
    WINEBOT_MAX_LOG_FOLLOW_STREAMS: int = 8
    WINEBOT_LOG_FOLLOW_IDLE_TIMEOUT_SECONDS: int = 300
    
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
    
    # Recorder (FFmpeg)
    RECORDER_PRESET: str = "ultrafast"
    RECORDER_CRF: int = 23
    RECORDER_PIX_FMT: str = "yuv420p"

def _get_int(key: str, default: int) -> int:
    val = os.getenv(key)
    if val is None or not val.strip():
        return default
    try:
        return int(val)
    except ValueError:
        return default

def _get_bool(key: str, default: bool) -> bool:
    val = os.getenv(key)
    if val is None or not val.strip():
        return default
    return val.lower() in ("1", "true", "yes")

def validate_config() -> WineBotConfig:
    """Validate environment variables against the schema."""
    try:
        # Construct dict from env vars, converting types where needed
        data = {
            "API_TOKEN": os.getenv("API_TOKEN"),
            "WINEBOT_LOG_LEVEL": os.getenv("WINEBOT_LOG_LEVEL", "INFO"),
            "WINEBOT_COMMAND_TIMEOUT": _get_int("WINEBOT_COMMAND_TIMEOUT", 5),
            "API_PORT": _get_int("API_PORT", 8000),
            "WINEBOT_DISCOVERY_ALLOW_MULTIPLE": _get_bool("WINEBOT_DISCOVERY_ALLOW_MULTIPLE", True),
            "WINEBOT_SESSION_ROOT": os.getenv("WINEBOT_SESSION_ROOT", "/artifacts/sessions"),
            "WINEBOT_MAX_SESSIONS": _get_int("WINEBOT_MAX_SESSIONS", 0) or None,
            "WINEBOT_SESSION_TTL_DAYS": _get_int("WINEBOT_SESSION_TTL_DAYS", 0) or None,
            "WINEBOT_MAX_LOG_SIZE_MB": _get_int("WINEBOT_MAX_LOG_SIZE_MB", 500),
            "WINEBOT_MAX_SCREENSHOTS_PER_SESSION": _get_int("WINEBOT_MAX_SCREENSHOTS_PER_SESSION", 1000),
            "WINEBOT_MAX_TRACE_LOAD_MB": _get_int("WINEBOT_MAX_TRACE_LOAD_MB", 100),
            "PROCESS_STORE_CAP": _get_int("WINEBOT_MAX_DETACHED_PROCESSES", 500),
            "WINEBOT_MAX_EVENTS_QUERY": _get_int("WINEBOT_MAX_EVENTS_QUERY", 2000),
            "WINEBOT_MAX_SESSIONS_QUERY": _get_int("WINEBOT_MAX_SESSIONS_QUERY", 1000),
            "WINEBOT_MAX_LOG_TAIL_LINES": _get_int("WINEBOT_MAX_LOG_TAIL_LINES", 2000),
            "WINEBOT_MAX_LOG_FOLLOW_STREAMS": _get_int("WINEBOT_MAX_LOG_FOLLOW_STREAMS", 8),
            "WINEBOT_LOG_FOLLOW_IDLE_TIMEOUT_SECONDS": _get_int("WINEBOT_LOG_FOLLOW_IDLE_TIMEOUT_SECONDS", 300),
            "WINEBOT_INACTIVITY_PAUSE_SECONDS": _get_int("WINEBOT_INACTIVITY_PAUSE_SECONDS", 180),
            "WINEBOT_INACTIVITY_PAUSE_SECONDS_HUMAN": _get_int("WINEBOT_INACTIVITY_PAUSE_SECONDS_HUMAN", 0) or None,
            "WINEBOT_INACTIVITY_PAUSE_SECONDS_AGENT": _get_int("WINEBOT_INACTIVITY_PAUSE_SECONDS_AGENT", 0) or None,
            "WINEBOT_INACTIVITY_RESUME_ACTIVITY_SECONDS": _get_int("WINEBOT_INACTIVITY_RESUME_ACTIVITY_SECONDS", 10),
            "WINEBOT_INACTIVITY_MIN_PAUSE_SECONDS": _get_int("WINEBOT_INACTIVITY_MIN_PAUSE_SECONDS", 15),
            "WINEBOT_INACTIVITY_RESUME_COOLDOWN_SECONDS": _get_int("WINEBOT_INACTIVITY_RESUME_COOLDOWN_SECONDS", 10),
            "WINEBOT_MONITOR_HEARTBEAT_SECONDS": _get_int("WINEBOT_MONITOR_HEARTBEAT_SECONDS", 5),
            "WINEBOT_PERF_METRICS": _get_bool("WINEBOT_PERF_METRICS", True),
            "WINEBOT_PERF_METRICS_SAMPLE_SECONDS": _get_int("WINEBOT_PERF_METRICS_SAMPLE_SECONDS", 30),
            "WINEBOT_TELEMETRY": _get_bool("WINEBOT_TELEMETRY", True),
            "WINEBOT_TELEMETRY_LEVEL": os.getenv("WINEBOT_TELEMETRY_LEVEL", "standard"),
            "WINEBOT_TELEMETRY_FEATURES": os.getenv("WINEBOT_TELEMETRY_FEATURES"),
            "WINEBOT_TELEMETRY_CAPABILITIES": os.getenv("WINEBOT_TELEMETRY_CAPABILITIES"),
            "WINEBOT_TELEMETRY_FEATURE_SETS": os.getenv("WINEBOT_TELEMETRY_FEATURE_SETS"),
            "WINEBOT_TELEMETRY_SAMPLE_RATE": float(os.getenv("WINEBOT_TELEMETRY_SAMPLE_RATE", "1.0") or "1.0"),
            "WINEBOT_TELEMETRY_MAX_EVENTS_PER_MIN": _get_int("WINEBOT_TELEMETRY_MAX_EVENTS_PER_MIN", 600),
            "DISPLAY": os.getenv("DISPLAY", ":99"),
            "SCREEN_RESOLUTION": os.getenv("SCREEN", "1280x720x24"),
        }
        return WineBotConfig(**(data))  # type: ignore[arg-type]
    except (ValidationError, ValueError) as e:
        print(f"--> [FATAL] Configuration validation failed: {e}")
        import sys
        sys.exit(1)

# Singleton
config = validate_config()
