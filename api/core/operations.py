import os
import time
import uuid
import asyncio
from typing import Any, Dict, List, Optional


def _env_int(name: str, default: int, minimum: int = 1) -> int:
    raw = os.getenv(name)
    if raw is None or not raw.strip():
        return default
    try:
        value = int(raw)
    except Exception:
        return default
    return max(minimum, value)


_OPERATION_MAX_ENTRIES = _env_int("WINEBOT_MAX_OPERATION_RECORDS", 500, minimum=10)
_OPERATION_TTL_SECONDS = _env_int("WINEBOT_OPERATION_RECORD_TTL_SECONDS", 86400, minimum=60)

_lock = asyncio.Lock()
_ops: Dict[str, Dict[str, Any]] = {}


def _now_iso() -> str:
    return time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())


def _now_epoch_ms() -> int:
    return int(time.time() * 1000)


def _prune_locked(now_ms: int) -> None:
    cutoff = now_ms - (_OPERATION_TTL_SECONDS * 1000)
    stale = [
        op_id
        for op_id, item in _ops.items()
        if int(item.get("updated_epoch_ms", 0)) < cutoff
    ]
    for op_id in stale:
        _ops.pop(op_id, None)
    if len(_ops) <= _OPERATION_MAX_ENTRIES:
        return
    # Evict oldest by updated time.
    ordered = sorted(
        _ops.items(), key=lambda pair: int(pair[1].get("updated_epoch_ms", 0))
    )
    excess = len(_ops) - _OPERATION_MAX_ENTRIES
    for op_id, _ in ordered[:excess]:
        _ops.pop(op_id, None)


async def create_operation(
    kind: str,
    session_dir: Optional[str] = None,
    metadata: Optional[Dict[str, Any]] = None,
) -> str:
    operation_id = f"op-{uuid.uuid4().hex[:12]}"
    now_ms = _now_epoch_ms()
    item: Dict[str, Any] = {
        "operation_id": operation_id,
        "kind": kind,
        "status": "running",
        "session_dir": session_dir,
        "created_at": _now_iso(),
        "updated_at": _now_iso(),
        "updated_epoch_ms": now_ms,
        "heartbeat_at": _now_iso(),
        "heartbeat_epoch_ms": now_ms,
        "progress": 0,
        "message": "started",
        "error": "",
        "result": {},
        "phases": [],
    }
    if metadata:
        item["metadata"] = dict(metadata)
    async with _lock:
        _prune_locked(now_ms)
        _ops[operation_id] = item
    return operation_id


async def heartbeat_operation(
    operation_id: str,
    phase: str,
    message: str,
    progress: int,
    extra: Optional[Dict[str, Any]] = None,
) -> None:
    now_ms = _now_epoch_ms()
    progress = max(0, min(100, int(progress)))
    async with _lock:
        item = _ops.get(operation_id)
        if not item:
            return
        item["updated_at"] = _now_iso()
        item["updated_epoch_ms"] = now_ms
        item["heartbeat_at"] = item["updated_at"]
        item["heartbeat_epoch_ms"] = now_ms
        item["progress"] = progress
        item["message"] = message
        phase_entry: Dict[str, Any] = {
            "phase": phase,
            "status": "running",
            "message": message,
            "timestamp": item["updated_at"],
            "progress": progress,
        }
        if extra:
            phase_entry["extra"] = dict(extra)
        phases = item.setdefault("phases", [])
        phases.append(phase_entry)
        if len(phases) > 200:
            del phases[:-200]


async def complete_operation(
    operation_id: str, result: Optional[Dict[str, Any]] = None
) -> None:
    now_ms = _now_epoch_ms()
    async with _lock:
        item = _ops.get(operation_id)
        if not item:
            return
        item["status"] = "succeeded"
        item["progress"] = 100
        item["updated_at"] = _now_iso()
        item["updated_epoch_ms"] = now_ms
        item["heartbeat_at"] = item["updated_at"]
        item["heartbeat_epoch_ms"] = now_ms
        item["message"] = "completed"
        if result is not None:
            item["result"] = result


async def fail_operation(
    operation_id: str, error: str, result: Optional[Dict[str, Any]] = None
) -> None:
    now_ms = _now_epoch_ms()
    async with _lock:
        item = _ops.get(operation_id)
        if not item:
            return
        item["status"] = "failed"
        item["updated_at"] = _now_iso()
        item["updated_epoch_ms"] = now_ms
        item["heartbeat_at"] = item["updated_at"]
        item["heartbeat_epoch_ms"] = now_ms
        item["message"] = "failed"
        item["error"] = (error or "").strip()
        if result is not None:
            item["result"] = result


async def get_operation(operation_id: str) -> Optional[Dict[str, Any]]:
    async with _lock:
        item = _ops.get(operation_id)
        if not item:
            return None
        return dict(item)


async def list_operations(limit: int = 50) -> List[Dict[str, Any]]:
    limit = max(1, min(int(limit), 500))
    async with _lock:
        items = sorted(
            _ops.values(),
            key=lambda item: int(item.get("updated_epoch_ms", 0)),
            reverse=True,
        )
        return [dict(item) for item in items[:limit]]

