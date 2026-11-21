"""Fail-closed single mutating-process admission for one shared session root.

POSIX filesystem lock, not a distributed lock or generation-fencing scheme.
"""

import os
import stat
from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path

try:
    import fcntl
except ImportError:  # WineBot server runs on Linux, not Windows hosts.
    fcntl = None  # type: ignore[assignment]

LOCK_BASENAME = ".winebot-active-writer.lock"


class WriterAdmissionError(RuntimeError):
    """No exclusive mutating-process admission was granted."""


def _acquire_writer_fd(session_root: str) -> int:
    if os.name != "posix" or fcntl is None:
        raise WriterAdmissionError("Exclusive writer admission is unsupported")
    required = ("O_DIRECTORY", "O_NOFOLLOW", "O_CLOEXEC")
    if any(not hasattr(os, flag) for flag in required):
        raise WriterAdmissionError("Secure writer lock operations are unavailable")

    root = Path(session_root)
    if not root.is_absolute() or root.is_symlink():
        raise WriterAdmissionError("Writer session root is not an admitted directory")
    root_fd = None
    writer_fd = None
    try:
        # Directory creation is lock infrastructure only; no session/control
        # state is mutated before this admission has succeeded.
        root.mkdir(mode=0o700, parents=True, exist_ok=True)
        root_fd = os.open(
            root, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW | os.O_CLOEXEC
        )
        if not stat.S_ISDIR(os.fstat(root_fd).st_mode):
            raise WriterAdmissionError("Writer root must be a directory")
        writer_fd = os.open(
            LOCK_BASENAME,
            os.O_RDWR | os.O_CREAT | os.O_NOFOLLOW | os.O_CLOEXEC,
            0o600,
            dir_fd=root_fd,
        )
        lock_stat = os.fstat(writer_fd)
        if (
            not stat.S_ISREG(lock_stat.st_mode)
            or lock_stat.st_nlink != 1
            or lock_stat.st_uid != os.geteuid()
        ):
            raise WriterAdmissionError("Writer lock file identity rejected")
        os.fchmod(writer_fd, 0o600)
        try:
            fcntl.flock(writer_fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError as exc:
            raise WriterAdmissionError(
                "Another WineBot mutating process is admitted"
            ) from exc
        acquired_fd = writer_fd
        writer_fd = None
        return acquired_fd
    except OSError as exc:
        raise WriterAdmissionError("Writer admission filesystem unavailable") from exc
    finally:
        if writer_fd is not None:
            os.close(writer_fd)
        if root_fd is not None:
            os.close(root_fd)


@contextmanager
def admit_single_writer(session_root: str) -> Iterator[None]:
    """Retain one exclusive lock FD across the entire API server lifespan."""
    fd = _acquire_writer_fd(session_root)
    try:
        yield
    finally:
        try:
            fcntl.flock(fd, fcntl.LOCK_UN)
        finally:
            os.close(fd)
