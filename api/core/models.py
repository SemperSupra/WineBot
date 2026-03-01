from pydantic import BaseModel, Field
from typing import Optional, List
from enum import Enum


class RecorderState(str, Enum):
    IDLE = "idle"
    RECORDING = "recording"
    PAUSED = "paused"
    STOPPING = "stopping"


class RecordingActionResult(str, Enum):
    CONVERGED = "converged"
    ACCEPTED = "accepted"


class RecordingAction(str, Enum):
    START = "start"
    STOP = "stop"
    PAUSE = "pause"
    RESUME = "resume"


class ControlMode(str, Enum):
    USER = "USER"
    AGENT = "AGENT"


class ControlPolicyMode(str, Enum):
    HUMAN_ONLY = "human-only"
    AGENT_ONLY = "agent-only"
    HYBRID = "hybrid"


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
    instance_control_mode: ControlPolicyMode = ControlPolicyMode.HYBRID
    session_control_mode: ControlPolicyMode = ControlPolicyMode.HYBRID
    effective_control_mode: ControlPolicyMode = ControlPolicyMode.HYBRID


class GrantControlModel(BaseModel):
    lease_seconds: int = Field(ge=1, le=86400)
    user_ack: bool = False
    challenge_token: Optional[str] = None


class UserIntentModel(BaseModel):
    intent: UserIntent


class ControlPolicyModeModel(BaseModel):
    mode: ControlPolicyMode


class ClickModel(BaseModel):
    x: int
    y: int
    button: int = Field(default=1, ge=1, le=3)
    window_title: Optional[str] = None
    window_id: Optional[str] = None
    relative: bool = False


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
    max_controls: int = Field(default=200, ge=1, le=2000)
    list_only: bool = False
    include_empty: bool = False


class FocusModel(BaseModel):
    window_id: str


class RecordingStartModel(BaseModel):
    session_label: Optional[str] = None
    session_root: Optional[str] = None
    display: Optional[str] = None
    resolution: Optional[str] = None
    fps: Optional[int] = Field(default=30, ge=1, le=120)
    new_session: Optional[bool] = False


class RecordingActionResponse(BaseModel):
    action: RecordingAction
    status: str
    result: RecordingActionResult
    converged: bool
    recording_timeline_id: Optional[str] = None
    session_dir: Optional[str] = None
    operation_id: Optional[str] = None
    warning: Optional[str] = None


class RecordingStartResponse(RecordingActionResponse):
    session_id: Optional[str] = None
    segment: Optional[int] = None
    output_file: Optional[str] = None
    events_file: Optional[str] = None
    display: Optional[str] = None
    resolution: Optional[str] = None
    fps: Optional[int] = None
    recorder_pid: Optional[int] = None


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
    motion_sample_ms: Optional[int] = Field(default=0, ge=0, le=5000)


class InputTraceX11CoreStartModel(BaseModel):
    session_id: Optional[str] = None
    session_dir: Optional[str] = None
    session_root: Optional[str] = None
    motion_sample_ms: Optional[int] = Field(default=0, ge=0, le=5000)


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
    motion_sample_ms: Optional[int] = Field(default=10, ge=0, le=5000)
    debug_keys: Optional[List[str]] = None
    debug_keys_csv: Optional[str] = None
    debug_sample_ms: Optional[int] = Field(default=200, ge=1, le=10000)
    backend: Optional[str] = None


class InputTraceWindowsStopModel(BaseModel):
    session_id: Optional[str] = None
    session_dir: Optional[str] = None
    session_root: Optional[str] = None
