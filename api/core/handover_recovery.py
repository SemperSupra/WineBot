"""Conservative restart reconciliation for an interrupted session handover.

Only the current active-session pointer is authoritative on restart. We never
guess another session from loose markers or accept paths outside the current
session's parent directory. No Wine process is started by this reconciler.
"""
import json
import os
from pathlib import Path

from api.core.constants import SESSION_STATE_ACTIVE, SESSION_STATE_SUSPENDED
from api.utils.files import read_session_state, write_session_state

MARKER_NAME = "session.transition.json"
_MAX_MARKER_BYTES = 16384


def _safe_peer(raw: object, active: Path) -> Path | None:
    if raw is None:
        return None
    if not isinstance(raw, str) or not raw:
        raise RuntimeError("Invalid handover peer")
    path = Path(raw)
    if not path.is_absolute() or path.is_symlink():
        raise RuntimeError("Invalid handover peer")
    resolved = path.resolve(strict=True)
    if resolved.parent != active.parent or not resolved.is_dir():
        raise RuntimeError("Handover peer is outside current session root")
    return resolved


def _marker(session: Path) -> dict | None:
    path = session / MARKER_NAME
    if path.is_symlink():
        raise RuntimeError("Refusing symlink handover marker")
    if not path.exists():
        return None
    if path.stat().st_size > _MAX_MARKER_BYTES:
        raise RuntimeError("Oversized handover marker")
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError) as exc:
        raise RuntimeError("Invalid handover marker") from exc
    if not isinstance(data, dict) or not isinstance(data.get("extra"), dict):
        raise RuntimeError("Invalid handover marker envelope")
    if not isinstance(data["extra"].get("operation_id"), str):
        raise RuntimeError("Missing handover operation identity")
    return data


def _remove_durable(session: Path) -> None:
    path = session / MARKER_NAME
    if path.is_symlink():
        raise RuntimeError("Refusing symlink handover marker")
    if path.exists():
        path.unlink()
        directory_fd = os.open(str(session), os.O_RDONLY)
        try:
            os.fsync(directory_fd)
        finally:
            os.close(directory_fd)


def reconcile_active_handover(session_dir: str, profile_link: str) -> str:
    """Converge interrupted ownership to the active pointer, fail closed.

    Call only after the runtime has relinked the user profile and updated its
    in-process broker for the active session. Reconcile no other session unless
    its marker matches the exact same operation and points back to active.
    """
    active = Path(session_dir).resolve(strict=True)
    marker = _marker(active)
    if marker is None:
        return "no_marker"
    if not active.is_dir() or not (active / "user").is_dir():
        raise RuntimeError("Active session profile unavailable")
    link = Path(profile_link)
    if not link.is_symlink() or link.resolve(strict=True) != (active / "user").resolve():
        raise RuntimeError("Active Wine profile link disagrees with session pointer")

    phase = marker.get("phase")
    extra = marker["extra"]
    operation_id = extra["operation_id"]
    if phase == "resume_target_prepare":
        peer = _safe_peer(extra.get("previous_session"), active)
        if peer is not None and peer != active:
            other = _marker(peer)
            # The original transaction writes BOTH markers before changing
            # the active pointer. A missing peer marker at this phase is not
            # an admissible crash outcome, and must remain quarantined.
            if other is None:
                # Crash after deleting a peer marker is replayable only if
                # both persisted owners already reached the safe end state.
                if (read_session_state(str(active)) != SESSION_STATE_ACTIVE or
                    read_session_state(str(peer)) == SESSION_STATE_ACTIVE):
                    raise RuntimeError("Absent handover peer marker before commit")
            elif (other.get("phase") != "resume_handover_out" or
                  other["extra"].get("operation_id") != operation_id or
                  _safe_peer(other["extra"].get("target_session"), peer) != active):
                raise RuntimeError("Conflicting handover peer marker")
        if peer is not None and peer != active:
            if read_session_state(str(peer)) == SESSION_STATE_ACTIVE:
                write_session_state(str(peer), SESSION_STATE_SUSPENDED)
        write_session_state(str(active), SESSION_STATE_ACTIVE)
        if peer is not None and peer != active:
            _remove_durable(peer)
    elif phase == "resume_handover_out":
        peer = _safe_peer(extra.get("target_session"), active)
        if peer is not None and peer != active:
            other = _marker(peer)
            if other is None:
                if (read_session_state(str(active)) != SESSION_STATE_ACTIVE or
                    read_session_state(str(peer)) == SESSION_STATE_ACTIVE):
                    raise RuntimeError("Absent handover peer marker before commit")
            elif (other.get("phase") != "resume_target_prepare" or
                  other["extra"].get("operation_id") != operation_id or
                  _safe_peer(other["extra"].get("previous_session"), peer) != active):
                raise RuntimeError("Conflicting handover peer marker")
            # Even a stray target ACTIVE must not leave dual active state.
            if read_session_state(str(peer)) == SESSION_STATE_ACTIVE:
                write_session_state(str(peer), SESSION_STATE_SUSPENDED)
        write_session_state(str(active), SESSION_STATE_ACTIVE)
        if peer is not None and peer != active:
            _remove_durable(peer)
    else:
        raise RuntimeError("Unknown handover phase")

    _remove_durable(active)
    return "reconciled"
