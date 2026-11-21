"""Restart handover recovery tests: synthetic files, no Wine or host effects."""
import json
from pathlib import Path
from unittest.mock import patch

import pytest

from api.core.handover_recovery import reconcile_active_handover


def _session(root: Path, name: str) -> Path:
    path = root / name
    (path / "user").mkdir(parents=True)
    (path / "session.state").write_text("suspended", encoding="utf-8")
    return path


def _write_marker(session: Path, phase: str, extra: dict) -> None:
    (session / "session.transition.json").write_text(
        json.dumps({"phase": phase, "extra": {"operation_id": "op-synthetic", **extra}}),
        encoding="utf-8",
    )


def _profile_link(root: Path, session: Path) -> Path:
    link = root / "active-profile"
    link.symlink_to(session / "user", target_is_directory=True)
    return link


def test_without_marker_is_noop(tmp_path):
    current = _session(tmp_path, "A")
    assert reconcile_active_handover(str(current), str(tmp_path / "absent")) == "no_marker"
    assert (current / "session.state").read_text() == "suspended"


def test_crash_after_active_pointer_update_converges_target(tmp_path):
    old = _session(tmp_path, "A")
    target = _session(tmp_path, "B")
    profile = _profile_link(tmp_path, target)
    _write_marker(target, "resume_target_prepare", {"previous_session": str(old)})
    _write_marker(old, "resume_handover_out", {"target_session": str(target)})
    # Simulate crash with both persisted sessions incorrectly still ACTIVE.
    (old / "session.state").write_text("active", encoding="utf-8")
    assert reconcile_active_handover(str(target), str(profile)) == "reconciled"
    assert (target / "session.state").read_text() == "active"
    assert (old / "session.state").read_text() == "suspended"
    assert not (target / "session.transition.json").exists()
    assert not (old / "session.transition.json").exists()
    assert reconcile_active_handover(str(target), str(profile)) == "no_marker"


def test_crash_before_active_pointer_update_keeps_old_owner(tmp_path):
    old = _session(tmp_path, "A")
    target = _session(tmp_path, "B")
    profile = _profile_link(tmp_path, old)
    _write_marker(old, "resume_handover_out", {"target_session": str(target)})
    _write_marker(target, "resume_target_prepare", {"previous_session": str(old)})
    (target / "session.state").write_text("active", encoding="utf-8")
    assert reconcile_active_handover(str(old), str(profile)) == "reconciled"
    assert (old / "session.state").read_text() == "active"
    assert (target / "session.state").read_text() == "suspended"
    assert not (old / "session.transition.json").exists()
    assert not (target / "session.transition.json").exists()


def test_pointer_switch_without_recipient_peer_intent_fails_closed(tmp_path):
    old = _session(tmp_path, "A")
    target = _session(tmp_path, "B")
    profile = _profile_link(tmp_path, target)
    _write_marker(target, "resume_target_prepare", {"previous_session": str(old)})
    with pytest.raises(RuntimeError, match="Absent handover peer marker"):
        reconcile_active_handover(str(target), str(profile))
    assert (target / "session.transition.json").exists()
    assert (target / "session.state").read_text() != "active"


def test_profile_link_mismatch_fails_closed_without_deleting_intent(tmp_path):
    old = _session(tmp_path, "A")
    target = _session(tmp_path, "B")
    profile = _profile_link(tmp_path, old)
    _write_marker(target, "resume_target_prepare", {"previous_session": str(old)})
    with pytest.raises(RuntimeError, match="profile link disagrees"):
        reconcile_active_handover(str(target), str(profile))
    assert (target / "session.transition.json").exists()


def test_conflicting_peer_operation_fails_closed(tmp_path):
    old = _session(tmp_path, "A")
    target = _session(tmp_path, "B")
    profile = _profile_link(tmp_path, target)
    _write_marker(target, "resume_target_prepare", {"previous_session": str(old)})
    _write_marker(old, "resume_handover_out", {"target_session": str(target)})
    peer = old / "session.transition.json"
    data = json.loads(peer.read_text())
    data["extra"]["operation_id"] = "op-foreign"
    peer.write_text(json.dumps(data), encoding="utf-8")
    with pytest.raises(RuntimeError, match="Conflicting"):
        reconcile_active_handover(str(target), str(profile))
    assert (target / "session.transition.json").exists()
    assert peer.exists()


def test_unsafe_external_peer_is_rejected(tmp_path):
    root = tmp_path / "sessions"
    _session(root, "A")
    target = _session(root, "B")
    profile = _profile_link(tmp_path, target)
    _write_marker(target, "resume_target_prepare", {"previous_session": str(tmp_path)})
    with pytest.raises(RuntimeError, match="outside current session root"):
        reconcile_active_handover(str(target), str(profile))
    assert (target / "session.transition.json").exists()


def test_malformed_marker_fails_closed(tmp_path):
    target = _session(tmp_path, "B")
    profile = _profile_link(tmp_path, target)
    (target / "session.transition.json").write_text("{not-json", encoding="utf-8")
    with pytest.raises(RuntimeError, match="Invalid handover marker"):
        reconcile_active_handover(str(target), str(profile))


def test_live_resume_profile_link_is_verified_fail_closed(tmp_path, monkeypatch):
    from api.routers.lifecycle import _link_profile_checked

    prefix = tmp_path / "wineprefix"
    user = tmp_path / "A" / "user"
    user.mkdir(parents=True)
    monkeypatch.setenv("WINEPREFIX", str(prefix))
    _link_profile_checked(str(user))
    link = prefix / "drive_c" / "users" / "winebot"
    assert link.is_symlink()
    assert link.resolve() == user.resolve()

    other_user = tmp_path / "B" / "user"
    other_user.mkdir(parents=True)
    # Model a failed linker: it silently returns while leaving the old link.
    with patch("api.routers.lifecycle.link_wine_user_dir"):
        with pytest.raises(RuntimeError, match="profile link verification failed"):
            _link_profile_checked(str(other_user))
    assert link.resolve() == user.resolve()


def test_replay_after_peer_cleanup_removes_remaining_marker(tmp_path):
    old = _session(tmp_path, "A")
    target = _session(tmp_path, "B")
    profile = _profile_link(tmp_path, target)
    (target / "session.state").write_text("active", encoding="utf-8")
    _write_marker(target, "resume_target_prepare", {"previous_session": str(old)})
    # Crash after unlink+fsync of the old peer marker; persisted states
    # have already safely converged, so only active-side cleanup remains.
    assert reconcile_active_handover(str(target), str(profile)) == "reconciled"
    assert not (target / "session.transition.json").exists()
    assert (old / "session.state").read_text() == "suspended"


def test_incomplete_cleanup_without_peer_marker_is_quarantined(tmp_path):
    old = _session(tmp_path, "A")
    target = _session(tmp_path, "B")
    profile = _profile_link(tmp_path, target)
    (old / "session.state").write_text("active", encoding="utf-8")
    _write_marker(target, "resume_target_prepare", {"previous_session": str(old)})
    with pytest.raises(RuntimeError, match="Absent handover peer marker"):
        reconcile_active_handover(str(target), str(profile))
    assert (target / "session.transition.json").exists()
    assert (old / "session.state").read_text() == "active"
