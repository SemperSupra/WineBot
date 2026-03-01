import json
from dataclasses import dataclass, field, asdict
from typing import Optional, List, Dict, Any

try:
    from api.core.versioning import ARTIFACT_SCHEMA_VERSION, EVENT_SCHEMA_VERSION
except Exception:
    ARTIFACT_SCHEMA_VERSION = "1.0"
    EVENT_SCHEMA_VERSION = "1.0"


@dataclass
class SessionManifest:
    session_id: str
    start_time_epoch: float
    start_time_iso: str
    hostname: str
    display: str
    resolution: str
    fps: int
    recording_timeline_id: Optional[str] = None
    git_sha: Optional[str] = None
    schema_version: str = ARTIFACT_SCHEMA_VERSION

    def to_json(self):
        return json.dumps(asdict(self), indent=2)

    @staticmethod
    def from_json(json_str: str):
        data = json.loads(json_str)
        data.setdefault("schema_version", ARTIFACT_SCHEMA_VERSION)
        return SessionManifest(**data)


@dataclass
class Event:
    session_id: str
    t_rel_ms: int
    t_epoch_ms: int
    level: str  # INFO, WARN, ERROR, DEBUG
    kind: str  # lifecycle, annotation, process, error
    message: str
    pos: Optional[Dict[str, int]] = None  # x, y, w, h
    style: Optional[Dict[str, str]] = None
    tags: List[str] = field(default_factory=list)
    source: Optional[str] = None
    extra: Dict[str, Any] = field(default_factory=dict)
    schema_version: str = EVENT_SCHEMA_VERSION

    def to_json(self):
        # Filter out None values to keep log clean
        d = asdict(self)
        return json.dumps({k: v for k, v in d.items() if v is not None})

    @staticmethod
    def from_json(json_str: str):
        data = json.loads(json_str)
        data.setdefault("schema_version", EVENT_SCHEMA_VERSION)
        return Event(**data)
