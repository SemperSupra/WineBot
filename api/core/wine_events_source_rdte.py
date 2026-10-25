"""Trusted local Wine event producer boundary (RDTE, no process launcher).

A WineBot-owned producer may feed a bounded, schema-controlled stream from an
already qualified local Wine WinEvent observer. This module does NOT accept
connections or launch arbitrary commands. Only the pre-existing active session
and Input Broker identity can own the live, read-only stream. No raw frames are
logged, recorded to disk, or uploaded.
"""
from collections.abc import Callable

from api.core.wine_events_rdte import SessionObserverRegistry
from rdte.wine11.event_bridge import EventBridge


class TrustedLocalEventSource:
    MAX_RECORDS = 129  # ready + 128 synthetic event records
    MAX_BYTES = 24_576

    def __init__(
        self,
        session_id: str,
        registry: SessionObserverRegistry,
        active_session_id: Callable[[], str | None],
        broker_session_id: Callable[[], str | None],
    ):
        if not isinstance(session_id, str) or not session_id or "/" in session_id or "\\" in session_id:
            raise ValueError("invalid_session")
        self._session_id = session_id
        self._registry = registry
        self._active_session_id = active_session_id
        self._broker_session_id = broker_session_id
        self._bridge = EventBridge()
        self._records = 0
        self._bytes = 0
        self._attached = False
        self._stopped = False

    def _session_valid(self) -> bool:
        try:
            return (
                self._active_session_id() == self._session_id
                and self._broker_session_id() == self._session_id
            )
        except Exception:
            return False

    def feed_internal(self, line: str) -> bool:
        """Consume one local, finite JSONL record; never publish raw content."""
        if self._stopped:
            return False
        if not self._session_valid():
            self.stop()
            return False
        if not isinstance(line, str):
            self.stop()
            return False
        try:
            size = len(line.encode("utf-8"))
        except UnicodeError:
            self.stop()
            return False
        if (
            size == 0
            or self._records >= self.MAX_RECORDS
            or self._bytes + size > self.MAX_BYTES
            or not line.endswith("\n")
        ):
            self.stop()
            return False
        self._records += 1
        self._bytes += size
        if not self._bridge.ingest(line):
            self.stop()
            return False
        if not self._attached:
            # First record must have been the valid ready@0 handshake.
            self._registry.attach_internal(self._session_id, self._bridge)
            self._attached = True
        return True

    def stop(self) -> None:
        if self._stopped:
            return
        self._stopped = True
        self._bridge.close()
        if self._attached:
            # This one-session source is the only publisher. Clear buffered
            # state on source termination; no stale events remain visible.
            self._registry.clear_if_owner(self._session_id, self._bridge)

    @property
    def stopped(self) -> bool:
        return self._stopped
