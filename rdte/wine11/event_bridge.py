"""Experimental WineBot WinEvent ingest/observation core; no network or mutation.

A *single owner-authorized WineBot session* owns each EventBridge instance.
This module never authenticates consumers or exposes a service endpoint.
It receives only the privacy-minimized, synthetic Wine observer JSONL format.
Consumers must be authorized and session-bound by an independently reviewed
WineBot transport. No screen-reader or UIA capability is implied.
"""

from collections import deque
from dataclasses import dataclass
import json
import threading

KINDS = frozenset({
    "create", "show", "hide", "destroy", "focus", "foreground", "location",
})
SCHEMA = "winebot.wine.event.v1"
FIELDS = frozenset({"schema", "kind", "sequence"})
MAX_LINE_BYTES = 256


@dataclass(frozen=True)
class Event:
    """Only published synthetic semantic data, never HWND/title/coordinates."""
    sequence: int
    kind: str

    def as_dict(self) -> dict:
        return {"sequence": self.sequence, "kind": self.kind}


class EventBridge:
    """Read-only finite event journal for one already-authorized session.

    No input control, event injection, persistence, internal telemetry, raw
    application data, network calls, or session discovery. Caller handles
    session lifecycle, authentication and access control.
    """

    def __init__(self, capacity: int = 128):
        if type(capacity) is not int or not 1 <= capacity <= 1024:
            raise ValueError("invalid_capacity")
        self._lock = threading.Lock()
        self._events: deque[Event] = deque(maxlen=capacity)
        self._ready = False
        self._failed = False
        self._reason = "not_ready"
        self._source_sequence = 0

    def ingest(self, line: str) -> bool:
        """Fail closed on any malformed, extra-field or reordered source input."""
        with self._lock:
            if self._failed:
                return False
            if not isinstance(line, str):
                return self._reject("invalid_event")
            try:
                if len(line.encode("utf-8")) > MAX_LINE_BYTES:
                    return self._reject("oversized_event")
                payload = json.loads(line)
                if (
                    not isinstance(payload, dict)
                    or set(payload) != FIELDS
                    or payload.get("schema") != SCHEMA
                    or type(payload.get("sequence")) is not int
                    or payload["sequence"] < 0
                    or not isinstance(payload.get("kind"), str)
                ):
                    return self._reject("invalid_schema")
            except (ValueError, UnicodeError, TypeError):
                return self._reject("invalid_json")

            sequence = payload["sequence"]
            kind = payload["kind"]
            if not self._ready:
                if sequence != 0 or kind != "ready":
                    return self._reject("missing_ready")
                self._ready = True
                self._reason = "ready"
                return True
            if sequence != self._source_sequence + 1:
                return self._reject("source_gap")
            if kind == "overflow":
                # Terminal callback loss is a failure, never a normal event.
                return self._reject("source_overflow")
            if kind not in KINDS:
                return self._reject("unsupported_event")
            self._source_sequence = sequence
            self._events.append(Event(sequence, kind))
            return True

    def _reject(self, reason: str) -> bool:
        self._failed = True
        self._reason = reason
        self._events.clear()
        return False

    def close(self) -> None:
        """Stop observation and erase any retained event data."""
        with self._lock:
            self._ready = False
            self._failed = True
            self._reason = "closed"
            self._events.clear()

    def observe(self, after: int = 0, limit: int = 64) -> dict:
        """Bounded, stable cursor reads. Dropped history is explicit, never silent.

        Invalid caller cursors fail closed and expose no retained events.
        """
        if (
            type(after) is not int or after < 0
            or type(limit) is not int or not 1 <= limit <= 128
        ):
            return {"state": "invalid_cursor", "events": [], "next_cursor": 0}
        with self._lock:
            if self._failed:
                return {"state": "unqualified", "reason": self._reason,
                        "events": [], "next_cursor": 0}
            if not self._ready:
                return {"state": "not_ready", "events": [], "next_cursor": 0}
            if after > self._source_sequence:
                return {"state": "invalid_cursor", "events": [], "next_cursor": 0}
            oldest = self._events[0].sequence if self._events else self._source_sequence + 1
            if after < oldest - 1:
                return {"state": "history_gap", "events": [],
                        "next_cursor": 0}
            selected = [e.as_dict() for e in self._events
                        if e.sequence > after][:limit]
            return {"state": "ready", "events": selected,
                    "next_cursor": selected[-1]["sequence"] if selected else after}
