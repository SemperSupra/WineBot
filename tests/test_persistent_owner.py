"""Safe synthetic persistent owner CAS and durability regression tests."""

import json
import os
import subprocess
import sys
from pathlib import Path
from unittest.mock import patch

import pytest

from api.core.persistent_owner import (
    OWNER_FILE,
    OwnerGenerationConflict,
    OwnerPointerError,
    commit_persistent_owner,
    read_persistent_owner,
)

pytestmark = pytest.mark.skipif(sys.platform != "linux", reason="Linux root lock only")
REPO_ROOT = Path(__file__).resolve().parents[1]

COMPETITOR = """
import sys
from api.core.persistent_owner import commit_persistent_owner, OwnerGenerationConflict
from api.core.writer_admission import WriterAdmissionError
try:
    commit_persistent_owner(sys.argv[1], sys.argv[2], 0, sys.argv[3])
except (OwnerGenerationConflict, WriterAdmissionError):
    raise SystemExit(43)
"""


def setup_root(tmp_path):
    root = tmp_path / "sessions"
    root.mkdir()
    a, b = root / "A", root / "B"
    a.mkdir()
    b.mkdir()
    return root, a, b


def test_initial_commit_replay_is_idempotent_and_advances_generation(tmp_path):
    root, a, b = setup_root(tmp_path)
    assert read_persistent_owner(str(root)) is None
    first = commit_persistent_owner(str(root), str(a), 0, "operation-1")
    assert first.generation == 1
    assert commit_persistent_owner(str(root), str(a), 0, "operation-1") == first
    new_owner = commit_persistent_owner(str(root), str(b), 1, "operation-2")
    assert new_owner.generation == 2
    assert read_persistent_owner(str(root)) == new_owner
    assert json.loads((root / OWNER_FILE).read_text())["session_dir"] == str(b)


def test_stale_generation_and_reused_operation_fail_without_mutation(tmp_path):
    root, a, b = setup_root(tmp_path)
    commit_persistent_owner(str(root), str(a), 0, "operation-1")
    source = (root / OWNER_FILE).read_bytes()
    with pytest.raises(OwnerGenerationConflict, match="Stale"):
        commit_persistent_owner(str(root), str(b), 0, "operation-2")
    with pytest.raises(OwnerGenerationConflict, match="reused"):
        commit_persistent_owner(str(root), str(b), 0, "operation-1")
    assert (root / OWNER_FILE).read_bytes() == source


def test_external_or_symlink_owner_paths_and_invalid_ops_rejected(tmp_path):
    root, a, _ = setup_root(tmp_path)
    outside = tmp_path / "external"
    outside.mkdir()
    alias = root / "alias"
    alias.symlink_to(a, target_is_directory=True)
    for attempted in (str(outside), str(alias), str(a / ".." / "A")):
        with pytest.raises(OwnerPointerError):
            commit_persistent_owner(str(root), attempted, 0, "operation-1")
    with pytest.raises(OwnerPointerError, match="identity"):
        commit_persistent_owner(str(root), str(a), 0, "../unsafe-id")
    assert read_persistent_owner(str(root)) is None


def test_symlink_or_malformed_persistent_record_fails_closed(tmp_path):
    root, a, _ = setup_root(tmp_path)
    target = root / OWNER_FILE
    target.symlink_to(a)
    with pytest.raises(OwnerPointerError):
        read_persistent_owner(str(root))
    with pytest.raises(OwnerPointerError):
        commit_persistent_owner(str(root), str(a), 0, "operation-1")
    target.unlink()
    target.write_text("{invalid json", encoding="utf-8")
    with pytest.raises(OwnerPointerError, match="malformed"):
        commit_persistent_owner(str(root), str(a), 0, "operation-1")


def test_directory_sync_failure_is_not_acknowledged_as_commit(tmp_path):
    root, a, _ = setup_root(tmp_path)
    real_sync = os.fsync

    def fail_directory_sync(fd):
        if os.fstat(fd).st_mode & 0o170000 == 0o040000:
            raise OSError("synthetic parent fsync denied")
        return real_sync(fd)

    with patch("api.utils.files.os.fsync", side_effect=fail_directory_sync):
        with pytest.raises(OSError, match="synthetic parent"):
            commit_persistent_owner(str(root), str(a), 0, "operation-1")
    # The rename may already have landed; no invented rollback/ACK.
    assert read_persistent_owner(str(root)).generation == 1
    # A retry of that exact operation must repair the parent fsync before
    # it may acknowledge the persisted idempotent owner record.
    with patch("api.core.persistent_owner.os.fsync", wraps=real_sync) as sync:
        replay = commit_persistent_owner(str(root), str(a), 0, "operation-1")
    assert replay.generation == 1
    assert sync.call_count >= 1


def test_two_real_processes_with_same_expected_epoch_only_one_commits(tmp_path):
    root, a, b = setup_root(tmp_path)
    commands = [
        [sys.executable, "-c", COMPETITOR, str(root), str(a), "operation-A"],
        [sys.executable, "-c", COMPETITOR, str(root), str(b), "operation-B"],
    ]
    processes = [
        subprocess.Popen(cmd, cwd=REPO_ROOT, stdout=subprocess.DEVNULL,
                         stderr=subprocess.DEVNULL)
        for cmd in commands
    ]
    try:
        results = [p.wait(timeout=5) for p in processes]
        assert sorted(results) == [0, 43]
        record = read_persistent_owner(str(root))
        assert record.generation == 1
        assert record.session_dir in {str(a), str(b)}
    finally:
        for p in processes:
            if p.poll() is None:
                p.kill()
            p.wait(timeout=3)
