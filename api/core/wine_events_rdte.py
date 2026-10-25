"""Experimental one-session, read-only Wine EventBridge registry.

No HTTP ingest, event injection, persistence, source launch, or telemetry.
Ownership remains with the pre-existing WineBot session lifecycle; a trusted
internal producer may attach an already-valid EventBridge. A new session
invalidates the old stream, and the API cannot create an observer.
"""
import threading
from rdte.wine11.event_bridge import EventBridge


class SessionObserverRegistry:
    def __init__(self):
        self._lock = threading.RLock()
        self._session_id = None
        self._bridge = None

    def attach_internal(self, session_id: str, bridge: EventBridge) -> None:
        """Trusted in-process producer only; deliberately not an HTTP method."""
        if not isinstance(session_id, str) or not session_id or "/" in session_id or "\\" in session_id:
            raise ValueError("invalid_session")
        if not isinstance(bridge, EventBridge):
            raise TypeError("invalid_bridge")
        with self._lock:
            if self._bridge is not None:
                self._bridge.close()
            self._session_id = session_id
            self._bridge = bridge

    def session_changed(self, active_session_id: str | None) -> None:
        with self._lock:
            if self._bridge is not None and self._session_id != active_session_id:
                self._bridge.close()
                self._bridge = None
                self._session_id = None

    def observe(self, session_id: str, after: int = 0, limit: int = 64) -> dict:
        with self._lock:
            if session_id != self._session_id or self._bridge is None:
                return {"state": "unavailable", "events": [], "next_cursor": 0}
            return self._bridge.observe(after=after, limit=limit)

    def clear_if_owner(self, session_id: str, bridge: EventBridge) -> bool:
        """Stale producers cannot erase a replacement session's event bridge."""
        with self._lock:
            if self._session_id != session_id or self._bridge is not bridge:
                return False
            self._bridge.close()
            self._bridge = None
            self._session_id = None
            return True

    def clear(self) -> None:
        with self._lock:
            if self._bridge is not None:
                self._bridge.close()
            self._bridge = None
            self._session_id = None


registry = SessionObserverRegistry()
