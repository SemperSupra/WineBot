from pydantic import BaseModel
from typing import Optional, List, Dict, Any
from enum import Enum

class RecorderState(str, Enum):
    IDLE = "idle"
    RECORDING = "recording"
    PAUSED = "paused"
    STOPPING = "stopping"

class ControlMode(str, Enum):
    USER = "USER"
    AGENT = "AGENT"

class UserIntent(str, Enum):
    WAIT = "WAIT"
    SAFE_INTERRUPT = "SAFE_INTERRUPT"
    STOP_NOW = "STOP_NOW"

class AgentStatus(str, Enum):
    IDLE = "IDLE"
    RUNNING = "RUNNING"
    PAUSED = "PAUSED"
    STOPPING = "STOPPING"
    STOPPED = "STOPPED"

class ControlState(BaseModel):
    session_id: str
    interactive: bool
    control_mode: ControlMode
    lease_expiry: Optional[float] = None
    user_intent: UserIntent
    agent_status: AgentStatus

class GrantControlModel(BaseModel):
    lease_seconds: int

class UserIntentModel(BaseModel):
    intent: UserIntent

class ClickModel(BaseModel):
    x: int
    y: int

class AHKModel(BaseModel):
    script: str
    focus_title: Optional[str] = None

class AutoItModel(BaseModel):
    script: str
    focus_title: Optional[str] = None

class PythonScriptModel(BaseModel):
    script: str

class AppRunModel(BaseModel):
    path: str
    args: Optional[str] = ""
    detach: bool = False

class WinedbgRunModel(BaseModel):
    path: str
    args: Optional[str] = ""
    detach: bool = False
    mode: Optional[str] = "gdb"
    port: Optional[int] = None
    no_start: bool = False
    command: Optional[str] = None
    script: Optional[str] = None

class InspectWindowModel(BaseModel):
    title: Optional[str] = None
    text: Optional[str] = ""
    handle: Optional[str] = None
    include_controls: bool = True
    max_controls: int = 200
    list_only: bool = False
    include_empty: bool = False

class FocusModel(BaseModel):
    window_id: str

class RecordingStartModel(BaseModel):
    session_label: Optional[str] = None
    session_root: Optional[str] = None
    display: Optional[str] = None
    resolution: Optional[str] = None
    fps: Optional[int] = 30
    new_session: Optional[bool] = False

class SessionResumeModel(BaseModel):
    session_id: Optional[str] = None
    session_dir: Optional[str] = None
    session_root: Optional[str] = None
    restart_wine: Optional[bool] = True
    stop_recording: Optional[bool] = True

class SessionSuspendModel(BaseModel):
    session_id: Optional[str] = None
    session_dir: Optional[str] = None
    session_root: Optional[str] = None
    shutdown_wine: Optional[bool] = True
    stop_recording: Optional[bool] = True

class InputTraceStartModel(BaseModel):
    session_id: Optional[str] = None
    session_dir: Optional[str] = None
    session_root: Optional[str] = None
    include_raw: Optional[bool] = False
    motion_sample_ms: Optional[int] = 0

class InputTraceX11CoreStartModel(BaseModel):
    session_id: Optional[str] = None
    session_dir: Optional[str] = None
    session_root: Optional[str] = None
    motion_sample_ms: Optional[int] = 0

class InputTraceX11CoreStopModel(BaseModel):
    session_id: Optional[str] = None
    session_dir: Optional[str] = None
    session_root: Optional[str] = None

class InputTraceStopModel(BaseModel):
    session_id: Optional[str] = None
    session_dir: Optional[str] = None
    session_root: Optional[str] = None

class InputTraceClientStartModel(BaseModel):
    session_id: Optional[str] = None
    session_dir: Optional[str] = None
    session_root: Optional[str] = None

class InputTraceClientStopModel(BaseModel):
    session_id: Optional[str] = None
    session_dir: Optional[str] = None
    session_root: Optional[str] = None

class InputTraceWindowsStartModel(BaseModel):
    session_id: Optional[str] = None
    session_dir: Optional[str] = None
    session_root: Optional[str] = None
    motion_sample_ms: Optional[int] = 10
    debug_keys: Optional[List[str]] = None
    debug_keys_csv: Optional[str] = None
    debug_sample_ms: Optional[int] = 200
    backend: Optional[str] = None

class InputTraceWindowsStopModel(BaseModel):
    session_id: Optional[str] = None
    session_dir: Optional[str] = None
    session_root: Optional[str] = None