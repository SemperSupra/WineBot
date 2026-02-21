import os
from typing import Dict, Any, Optional, List
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
    
    # Inactivity
    WINEBOT_INACTIVITY_PAUSE_SECONDS: int = 0
    WINEBOT_MONITOR_HEARTBEAT_SECONDS: int = 5
    
    # Recorder (FFmpeg)
    RECORDER_PRESET: str = "ultrafast"
    RECORDER_CRF: int = 23
    RECORDER_PIX_FMT: str = "yuv420p"

def validate_config() -> WineBotConfig:
    """Validate environment variables against the schema."""
    try:
        # Construct dict from env vars, converting types where needed
        data = {
            "API_TOKEN": os.getenv("API_TOKEN"),
            "WINEBOT_LOG_LEVEL": os.getenv("WINEBOT_LOG_LEVEL", "INFO"),
            "WINEBOT_COMMAND_TIMEOUT": int(os.getenv("WINEBOT_COMMAND_TIMEOUT", "5")),
            "API_PORT": int(os.getenv("API_PORT", "8000")),
            "WINEBOT_DISCOVERY_ALLOW_MULTIPLE": os.getenv("WINEBOT_DISCOVERY_ALLOW_MULTIPLE", "1") == "1",
            "WINEBOT_SESSION_ROOT": os.getenv("WINEBOT_SESSION_ROOT", "/artifacts/sessions"),
            "WINEBOT_MAX_SESSIONS": int(os.getenv("WINEBOT_MAX_SESSIONS")) if os.getenv("WINEBOT_MAX_SESSIONS") else None,
            "WINEBOT_SESSION_TTL_DAYS": int(os.getenv("WINEBOT_SESSION_TTL_DAYS")) if os.getenv("WINEBOT_SESSION_TTL_DAYS") else None,
            "WINEBOT_MAX_LOG_SIZE_MB": int(os.getenv("WINEBOT_MAX_LOG_SIZE_MB", "500")),
            "WINEBOT_MAX_SCREENSHOTS_PER_SESSION": int(os.getenv("WINEBOT_MAX_SCREENSHOTS_PER_SESSION", "1000")),
            "WINEBOT_MAX_TRACE_LOAD_MB": int(os.getenv("WINEBOT_MAX_TRACE_LOAD_MB", "100")),
            "PROCESS_STORE_CAP": int(os.getenv("WINEBOT_MAX_DETACHED_PROCESSES", "500")),
            "WINEBOT_INACTIVITY_PAUSE_SECONDS": int(os.getenv("WINEBOT_INACTIVITY_PAUSE_SECONDS", "0")),
            "WINEBOT_MONITOR_HEARTBEAT_SECONDS": int(os.getenv("WINEBOT_MONITOR_HEARTBEAT_SECONDS", "5")),
            "DISPLAY": os.getenv("DISPLAY", ":99"),
            "SCREEN_RESOLUTION": os.getenv("SCREEN", "1280x720x24"),
        }
        return WineBotConfig(**data)
    except (ValidationError, ValueError) as e:
        print(f"--> [FATAL] Configuration validation failed: {e}")
        import sys
        sys.exit(1)

# Singleton
config = validate_config()
