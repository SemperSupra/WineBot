from collections.abc import Iterator
from contextlib import contextmanager
from contextvars import ContextVar, Token

_current_session_dir: ContextVar[str | None] = ContextVar(
    "winebot_current_session_dir", default=None
)


def _normalize(session_dir: str | None) -> str | None:
    if session_dir is None:
        return None
    value = session_dir.strip()
    return value or None


def get_current_session_dir() -> str | None:
    return _normalize(_current_session_dir.get())


def set_current_session_dir(session_dir: str | None) -> Token[str | None]:
    return _current_session_dir.set(_normalize(session_dir))


def reset_current_session_dir(token: Token[str | None]) -> None:
    _current_session_dir.reset(token)


@contextmanager
def bind_session_dir(session_dir: str | None) -> Iterator[None]:
    token = set_current_session_dir(session_dir)
    try:
        yield
    finally:
        reset_current_session_dir(token)
