"""Bounded WineBot-owned synthetic WinEvent observer process (RDTE ONLY).

Starts ONLY a pinned fixture-class Win32 observer under Wine, for an already
authorized live session. No HTTP listener, arbitrary command, screenshots,
injection, disk output, persistent telemetry or raw event logging. The public
interface does not include a spawn route. Test-only process factory injection
is a Python in-process dependency, never caller-provided input.
"""
import os
import selectors
import signal
import subprocess
import time
from collections.abc import Callable

from api.core.wine_events_rdte import SessionObserverRegistry
from api.core.wine_events_source_rdte import TrustedLocalEventSource

# Hard-coded synthetic fixture-specific binary. No argv supplied by requests.
_OBSERVER_ARGV = ("wine", "/opt/winebot/rdte/win_event_observer.exe")
_MAX_LINE_BYTES = 256
_MAX_WAIT_SECONDS = 22.0


class OwnedWineEventProcess:
    """Single run: start, ingest bounded records, stop and erase on every exit."""

    def __init__(
        self,
        session_id: str,
        registry: SessionObserverRegistry,
        active_session_id: Callable[[], str | None],
        broker_session_id: Callable[[], str | None],
        *,
        prefix: str,
        display: str = ":99",
        spawn: Callable = subprocess.Popen,
    ):
        if not isinstance(prefix, str) or not prefix.startswith("/") or not prefix:
            raise ValueError("invalid_prefix")
        if not isinstance(display, str) or not display.startswith(":"):
            raise ValueError("invalid_display")
        self.source = TrustedLocalEventSource(
            session_id, registry, active_session_id, broker_session_id
        )
        self._spawn = spawn
        self._active = active_session_id
        self._broker = broker_session_id
        self._session_id = session_id
        self._prefix = prefix
        self._display = display
        self._started = False
        self._process = None

    def _alive_session(self) -> bool:
        try:
            return (
                self._active() == self._session_id
                and self._broker() == self._session_id
            )
        except Exception:
            return False

    @staticmethod
    def _stop_process(process) -> None:
        if process is None:
            return
        try:
            if process.poll() is None:
                try:
                    os.killpg(process.pid, signal.SIGTERM)
                except (OSError, AttributeError):
                    process.terminate()
                try:
                    process.wait(timeout=1.0)
                except subprocess.TimeoutExpired:
                    try:
                        os.killpg(process.pid, signal.SIGKILL)
                    except (OSError, AttributeError):
                        process.kill()
                    try:
                        process.wait(timeout=1.0)
                    except subprocess.TimeoutExpired:
                        pass
            if process.stdout is not None:
                process.stdout.close()
        except (OSError, ValueError):
            pass

    def run(self, *, deadline_seconds: float = 18.0) -> str:
        """Return a fixed verdict. Never include raw source bytes or process IDs."""
        if self._started:
            return "already_started"
        self._started = True
        if (
            type(deadline_seconds) not in (int, float)
            or not 0.1 <= deadline_seconds <= _MAX_WAIT_SECONDS
        ):
            self.source.stop()
            return "invalid_deadline"
        if not self._alive_session():
            self.source.stop()
            return "session_handover"

        # Only the Wine-specific keys needed for a disposable test survive.
        # Explicitly do not inherit API_TOKEN, private credentials or service
        # secrets into the Wine child process.
        env = {
            "PATH": "/usr/local/bin:/usr/bin:/bin",
            "HOME": os.environ.get("HOME", "/home/winebot"),
            "WINEPREFIX": self._prefix,
            "DISPLAY": self._display,
            "WINEDEBUG": "-all",
            "WINEDLLOVERRIDES": "mscoree,mshtml=",
        }
        if "XDG_RUNTIME_DIR" in os.environ:
            env["XDG_RUNTIME_DIR"] = os.environ["XDG_RUNTIME_DIR"]

        process = None
        selector = None
        deadline = time.monotonic() + float(deadline_seconds)
        buffer = bytearray()
        total = 0
        ready = False
        reason = "unqualified"
        try:
            process = self._spawn(
                list(_OBSERVER_ARGV), stdin=subprocess.DEVNULL,
                stdout=subprocess.PIPE, stderr=subprocess.DEVNULL,
                env=env, close_fds=True, start_new_session=True,
                bufsize=0,
            )
            self._process = process
            if process.stdout is None:
                return "source_missing_stdout"
            selector = selectors.DefaultSelector()
            selector.register(process.stdout, selectors.EVENT_READ)
            while True:
                if not self._alive_session():
                    reason = "session_handover"
                    break
                remaining = deadline - time.monotonic()
                if remaining <= 0:
                    reason = "timeout"
                    break
                if not selector.select(min(0.1, remaining)):
                    # A child may be exited but a pipe still held open by
                    # other wine processes; bounded deadline remains binding.
                    continue
                chunk = os.read(process.stdout.fileno(), 4096)
                if not chunk:
                    if buffer:
                        reason = "truncated_event"
                    elif not ready:
                        reason = "missing_ready"
                    elif process.wait(timeout=min(1, max(0.01, deadline - time.monotonic()))) != 0:
                        reason = "nonzero_exit"
                    else:
                        reason = "clean_eof"
                    break
                total += len(chunk)
                if total > TrustedLocalEventSource.MAX_BYTES:
                    reason = "stream_oversized"
                    break
                buffer.extend(chunk)
                if len(buffer) > _MAX_LINE_BYTES and b"\n" not in buffer:
                    reason = "line_oversized"
                    break
                while b"\n" in buffer:
                    line, _, remainder = buffer.partition(b"\n")
                    buffer = bytearray(remainder)
                    if len(line) + 1 > _MAX_LINE_BYTES:
                        reason = "line_oversized"
                        break
                    try:
                        text = (line + b"\n").decode("utf-8")
                    except UnicodeDecodeError:
                        reason = "invalid_utf8"
                        break
                    if not self.source.feed_internal(text):
                        reason = "source_rejected"
                        break
                    ready = True
                if reason not in ("unqualified",):
                    break
        except (OSError, ValueError, subprocess.SubprocessError):
            reason = "source_launch_or_read_failure"
        finally:
            if selector is not None:
                selector.close()
            self._stop_process(process)
            self.source.stop()
            self._process = None
        return reason
