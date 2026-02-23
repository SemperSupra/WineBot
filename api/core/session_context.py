from contextlib import contextmanager
from contextvars import ContextVar, Token
from typing import Iterator, Optional

_current_session_dir: ContextVar[Optional[str]] = ContextVar(
    "winebot_current_session_dir", default=None
)


def _normalize(session_dir: Optional[str]) -> Optional[str]:
    if session_dir is None:
        return None
    value = session_dir.strip()
    return value or None


def get_current_session_dir() -> Optional[str]:
    return _normalize(_current_session_dir.get())


def set_current_session_dir(session_dir: Optional[str]) -> Token[Optional[str]]:
    return _current_session_dir.set(_normalize(session_dir))


def reset_current_session_dir(token: Token[Optional[str]]) -> None:
    _current_session_dir.reset(token)


@contextmanager
def bind_session_dir(session_dir: Optional[str]) -> Iterator[None]:
    token = set_current_session_dir(session_dir)
    try:
        yield
    finally:
        reset_current_session_dir(token)
