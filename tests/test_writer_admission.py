"""Disposable Linux process-admission and synthetic SIGKILL tests."""

import asyncio
import os
import signal
import subprocess
import sys
import time
from pathlib import Path
from unittest.mock import patch

import pytest

from api.core.writer_admission import WriterAdmissionError, admit_single_writer

pytestmark = pytest.mark.skipif(sys.platform != "linux", reason="Linux POSIX flock only")

PROBE = """
import sys
from api.core.writer_admission import WriterAdmissionError, admit_single_writer
try:
    with admit_single_writer(sys.argv[1]):
        pass
except WriterAdmissionError:
    raise SystemExit(43)
"""
HOLD = """
import sys, time
from pathlib import Path
from api.core.writer_admission import admit_single_writer
with admit_single_writer(sys.argv[1]):
    Path(sys.argv[2]).write_text('ready', encoding='ascii')
    time.sleep(20)
"""


def test_two_independent_open_descriptors_and_processes_admit_only_one(tmp_path):
    with admit_single_writer(str(tmp_path)):
        with pytest.raises(WriterAdmissionError, match="Another WineBot"):
            with admit_single_writer(str(tmp_path)):
                pytest.fail("Unexpected double writer")
        proc = subprocess.run(
            [sys.executable, "-c", PROBE, str(tmp_path)],
            cwd=Path(__file__).resolve().parents[1],
            timeout=4,
            check=False,
        )
        assert proc.returncode == 43
    with admit_single_writer(str(tmp_path)):
        pass


def test_writer_symlink_lock_and_symlink_root_fail_closed(tmp_path):
    root = tmp_path / "root"
    root.mkdir()
    (root / ".winebot-active-writer.lock").symlink_to(tmp_path / "victim")
    with pytest.raises(WriterAdmissionError):
        with admit_single_writer(str(root)):
            pytest.fail("Symlink writer lock admitted")
    alias = tmp_path / "alias"
    alias.symlink_to(root, target_is_directory=True)
    with pytest.raises(WriterAdmissionError):
        with admit_single_writer(str(alias)):
            pytest.fail("Symlink writer root admitted")


def test_sigkill_releases_lock_without_deleting_identity(tmp_path):
    root = tmp_path / "sessions"
    ready = tmp_path / "ready.txt"
    proc = subprocess.Popen(
        [sys.executable, "-c", HOLD, str(root), str(ready)],
        cwd=Path(__file__).resolve().parents[1],
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )
    try:
        for _ in range(200):
            if ready.is_file() or proc.poll() is not None:
                break
            time.sleep(0.01)
        assert ready.is_file(), "Synthetic owner failed to acquire admission"
        with pytest.raises(WriterAdmissionError):
            with admit_single_writer(str(root)):
                pytest.fail("Second writer admitted while owner alive")
        os.kill(proc.pid, signal.SIGKILL)
        proc.wait(timeout=3)
        with admit_single_writer(str(root)):
            assert (root / ".winebot-active-writer.lock").is_file()
    finally:
        if proc.poll() is None:
            proc.kill()
        proc.wait(timeout=3)


def test_relative_root_is_not_admitted():
    with pytest.raises(WriterAdmissionError):
        with admit_single_writer("relative/sessions"):
            pytest.fail("Nonabsolute writer root admitted")


def test_lifespan_rejects_writer_contention_before_instance_mutation():
    from api import server

    async def enter_lifespan():
        async with server.lifespan(server.app):
            pass

    with (
        patch("api.server.admit_single_writer",
              side_effect=WriterAdmissionError("synthetic contention")),
        patch("api.server.write_instance_state") as state_writer,
    ):
        with pytest.raises(WriterAdmissionError, match="synthetic contention"):
            asyncio.run(enter_lifespan())
    state_writer.assert_not_called()
