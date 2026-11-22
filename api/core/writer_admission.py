"""Fail-closed single mutating-process admission for one shared session root.

POSIX filesystem lock, not a distributed lock or generation-fencing scheme.
"""

import os
import stat
import sys
from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path

try:
    import fcntl
except ImportError:  # WineBot server runs on Linux, not Windows hosts.
    fcntl = None  # type: ignore[assignment]

try:
    import pwd
except ImportError:  # Source imports remain portable; runtime fails closed.
    pwd = None  # type: ignore[assignment]

LOCK_BASENAME = ".winebot-active-writer.lock"
WRITER_FD_ENV = "WINEBOT_WRITER_LOCK_FD"
WRITER_ROOT_ENV = "WINEBOT_WRITER_LOCK_ROOT"
DEFAULT_SESSION_ROOT = "/artifacts/sessions"


class WriterAdmissionError(RuntimeError):
    """No exclusive mutating-process admission was granted."""


def _acquire_writer_fd(session_root: str) -> int:
    if os.name != "posix" or fcntl is None:
        raise WriterAdmissionError("Exclusive writer admission is unsupported")
    required = ("O_DIRECTORY", "O_NOFOLLOW", "O_CLOEXEC")
    if any(not hasattr(os, flag) for flag in required):
        raise WriterAdmissionError("Secure writer lock operations are unavailable")

    root = Path(session_root)
    if (
        not root.is_absolute()
        or root.is_symlink()
        or os.path.realpath(root) != str(root)
    ):
        raise WriterAdmissionError("Writer session root is not an admitted directory")
    root_fd = None
    writer_fd = None
    try:
        # Directory creation is lock infrastructure only; no session/control
        # state is mutated before this admission has succeeded.
        # Refuse to create arbitrary parent trees or traverse symlink aliases.
        # Normal WineBot mounts already provide the /artifacts parent.
        root.mkdir(mode=0o700, parents=False, exist_ok=True)
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
        # A root-launched legacy entrypoint may have chowned the previous
        # writer lock to the winebot UID before its next root invocation.
        allowed_owners = {os.geteuid()}
        if os.geteuid() == 0:
            if pwd is None:
                raise WriterAdmissionError("Writer account resolution unavailable")
            allowed_owners.add(pwd.getpwnam("winebot").pw_uid)
        if (
            not stat.S_ISREG(lock_stat.st_mode)
            or lock_stat.st_nlink != 1
            or lock_stat.st_uid not in allowed_owners
            or bool(stat.S_IMODE(lock_stat.st_mode) & 0o077)
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


def validate_inherited_writer_fd(session_root: str) -> int:
    """Validate the exact entrypoint OFD; never release its shared lock."""
    if os.name != "posix" or fcntl is None:
        raise WriterAdmissionError("Inherited admission is unsupported")
    root = Path(session_root)
    if (
        not root.is_absolute()
        or root.is_symlink()
        or os.path.realpath(root) != str(root)
        or os.environ.get(WRITER_ROOT_ENV) != session_root
    ):
        raise WriterAdmissionError("Inherited writer admission root mismatch")
    raw_fd = os.environ.get(WRITER_FD_ENV, "")
    if not raw_fd.isdecimal() or len(raw_fd) > 8:
        raise WriterAdmissionError("Missing or invalid inherited writer FD")
    fd = int(raw_fd)
    if fd < 3:
        raise WriterAdmissionError("Inherited writer FD is reserved")
    try:
        opened = os.fstat(fd)
        on_disk = os.stat(root / LOCK_BASENAME, follow_symlinks=False)
        if (
            not stat.S_ISREG(opened.st_mode)
            or not stat.S_ISREG(on_disk.st_mode)
            or opened.st_nlink != 1
            or opened.st_dev != on_disk.st_dev
            or opened.st_ino != on_disk.st_ino
            or bool(stat.S_IMODE(opened.st_mode) & 0o077)
        ):
            raise WriterAdmissionError("Inherited writer lock identity mismatch")
        # A genuine child sees the same kernel open-file description; an
        # unrelated holder's OFD rejects this nonblocking flock attempt.
        fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
    except OSError as exc:
        raise WriterAdmissionError("Inherited writer admission unavailable") from exc
    return fd


@contextmanager
def admit_single_writer(session_root: str) -> Iterator[None]:
    """Use entrypoint-held admission or acquire standalone API ownership."""
    if WRITER_FD_ENV in os.environ or WRITER_ROOT_ENV in os.environ:
        validate_inherited_writer_fd(session_root)
        # Calling LOCK_UN on an inherited FD would unlock the entrypoint.
        yield
        return
    fd = _acquire_writer_fd(session_root)
    try:
        yield
    finally:
        try:
            fcntl.flock(fd, fcntl.LOCK_UN)
        finally:
            os.close(fd)


def _exec_entrypoint(arguments: list[str]) -> None:
    """Acquire once, before any shell/setup mutation, then exec with FD."""
    if WRITER_FD_ENV in os.environ or WRITER_ROOT_ENV in os.environ:
        raise WriterAdmissionError("Already carrying writer admission")
    root = os.getenv("WINEBOT_SESSION_ROOT", DEFAULT_SESSION_ROOT)
    acquired = _acquire_writer_fd(root)
    try:
        # Reserve a high descriptor so bash temporary descriptors do not
        # collide with the shared admission during root->gosu->API execs.
        fd = fcntl.fcntl(acquired, fcntl.F_DUPFD, 200)
    finally:
        os.close(acquired)
    try:
        os.set_inheritable(fd, True)
        environment = dict(os.environ)
        environment[WRITER_FD_ENV] = str(fd)
        environment[WRITER_ROOT_ENV] = root
        os.execve("/entrypoint.sh", ["/entrypoint.sh", *arguments], environment)
    finally:
        # Only on failed exec; otherwise kernel owns the lifetime of all
        # inherited references. No unlink or unlocked handoff is permitted.
        os.close(fd)


def main(arguments: list[str] | None = None) -> int:
    arguments = list(sys.argv[1:] if arguments is None else arguments)
    try:
        if arguments[:1] == ["--exec-entrypoint"]:
            _exec_entrypoint(arguments[1:])
            return 0
        if arguments == ["--validate-inherited"]:
            validate_inherited_writer_fd(
                os.getenv("WINEBOT_SESSION_ROOT", DEFAULT_SESSION_ROOT)
            )
            return 0
        raise WriterAdmissionError("Invalid writer admission command")
    except (OSError, WriterAdmissionError, KeyError):
        # Source-safe diagnostic: no paths, environment values or credentials.
        print("WINEBOT_WRITER_ADMISSION=REJECTED", file=sys.stderr)
        return 73


if __name__ == "__main__":
    sys.exit(main())
