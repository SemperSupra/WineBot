"""Opt-in WineBot API lifespan hook for synthetic read-only WinEvent source.

No HTTP start or ingest. Requires both feature flags, a configured token,
one active matching broker session, an existing Wine prefix and the fixed
fixture-class observer binary before an internal worker is allowed.
Only one bounded observer start per session is admitted in this RDTE.
"""
import os
import threading
from collections.abc import Callable

from api.core.wine_events_process_rdte import OwnedWineEventProcess
from api.core.wine_events_rdte import registry
from api.utils.config import config

_OBSERVER_PATH = "/opt/winebot/rdte/win_event_observer.exe"


class ObserverService:
    def __init__(
        self,
        active_session: Callable[[], str | None],
        broker_session: Callable[[], str | None],
        owner_factory: Callable = OwnedWineEventProcess,
    ):
        self._active_session = active_session
        self._broker_session = broker_session
        self._owner_factory = owner_factory
        self._lock = threading.RLock()
        self._last_started_session = None
        self._owner = None
        self._thread = None
        self._stopped = False
        self._last_verdict = None

    def _admitted(self):
        if (
            os.getenv("WINEBOT_WINE_EVENTS_RDTE_ENABLED", "0") != "1"
            or os.getenv("WINEBOT_WINE_EVENTS_PROCESS_RDTE_ENABLED", "0") != "1"
            or not (os.getenv("API_TOKEN") or config.API_TOKEN or "").strip()
            or not os.path.isfile(_OBSERVER_PATH)
        ):
            return None
        prefix = os.getenv("WINEPREFIX", "/wineprefix")
        if not os.path.isdir(prefix):
            return None
        try:
            session_id = self._active_session()
            if session_id and session_id == self._broker_session():
                return session_id
        except Exception:
            return None
        return None

    def start_if_admitted(self) -> bool:
        """Called only by WineBot internal lifecycle / reconciliation."""
        with self._lock:
            if self._stopped:
                return False
            session = self._admitted()
            if not session or session == self._last_started_session:
                return False
            if self._thread is not None and self._thread.is_alive():
                return False
            try:
                owner = self._owner_factory(
                    session, registry, self._active_session,
                    self._broker_session,
                    prefix=os.getenv("WINEPREFIX", "/wineprefix"),
                    display=os.getenv("DISPLAY", ":99"),
                )
            except (TypeError, ValueError, OSError):
                return False
            self._owner = owner
            self._last_verdict = None
            self._last_started_session = session
            self._thread = threading.Thread(
                target=self._run_bounded_owner, args=(owner,),
                name="wine-events-rdte",
                daemon=True,
            )
            self._thread.start()
            return True

    def _run_bounded_owner(self, owner) -> None:
        try:
            verdict = owner.run(deadline_seconds=110.0)
        except Exception:
            # No exception string or raw application data in service logs.
            owner.source.stop()
            verdict = "owner_exception"
        safe_verdicts = frozenset({
            "cancelled", "session_handover", "timeout", "truncated_event",
            "missing_ready", "nonzero_exit", "clean_eof",
            "stream_oversized", "line_oversized", "invalid_utf8",
            "source_rejected", "source_overflow", "source_launch_or_read_failure",
            "source_missing_stdout", "owner_exception", "invalid_deadline",
        })
        with self._lock:
            if self._owner is owner:
                self._last_verdict = verdict if verdict in safe_verdicts else "unqualified"

    @property
    def last_verdict(self) -> str | None:
        """Internal enum only; not an HTTP event source or actor capability."""
        with self._lock:
            return self._last_verdict

    def shutdown(self) -> bool:
        with self._lock:
            self._stopped = True
            owner = self._owner
            thread = self._thread
        if owner is not None:
            owner.request_stop()
        if thread is not None:
            thread.join(timeout=4.0)
        # Erase the per-session stream even if a broken child missed grace.
        # Return false to preserve the cleanup failure for the outer owner.
        complete = thread is None or not thread.is_alive()
        registry.clear()
        return complete


def _active_session_id() -> str | None:
    from api.utils.files import read_session_dir
    path = read_session_dir()
    return os.path.basename(path.rstrip(os.sep)) if path else None


def _broker_session_id() -> str | None:
    from api.core.broker import broker
    return getattr(broker.get_state(), "session_id", None)


service = ObserverService(_active_session_id, _broker_session_id)
