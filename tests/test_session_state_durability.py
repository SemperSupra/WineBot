"""Crash-durability checks for authoritative session pointer/state commits.

Temporary synthetic files only; no host Wine profile, real session or input.
"""
import os
import stat
from unittest.mock import patch

import pytest

from api.utils import files


def test_session_pointer_and_state_fsync_parent_directories(tmp_path, monkeypatch):
    actual_fsync = os.fsync
    calls = []

    def recorded_fsync(fd):
        mode = os.fstat(fd).st_mode
        calls.append("directory" if stat.S_ISDIR(mode) else "file")
        return actual_fsync(fd)

    monkeypatch.setattr(files.os, "fsync", recorded_fsync)
    with (
        patch.object(files, "SESSION_FILE", str(tmp_path / "active-session")),
        patch.object(files, "set_current_session_dir"),
    ):
        files.write_session_dir(str(tmp_path / "A"))
    assert calls == ["file", "directory"]
    assert (tmp_path / "active-session").read_text() == str(tmp_path / "A")

    calls.clear()
    state_dir = tmp_path / "A"
    state_dir.mkdir()
    files.write_session_state(str(state_dir), "active")
    assert calls == ["file", "directory"]
    assert (state_dir / "session.state").read_text() == "active"


def test_replace_failure_preserves_previous_state_and_removes_temp(tmp_path):
    state_dir = tmp_path / "B"
    state_dir.mkdir()
    state = state_dir / "session.state"
    state.write_text("suspended")
    with patch.object(files.os, "replace", side_effect=OSError("synthetic crash")):
        with pytest.raises(OSError, match="synthetic crash"):
            files.write_session_state(str(state_dir), "active")
    assert state.read_text() == "suspended"
    assert sorted(p.name for p in state_dir.iterdir()) == ["session.state"]


def test_directory_fsync_failure_is_not_reported_as_committed(tmp_path, monkeypatch):
    state_dir = tmp_path / "C"
    state_dir.mkdir()
    real_fsync = os.fsync
    called_directory = []

    def reject_directory(fd):
        if stat.S_ISDIR(os.fstat(fd).st_mode):
            called_directory.append(True)
            raise OSError("directory sync unavailable")
        return real_fsync(fd)

    monkeypatch.setattr(files.os, "fsync", reject_directory)
    with pytest.raises(OSError, match="directory sync unavailable"):
        files.write_session_state(str(state_dir), "active")
    assert called_directory == [True]
    # Rename may have happened before directory fsync failed. A new process
    # must verify/reconcile state rather than assume this returned success.
    assert (state_dir / "session.state").read_text() == "active"
    assert sorted(p.name for p in state_dir.iterdir()) == ["session.state"]
