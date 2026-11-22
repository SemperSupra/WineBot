"""A versioned durable owner pointer primitive for a single admitted Linux root.

Not yet wired to shell startup, resume, or crash reconciliation. An admitted
writer must still prove the host's shared filesystem flock behavior.
"""

import json
import os
import re
import stat
from dataclasses import dataclass
from pathlib import Path

from api.core.writer_admission import admit_single_writer

from api.utils.files import _atomic_write_text

OWNER_FILE = ".winebot-committed-owner.json"
MAX_OWNER_BYTES = 8192
MAX_GENERATION = (1 << 63) - 1
_OPERATION_ID = re.compile(r"^[A-Za-z0-9_.:-]{1,128}$")
_FIELDS = frozenset(("schema_version", "generation", "session_dir", "operation_id"))


class OwnerPointerError(RuntimeError):
    """Persistent owner data is missing trust or schema requirements."""


class OwnerGenerationConflict(OwnerPointerError):
    """A stale generation or operation identity must not commit."""


@dataclass(frozen=True)
class OwnerPointer:
    schema_version: int
    generation: int
    session_dir: str
    operation_id: str


def _root(root: str) -> Path:
    path = Path(root)
    if (
        not path.is_absolute()
        or path.is_symlink()
        or os.path.realpath(path) != str(path)
        or not path.is_dir()
    ):
        raise OwnerPointerError("Persistent control root is not admitted")
    return path


def _session(root: Path, session_dir: str) -> str:
    candidate = Path(session_dir)
    if (
        not candidate.is_absolute()
        or candidate.is_symlink()
        or candidate.parent != root
        or os.path.realpath(candidate) != str(candidate)
        or not candidate.is_dir()
    ):
        raise OwnerPointerError("Persistent owner is not a direct child session")
    return str(candidate)


def _identity(operation_id: str) -> str:
    if not isinstance(operation_id, str) or not _OPERATION_ID.fullmatch(
        operation_id
    ):
        raise OwnerPointerError("Invalid owner operation identity")
    return operation_id


def read_persistent_owner(root: str) -> OwnerPointer | None:
    """Read only a validated root-local record. Corruption is never 'missing'."""
    directory = _root(root)
    target = directory / OWNER_FILE
    try:
        fd = os.open(target, os.O_RDONLY | os.O_NOFOLLOW | os.O_CLOEXEC)
    except FileNotFoundError:
        return None
    except OSError as exc:
        raise OwnerPointerError("Persistent owner record inaccessible") from exc
    try:
        metadata = os.fstat(fd)
        if (
            not stat.S_ISREG(metadata.st_mode)
            or metadata.st_nlink != 1
            or metadata.st_size > MAX_OWNER_BYTES
            or metadata.st_size <= 0
        ):
            raise OwnerPointerError("Persistent owner record identity rejected")
        with os.fdopen(fd, "r", encoding="utf-8") as handle:
            fd = -1
            content = handle.read(MAX_OWNER_BYTES + 1)
        payload = json.loads(content)
    except (OSError, ValueError, UnicodeError) as exc:
        raise OwnerPointerError("Persistent owner record malformed") from exc
    finally:
        if fd >= 0:
            os.close(fd)
    if not isinstance(payload, dict) or set(payload) != _FIELDS:
        raise OwnerPointerError("Unknown persistent owner schema")
    if type(payload["schema_version"]) is not int or payload["schema_version"] != 1:
        raise OwnerPointerError("Unsupported persistent owner schema version")
    gen = payload["generation"]
    if type(gen) is not int or not 0 < gen <= MAX_GENERATION:
        raise OwnerPointerError("Invalid persistent owner generation")
    session_dir = payload["session_dir"]
    if not isinstance(session_dir, str):
        raise OwnerPointerError("Invalid persistent owner session")
    return OwnerPointer(
        schema_version=1,
        generation=gen,
        session_dir=_session(directory, session_dir),
        operation_id=_identity(payload["operation_id"]),
    )


def commit_persistent_owner(
    root: str, session_dir: str, expected_generation: int, operation_id: str
) -> OwnerPointer:
    """Idempotent generation CAS while holding the admitted root writer lock.

    This one-file CAS cannot by itself atomically switch the Wine profile,
    broker state, multiple handover markers, or live guest effects.
    """
    if type(expected_generation) is not int or not 0 <= expected_generation < MAX_GENERATION:
        raise OwnerGenerationConflict("Invalid expected owner generation")
    op = _identity(operation_id)
    # This context shares the entrypoint's exact inherited OFD if present;
    # otherwise it acquires an independent exclusive lock for a direct call.
    with admit_single_writer(root):
        directory = _root(root)
        requested = _session(directory, session_dir)
        current = read_persistent_owner(root)
        if current is not None and current.operation_id == op:
            if (
                current.session_dir == requested
                and current.generation == expected_generation + 1
            ):
                # A prior caller may have seen rename succeed but parent
                # fsync fail. Never ACK its idempotent replay without a
                # fresh successful durability barrier on the same directory.
                directory_fd = os.open(
                    directory,
                    os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW | os.O_CLOEXEC,
                )
                try:
                    os.fsync(directory_fd)
                finally:
                    os.close(directory_fd)
                return current
            raise OwnerGenerationConflict("Owner operation identity reused")
        actual = current.generation if current else 0
        if actual != expected_generation:
            raise OwnerGenerationConflict("Stale persistent owner generation")
        next_record = OwnerPointer(
            schema_version=1,
            generation=actual + 1,
            session_dir=requested,
            operation_id=op,
        )
        payload = {
            "schema_version": next_record.schema_version,
            "generation": next_record.generation,
            "session_dir": next_record.session_dir,
            "operation_id": next_record.operation_id,
        }
        if (directory / OWNER_FILE).is_symlink():
            raise OwnerPointerError("Symlink persistent owner record rejected")
        _atomic_write_text(str(directory / OWNER_FILE), json.dumps(payload, sort_keys=True))
        return next_record
