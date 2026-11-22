"""Synthetic entrypoint-to-API single-OFD admission proof; no Wine effects."""

import os
import signal
import subprocess
import sys
import time
from pathlib import Path
from unittest.mock import patch

import pytest

from api.core.writer_admission import (
    WRITER_FD_ENV,
    WRITER_ROOT_ENV,
    WriterAdmissionError,
    _acquire_writer_fd,
    _exec_entrypoint,
    admit_single_writer,
    validate_inherited_writer_fd,
)

pytestmark = pytest.mark.skipif(sys.platform != "linux", reason="Linux OFD only")
REPO_ROOT = Path(__file__).resolve().parents[1]
INHERITED_WORKER = """
import os, sys, time
from pathlib import Path
from api.core.writer_admission import validate_inherited_writer_fd
validate_inherited_writer_fd(sys.argv[1])
Path(sys.argv[2]).write_text('admitted', encoding='ascii')
time.sleep(20)
"""


def test_entrypoint_exec_passes_same_lock_fd_and_does_not_unlock(tmp_path, monkeypatch):
    root = str(tmp_path / "sessions")
    monkeypatch.setenv("WINEBOT_SESSION_ROOT", root)
    monkeypatch.delenv(WRITER_FD_ENV, raising=False)
    monkeypatch.delenv(WRITER_ROOT_ENV, raising=False)

    class InterceptedExec(Exception):
        pass

    def fake_execve(path, argv, env):
        assert path == "/entrypoint.sh"
        assert argv == [path, "synthetic"]
        assert env[WRITER_ROOT_ENV] == root
        fd = int(env[WRITER_FD_ENV])
        assert fd >= 200 and os.get_inheritable(fd)
        with pytest.raises(WriterAdmissionError, match="Another WineBot"):
            with admit_single_writer(root):
                pytest.fail("Independent writer acquired while wrapper holds FD")
        with patch.dict(os.environ, env):
            assert validate_inherited_writer_fd(root) == fd
            with admit_single_writer(root):
                assert validate_inherited_writer_fd(root) == fd
        raise InterceptedExec

    with patch("api.core.writer_admission.os.execve", side_effect=fake_execve):
        with pytest.raises(InterceptedExec):
            _exec_entrypoint(["synthetic"])
    with admit_single_writer(root):
        pass


def test_real_inherited_fd_survives_exec_and_sigkill(tmp_path):
    root = str(tmp_path / "sessions")
    fd = _acquire_writer_fd(root)
    inherited = os.dup(fd)
    os.set_inheritable(inherited, True)
    os.close(fd)
    ready = tmp_path / "ready"
    env = {
        **os.environ,
        WRITER_FD_ENV: str(inherited),
        WRITER_ROOT_ENV: root,
    }
    proc = subprocess.Popen(
        [sys.executable, "-c", INHERITED_WORKER, root, str(ready)],
        env=env,
        cwd=REPO_ROOT,
        pass_fds=(inherited,),
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )
    try:
        # Parent's descriptor closes without releasing child's inherited OFD.
        os.close(inherited)
        for _ in range(250):
            if ready.exists() or proc.poll() is not None:
                break
            time.sleep(0.01)
        assert ready.exists(), "Synthetic API child did not inherit the writer lock"
        with pytest.raises(WriterAdmissionError, match="Another WineBot"):
            with admit_single_writer(root):
                pytest.fail("Unadmitted writer acquired while child still alive")
        os.kill(proc.pid, signal.SIGKILL)
        proc.wait(timeout=3)
        with admit_single_writer(root):
            pass
    finally:
        if proc.poll() is None:
            proc.kill()
        proc.wait(timeout=3)


def test_root_change_and_spoofed_inherited_fd_fail_closed(tmp_path, monkeypatch):
    root = str(tmp_path / "sessions")
    other = str(tmp_path / "other")
    with admit_single_writer(root):
        monkeypatch.setenv(WRITER_ROOT_ENV, root)
        monkeypatch.setenv(WRITER_FD_ENV, "123456")
        with pytest.raises(WriterAdmissionError):
            with admit_single_writer(root):
                pytest.fail("Fake inherited FD admitted")
        with pytest.raises(WriterAdmissionError, match="root mismatch"):
            validate_inherited_writer_fd(other)


def test_entrypoint_admits_before_all_mutating_setup_and_forbids_fallback():
    entrypoint_path = REPO_ROOT / "docker/entrypoint.sh"
    if not entrypoint_path.is_file():
        # Production/test Docker images install the script at /entrypoint.sh;
        # the source checkout retains its original docker/entrypoint.sh path.
        entrypoint_path = REPO_ROOT / "entrypoint.sh"
    entrypoint = entrypoint_path.read_text(encoding="utf-8")
    infra = (REPO_ROOT / "scripts/init/10-setup-infra.sh").read_text(
        encoding="utf-8"
    )
    assert entrypoint.index("--exec-entrypoint") < entrypoint.index(
        "source /scripts/init/00-setup-user.sh"
    )
    assert entrypoint.index("--exec-entrypoint") < entrypoint.index(
        'write_instance_state "starting"'
    )
    assert entrypoint.index("writer_root_or_fd_changed") < entrypoint.index(
        "source /scripts/init/10-setup-infra.sh"
    )
    assert "SESSION_ROOT_UNAVAILABLE" in infra
    assert infra.index("SESSION_ROOT_UNAVAILABLE") < infra.index(
        'FALLBACK_SESSION_ROOT="/tmp/winebot-sessions"'
    )
