from enum import Enum

from pydantic import BaseModel, Field


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
    lease_expiry: float | None = None
    user_intent: UserIntent
    agent_status: AgentStatus
    instance_control_mode: ControlPolicyMode = ControlPolicyMode.HYBRID
    session_control_mode: ControlPolicyMode = ControlPolicyMode.HYBRID
    effective_control_mode: ControlPolicyMode = ControlPolicyMode.HYBRID


class GrantControlModel(BaseModel):
    lease_seconds: int = Field(ge=1, le=86400)
    user_ack: bool = False
    challenge_token: str | None = None


class UserIntentModel(BaseModel):
    intent: UserIntent


class ControlPolicyModeModel(BaseModel):
    mode: ControlPolicyMode


class ClickModel(BaseModel):
    x: int
    y: int
    button: int = Field(default=1, ge=1, le=3)
    window_title: str | None = None
    window_id: str | None = None
    relative: bool = False


class KeyModel(BaseModel):
    keys: str
    window_title: str | None = None
    window_id: str | None = None
    backend: str | None = None


class AHKModel(BaseModel):
    script: str
    focus_title: str | None = None


class AutoItModel(BaseModel):
    script: str
    focus_title: str | None = None


class PythonScriptModel(BaseModel):
    script: str


class AppRunModel(BaseModel):
    path: str
    args: str | None = ""
    detach: bool = False


class WinedbgRunModel(BaseModel):
    path: str
    args: str | None = ""
    detach: bool = False
    mode: str | None = "gdb"
    port: int | None = None
    no_start: bool = False
    command: str | None = None
    script: str | None = None


class InspectWindowModel(BaseModel):
    title: str | None = None
    text: str | None = ""
    handle: str | None = None
    include_controls: bool = True
    max_controls: int = Field(default=200, ge=1, le=2000)
    list_only: bool = False
    include_empty: bool = False


class FocusModel(BaseModel):
    window_id: str


class RecordingStartModel(BaseModel):
    session_label: str | None = None
    session_root: str | None = None
    display: str | None = None
    resolution: str | None = None
    fps: int | None = Field(default=30, ge=1, le=120)
    new_session: bool | None = False


class RecordingActionResponse(BaseModel):
    action: RecordingAction
    status: str
    result: RecordingActionResult
    converged: bool
    recording_timeline_id: str | None = None
    session_dir: str | None = None
    operation_id: str | None = None
    warning: str | None = None


class RecordingStartResponse(RecordingActionResponse):
    session_id: str | None = None
    segment: int | None = None
    output_file: str | None = None
    events_file: str | None = None
    display: str | None = None
    resolution: str | None = None
    fps: int | None = None
    recorder_pid: int | None = None


class SessionResumeModel(BaseModel):
    session_id: str | None = None
    session_dir: str | None = None
    session_root: str | None = None
    restart_wine: bool | None = True
    stop_recording: bool | None = True


class SessionSuspendModel(BaseModel):
    session_id: str | None = None
    session_dir: str | None = None
    session_root: str | None = None
    shutdown_wine: bool | None = True
    stop_recording: bool | None = True


class InputTraceStartModel(BaseModel):
    session_id: str | None = None
    session_dir: str | None = None
    session_root: str | None = None
    include_raw: bool | None = False
    motion_sample_ms: int | None = Field(default=0, ge=0, le=5000)


class InputTraceX11CoreStartModel(BaseModel):
    session_id: str | None = None
    session_dir: str | None = None
    session_root: str | None = None
    motion_sample_ms: int | None = Field(default=0, ge=0, le=5000)


class InputTraceX11CoreStopModel(BaseModel):
    session_id: str | None = None
    session_dir: str | None = None
    session_root: str | None = None


class InputTraceStopModel(BaseModel):
    session_id: str | None = None
    session_dir: str | None = None
    session_root: str | None = None


class InputTraceClientStartModel(BaseModel):
    session_id: str | None = None
    session_dir: str | None = None
    session_root: str | None = None


class InputTraceClientStopModel(BaseModel):
    session_id: str | None = None
    session_dir: str | None = None
    session_root: str | None = None


class InputTraceWindowsStartModel(BaseModel):
    session_id: str | None = None
    session_dir: str | None = None
    session_root: str | None = None
    motion_sample_ms: int | None = Field(default=10, ge=0, le=5000)
    debug_keys: list[str] | None = None
    debug_keys_csv: str | None = None
    debug_sample_ms: int | None = Field(default=200, ge=1, le=10000)
    backend: str | None = None


class InputTraceWindowsStopModel(BaseModel):
    session_id: str | None = None
    session_dir: str | None = None
    session_root: str | None = None
