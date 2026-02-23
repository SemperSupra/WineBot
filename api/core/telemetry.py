import os
import random
import threading
import time
import datetime
from collections import deque
from typing import Dict, Any, Optional, Set

from api.core.versioning import EVENT_SCHEMA_VERSION
from api.utils.files import (
    append_trace_event,
    performance_metrics_log_path,
    session_id_from_dir,
)


_rate_lock = threading.Lock()
_event_timestamps: deque[float] = deque()  # epoch seconds


def _env_bool(name: str, default: bool) -> bool:
    raw = os.getenv(name)
    if raw is None:
        return default
    return raw.strip().lower() in {"1", "true", "yes", "on"}


def _env_float(name: str, default: float) -> float:
    raw = os.getenv(name)
    if raw is None or not raw.strip():
        return default
    try:
        value = float(raw)
    except Exception:
        return default
    return max(0.0, min(1.0, value))


def _env_int(name: str, default: int, minimum: int = 1) -> int:
    raw = os.getenv(name)
    if raw is None or not raw.strip():
        return default
    try:
        value = int(raw)
    except Exception:
        return default
    return max(minimum, value)


def _csv_set(value: Optional[str]) -> Set[str]:
    if not value:
        return set()
    return {item.strip() for item in value.split(",") if item.strip()}


def _allowlist_match(value: str, allowlist: Set[str]) -> bool:
    if not allowlist:
        return True
    return value in allowlist


def _rate_limit_ok(max_events_per_min: int) -> bool:
    now = time.time()
    window_start = now - 60.0
    with _rate_lock:
        while _event_timestamps and _event_timestamps[0] < window_start:
            _event_timestamps.popleft()
        if len(_event_timestamps) >= max_events_per_min:
            return False
        _event_timestamps.append(now)
    return True


def telemetry_enabled() -> bool:
    return _env_bool("WINEBOT_TELEMETRY", _env_bool("WINEBOT_PERF_METRICS", True))


def should_emit(feature: str, capability: str, feature_set: str) -> bool:
    if not telemetry_enabled():
        return False
    features = _csv_set(os.getenv("WINEBOT_TELEMETRY_FEATURES", ""))
    capabilities = _csv_set(os.getenv("WINEBOT_TELEMETRY_CAPABILITIES", ""))
    feature_sets = _csv_set(os.getenv("WINEBOT_TELEMETRY_FEATURE_SETS", ""))
    if not _allowlist_match(feature, features):
        return False
    if not _allowlist_match(capability, capabilities):
        return False
    if not _allowlist_match(feature_set, feature_sets):
        return False

    sample_rate = _env_float("WINEBOT_TELEMETRY_SAMPLE_RATE", 1.0)
    if random.random() > sample_rate:
        return False

    max_events_per_min = _env_int("WINEBOT_TELEMETRY_MAX_EVENTS_PER_MIN", 600, minimum=1)
    if not _rate_limit_ok(max_events_per_min):
        return False
    return True


def emit_operation_timing(
    session_dir: Optional[str],
    *,
    feature: str,
    capability: str,
    feature_set: str,
    operation: str,
    duration_ms: float,
    result: str = "ok",
    source: str = "api",
    metric_name: Optional[str] = None,
    tags: Optional[Dict[str, Any]] = None,
    resource: Optional[Dict[str, Any]] = None,
) -> None:
    if not session_dir:
        return
    if not should_emit(feature, capability, feature_set):
        return
    metric = metric_name or f"{feature}.{capability}.{operation}.latency"
    payload: Dict[str, Any] = {
        "schema_version": EVENT_SCHEMA_VERSION,
        "timestamp_utc": datetime.datetime.now(datetime.timezone.utc).isoformat(),
        "timestamp_epoch_ms": int(time.time() * 1000),
        "event": "performance_metric",
        "metric": metric,
        "value_ms": round(float(duration_ms), 3),
        "duration_ms": round(float(duration_ms), 3),
        "feature": feature,
        "capability": capability,
        "feature_set": feature_set,
        "operation": operation,
        "result": result,
        "source": source,
        "session_id": session_id_from_dir(session_dir),
        "telemetry_level": os.getenv("WINEBOT_TELEMETRY_LEVEL", "standard"),
        "git_sha": os.getenv("VCS_REF", ""),
        "build_intent": os.getenv("BUILD_INTENT", ""),
        "runtime_mode": os.getenv("MODE", ""),
    }
    if tags:
        payload["tags"] = tags
    if resource:
        payload["resource"] = resource
    append_trace_event(performance_metrics_log_path(session_dir), payload)
