"""Opt-in WineBot API lifespan hook for synthetic read-only WinEvent source.

No HTTP start or ingest. Requires both feature flags, a configured token,
one active matching broker session, an existing Wine prefix and the fixed
fixture-class observer binary before an internal worker is allowed.
Only one bounded observer start per session is admitted in this RDTE.
"""
import os
import threading
import time
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
        self._lease_session = None
        self._starts_this_session = 0
        self._last_start_at = 0.0
        self._owner = None
        self._thread = None
        self._stopped = False

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
            if not session:
                return False
            if self._thread is not None and self._thread.is_alive():
                return False
            if session != self._lease_session:
                self._lease_session = session
                self._starts_this_session = 0
                self._last_start_at = 0.0
            # At most two bounded leases per session; no unbounded crash loop.
            if self._starts_this_session >= 2 or (
                self._starts_this_session and time.monotonic() - self._last_start_at < 1.0
            ):
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
            self._starts_this_session += 1
            self._last_start_at = time.monotonic()
            self._thread = threading.Thread(
                target=self._run_bounded_owner, args=(owner,),
                name="wine-events-rdte",
                daemon=True,
            )
            self._thread.start()
            return True

    @staticmethod
    def _run_bounded_owner(owner) -> None:
        try:
            owner.run(deadline_seconds=110.0)
        except Exception:
            # No exception string or raw application data in service logs.
            owner.source.stop()

    def shutdown(self) -> bool:
        with self._lock:
            self._stopped = True
            owner = self._owner
            thread = self._thread
        if owner is not None:
            owner.request_stop()
        if thread is not None:
            thread.join(timeout=3.0)
            if thread.is_alive():
                return False
        registry.clear()
        return True


def _active_session_id() -> str | None:
    from api.utils.files import read_session_dir
    path = read_session_dir()
    return os.path.basename(path.rstrip(os.sep)) if path else None


def _broker_session_id() -> str | None:
    from api.core.broker import broker
    return getattr(broker.get_state(), "session_id", None)


service = ObserverService(_active_session_id, _broker_session_id)
