"""Local-only, versioned Wine event cursor qualification (synthetic RDTE).

NOT a WineBot endpoint, authority token, event producer, or portable contract.
A cursor names one session, one collector incarnation, and one source sequence.
Collector generations are fresh per view; a recreated view NEVER accepts an
earlier incarnation's sequence=1 as a continuation. No automatic restart.
"""
import re
import secrets
import threading

from rdte.wine11.event_bridge import EventBridge

CURSOR_SCHEMA = "winebot.wine.cursor.v1"
CURSOR_VERSION = 1
CURSOR_FIELDS = frozenset({"version", "session", "generation", "sequence"})
SESSION_PATTERN = re.compile(r"[A-Za-z0-9_-]{1,64}\Z")
GENERATION_PATTERN = re.compile(r"[0-9a-f]{32}\Z")
SOURCE_REASONS = frozenset({
    "closed", "invalid_event", "oversized_event", "invalid_schema",
    "invalid_json", "missing_ready", "source_gap", "source_overflow",
    "unsupported_event",
})


def _empty(state: str, reason: str | None = None) -> dict:
    result = {
        "schema": CURSOR_SCHEMA,
        "state": state,
        "events": [],
        "next_cursor": None,
    }
    if reason is not None:
        result["reason"] = reason
    return result


class GenerationCursorView:
    """One independent read view; never attaches to a production registry.

    The source owner separately controls authentication and session admission.
    A generation is an opaque discriminator, NOT an authentication credential.
    A close invalidates this local view and its owned synthetic EventBridge.
    """

    def __init__(self, session_identity: str, bridge: EventBridge):
        if (
            type(session_identity) is not str
            or SESSION_PATTERN.fullmatch(session_identity) is None
        ):
            raise ValueError("invalid_session")
        if not isinstance(bridge, EventBridge):
            raise TypeError("invalid_bridge")
        self._session_identity = session_identity
        self._generation = secrets.token_hex(16)
        self._bridge = bridge
        self._closed = False
        self._lock = threading.RLock()

    def _cursor(self, sequence: int) -> dict:
        return {
            "version": CURSOR_VERSION,
            "session": self._session_identity,
            "generation": self._generation,
            "sequence": sequence,
        }

    def initial_cursor(self) -> dict | None:
        """Start from source sequence 0; retained history still gates reads."""
        with self._lock:
            return None if self._closed else self._cursor(0)

    def read(
        self, session_identity: str, cursor: object, limit: int = 64,
    ) -> dict:
        """Independent non-destructive read, with typed fail-closed outcomes.

        Callers MUST separately authorize session_identity; cursor possession
        alone does not grant read access. No cursor-based replay or reset.
        """
        if session_identity != self._session_identity:
            return _empty("unavailable")
        if type(limit) is not int or not 1 <= limit <= 128:
            return _empty("invalid_cursor")
        if (
            type(cursor) is not dict
            or set(cursor) != CURSOR_FIELDS
            or type(cursor.get("version")) is not int
            or cursor["version"] != CURSOR_VERSION
            or type(cursor.get("session")) is not str
            or SESSION_PATTERN.fullmatch(cursor["session"]) is None
            or type(cursor.get("generation")) is not str
            or GENERATION_PATTERN.fullmatch(cursor["generation"]) is None
            or type(cursor.get("sequence")) is not int
            or cursor["sequence"] < 0
        ):
            return _empty("invalid_cursor")
        if cursor["session"] != self._session_identity:
            return _empty("session_mismatch")
        with self._lock:
            if self._closed:
                return _empty("unavailable")
            if cursor["generation"] != self._generation:
                return _empty("stale_generation")
            observation = self._bridge.observe(
                after=cursor["sequence"], limit=limit,
            )
            state = observation.get("state")
            if state == "ready":
                return {
                    "schema": CURSOR_SCHEMA,
                    "state": "ready",
                    "events": observation["events"],
                    "next_cursor": self._cursor(observation["next_cursor"]),
                }
            if state == "unqualified":
                reason = observation.get("reason")
                return _empty(
                    "unqualified",
                    reason if reason in SOURCE_REASONS else "source_error",
                )
            if state in {"not_ready", "invalid_cursor", "history_gap"}:
                return _empty(state)
            return _empty("unqualified", "source_error")

    def close(self) -> None:
        """Stop this private experiment; do not erase a replacement collector."""
        with self._lock:
            if not self._closed:
                self._closed = True
                self._bridge.close()
