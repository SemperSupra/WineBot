import json
import os
import socket
import struct
import subprocess
import threading
import time
import uuid
from pathlib import Path
from typing import Any

from api.utils.files import read_session_dir
from api.utils.process import find_processes, manage_process

DEFAULT_HOST = "127.0.0.1"
DEFAULT_PORT = 1985
DEFAULT_TIMEOUT_SECONDS = 3.0
MAX_MESSAGE_SIZE = 10 * 1024 * 1024
READ_ONLY_METHODS = {
    "daemon.health",
    "observer.capabilities",
    "observer.open",
    "observer.poll",
    "daemon.capabilities",
    "daemon.status",
    "daemon.metrics",
    "daemon.diag",
    "window.listTop",
    "window.listChildren",
    "window.getInfo",
    "window.getTree",
    "window.getZOrder",
    "window.pickAtPoint",
    "window.findRegex",
    "screen.desktopInfo",
    "screen.getPixel",
    "screen.pixelSearch",
}

# Mutating methods — only callable through brokered endpoints.
MUTATION_METHODS = {
    "window.controlClick",
    "input.mouseClick",
    "input.text",
    "input.hotkey",
    "window.ensureVisible",
    "window.ensureForeground",
}

_daemon_lock = threading.Lock()
_daemon_proc: subprocess.Popen | None = None


class WinInspectError(RuntimeError):
    """Raised when the WinInspect daemon cannot satisfy a request."""


class WinInspectRPCError(WinInspectError):
    """A failed RPC with a normalized, machine-readable error code."""

    def __init__(self, code: str, message: str):
        super().__init__(message)
        self.code = code


def enabled() -> bool:
    return (os.getenv("WINEBOT_WININSPECT_ENABLED", "1").strip().lower()) in {
        "1",
        "true",
        "yes",
        "on",
    }


def host() -> str:
    return os.getenv("WINEBOT_WININSPECT_HOST", DEFAULT_HOST).strip() or DEFAULT_HOST


def port() -> int:
    raw = os.getenv("WINEBOT_WININSPECT_PORT", str(DEFAULT_PORT)).strip()
    try:
        value = int(raw)
    except ValueError:
        return DEFAULT_PORT
    return value if 1 <= value <= 65535 else DEFAULT_PORT


def timeout_seconds() -> float:
    raw = os.getenv("WINEBOT_WININSPECT_TIMEOUT_SECONDS", str(DEFAULT_TIMEOUT_SECONDS)).strip()
    try:
        value = float(raw)
    except ValueError:
        return DEFAULT_TIMEOUT_SECONDS
    return max(0.1, min(value, 30.0))


def tool_dir() -> Path:
    return Path(
        os.getenv("WINEBOT_WININSPECT_DIR", "/opt/winebot/windows-tools/WinSpy").strip()
        or "/opt/winebot/windows-tools/WinSpy"
    )


def daemon_exe() -> Path:
    return tool_dir() / "wininspectd.exe"


def cli_exe() -> Path:
    return tool_dir() / "wininspect.exe"


def gui_exe() -> Path:
    return tool_dir() / "wininspect-gui.exe"


def installed() -> bool:
    return daemon_exe().is_file() and cli_exe().is_file()


def _log_path() -> str:
    session_dir = read_session_dir()
    log_dir = Path(session_dir) / "logs" if session_dir else Path("/tmp")
    log_dir.mkdir(parents=True, exist_ok=True)
    return str(log_dir / "wininspectd.log")


def _tcp_ready(timeout: float = 0.25) -> bool:
    try:
        with socket.create_connection((host(), port()), timeout=timeout):
            return True
    except OSError:
        return False


def _process_running() -> bool:
    global _daemon_proc
    if _daemon_proc is not None and _daemon_proc.poll() is None:
        return True
    return bool(find_processes("wininspectd.exe"))


def ensure_daemon(start: bool = True) -> dict[str, Any]:
    """Ensure the WinInspect daemon is reachable on loopback TCP."""
    global _daemon_proc
    if not enabled():
        return {"enabled": False, "installed": installed(), "running": False}
    if not installed():
        return {
            "enabled": True,
            "installed": False,
            "running": False,
            "error": f"missing {daemon_exe()} or {cli_exe()}",
        }
    if _tcp_ready():
        return {
            "enabled": True,
            "installed": True,
            "running": True,
            "host": host(),
            "port": port(),
            "started": False,
        }
    if not start:
        return {
            "enabled": True,
            "installed": True,
            "running": _process_running(),
            "host": host(),
            "port": port(),
            "started": False,
        }

    with _daemon_lock:
        if _tcp_ready():
            return {
                "enabled": True,
                "installed": True,
                "running": True,
                "host": host(),
                "port": port(),
                "started": False,
            }
        log_file = open(_log_path(), "ab")
        try:
            proc = subprocess.Popen(
                ["wine", str(daemon_exe())],
                stdout=log_file,
                stderr=subprocess.STDOUT,
                start_new_session=True,
            )
            manage_process(proc)
        except Exception as exc:
            log_file.close()
            return {
                "enabled": True,
                "installed": True,
                "running": False,
                "host": host(),
                "port": port(),
                "error": str(exc),
            }

        log_file.close()
        _daemon_proc = proc
        deadline = time.monotonic() + float(
            os.getenv("WINEBOT_WININSPECT_START_TIMEOUT_SECONDS", "10")
        )
        while time.monotonic() < deadline:
            if _tcp_ready():
                return {
                    "enabled": True,
                    "installed": True,
                    "running": True,
                    "host": host(),
                    "port": port(),
                    "pid": proc.pid,
                    "started": True,
                }
            if proc.poll() is not None:
                return {
                    "enabled": True,
                    "installed": True,
                    "running": False,
                    "host": host(),
                    "port": port(),
                    "pid": proc.pid,
                    "exit_code": proc.returncode,
                    "started": True,
                    "error": "wininspectd exited before TCP became ready",
                }
            time.sleep(0.25)

        return {
            "enabled": True,
            "installed": True,
            "running": False,
            "host": host(),
            "port": port(),
            "pid": proc.pid,
            "started": True,
            "error": "timeout waiting for wininspectd TCP readiness",
        }


def _recv_exact(sock: socket.socket, size: int) -> bytes:
    chunks = bytearray()
    while len(chunks) < size:
        chunk = sock.recv(size - len(chunks))
        if not chunk:
            raise WinInspectError("connection closed while reading frame")
        chunks.extend(chunk)
    return bytes(chunks)


def _read_frame(sock: socket.socket) -> dict[str, Any]:
    header = _recv_exact(sock, 4)
    raw_length = struct.unpack("!I", header)[0]
    compressed = bool(raw_length & 0x80000000)
    length = raw_length & 0x7FFFFFFF
    if compressed:
        raise WinInspectError("compressed WinInspect frames are not supported yet")
    if length > MAX_MESSAGE_SIZE:
        raise WinInspectError(f"WinInspect frame too large: {length}")
    payload = _recv_exact(sock, length)
    try:
        return json.loads(payload.decode("utf-8"))
    except json.JSONDecodeError as exc:
        raise WinInspectError(f"invalid WinInspect JSON frame: {exc}") from exc


def _write_frame(sock: socket.socket, payload: dict[str, Any]) -> None:
    data = json.dumps(payload, separators=(",", ":")).encode("utf-8")
    if len(data) > MAX_MESSAGE_SIZE:
        raise WinInspectError(f"WinInspect request too large: {len(data)}")
    sock.sendall(struct.pack("!I", len(data)) + data)


def request(method: str, params: dict[str, Any] | None = None) -> dict[str, Any]:
    if method not in READ_ONLY_METHODS and method not in MUTATION_METHODS:
        raise WinInspectError(f"WinInspect method is not allowed by WineBot: {method}")
    state = ensure_daemon(start=True)
    if not state.get("running"):
        raise WinInspectError(str(state.get("error") or "WinInspect daemon is not running"))

    request_id = f"winebot-{uuid.uuid4().hex[:12]}"
    payload = {
        "id": request_id,
        "method": method,
        "params": {
            "protocol_version": "0.4.0",
            **(params or {}),
        },
    }
    with socket.create_connection((host(), port()), timeout=timeout_seconds()) as sock:
        sock.settimeout(timeout_seconds())
        hello = _read_frame(sock)
        _write_frame(sock, payload)
        response = _read_frame(sock)

    if response.get("id") != request_id:
        # Never expose untrusted daemon hello identity in API-visible errors.
        raise WinInspectError("WinInspect response correlation failed")
    if not response.get("ok"):
        error = response.get("error") or {}
        if isinstance(error, dict):
            code = error.get("code")
            code = code if isinstance(code, str) else ""
            message = str(error.get("message") or error or "WinInspect request failed")
        else:
            code = ""
            message = str(error or "WinInspect request failed")
        if method.startswith("observer."):
            allowed = {
                "E_OBSERVER_OVERFLOW", "E_OBSERVER_GAP",
                "E_OBSERVER_STALE_SOURCE", "E_OBSERVER_INVALID_CURSOR",
                "E_OBSERVER_UNSUPPORTED", "E_BAD_REQUEST", "E_ACCESS_DENIED",
            }
            code = code if code in allowed else "E_OBSERVER_UNKNOWN"
            # Never disclose an untrusted daemon error string or hello identity.
            message = "WinInspect observer RPC rejected"
        raise WinInspectRPCError(code, message)
    return {
        "result": response.get("result"),
        "metrics": response.get("metrics"),
        "hello": hello,
    }


def capabilities() -> dict[str, Any]:
    return request("daemon.capabilities")["result"]


MAX_OBSERVER_SEQUENCE = (1 << 53) - 1
OBSERVER_READ_CONTRACT = "wininspect.observer.read.v0"
OBSERVER_EVENT_CONTRACT = "observer.portable.v0"
OBSERVER_FRAME_KEYS = frozenset(
    {"contract", "stream", "source", "sequence", "status", "kind"}
)


def _observer_sequence(value: Any) -> int:
    if type(value) not in (int, float) or not 0 <= value <= MAX_OBSERVER_SEQUENCE:
        raise WinInspectError("WinInspect observer response contract mismatch")
    if int(value) != value:
        raise WinInspectError("WinInspect observer response contract mismatch")
    return int(value)


def observer_capabilities() -> dict[str, Any]:
    """Discover opt-in source availability; registration is not delivery proof."""
    result = request("observer.capabilities")["result"]
    if not isinstance(result, dict) or result.get("contract") != OBSERVER_READ_CONTRACT:
        raise WinInspectError("WinInspect observer response contract mismatch")
    allowed = (
        "contract", "source", "runtime", "state", "event_delivery",
        "scope", "target_identity", "actuation_authority", "max_batch", "retention",
    )
    return {field: result[field] for field in allowed if field in result}


def observer_open() -> dict[str, Any]:
    """Return an explicit source-incarnation/offset, never a desktop control lease."""
    result = request("observer.open")["result"]
    if not isinstance(result, dict) or result.get("contract") != OBSERVER_READ_CONTRACT:
        raise WinInspectError("WinInspect observer response contract mismatch")
    stream = result.get("stream")
    if not isinstance(stream, str) or not 1 <= len(stream) <= 96:
        raise WinInspectError("WinInspect observer response contract mismatch")
    after = _observer_sequence(result.get("after_sequence"))
    if result.get("cursor_mode") != "explicit_stream_and_offset":
        raise WinInspectError("WinInspect observer response contract mismatch")
    return {
        "contract": OBSERVER_READ_CONTRACT,
        "stream": stream,
        "after_sequence": after,
        "cursor_mode": "explicit_stream_and_offset",
    }


def observer_poll(stream: str, after_sequence: int,
                  max_events: int = 32) -> dict[str, Any]:
    """Read only canonical event kinds; on overflow/stale source, reinspect."""
    if not isinstance(stream, str) or not 1 <= len(stream) <= 96:
        raise WinInspectError("Invalid WinInspect observer cursor")
    if type(after_sequence) is not int or not 0 <= after_sequence <= MAX_OBSERVER_SEQUENCE:
        raise WinInspectError("Invalid WinInspect observer cursor")
    if type(max_events) is not int or not 1 <= max_events <= 128:
        raise WinInspectError("Invalid WinInspect observer batch bound")
    result = request("observer.poll", {
        "stream": stream, "after_sequence": after_sequence, "max_events": max_events,
    })["result"]
    if not isinstance(result, dict) or result.get("contract") != OBSERVER_READ_CONTRACT:
        raise WinInspectError("WinInspect observer response contract mismatch")
    status = result.get("status")
    events = result.get("events")
    if status not in ("observed", "idle") or not isinstance(events, list):
        raise WinInspectError("WinInspect observer response contract mismatch")
    if len(events) > max_events or (status == "idle") != (len(events) == 0):
        raise WinInspectError("WinInspect observer response contract mismatch")
    next_sequence = _observer_sequence(result.get("next_sequence"))
    if next_sequence < after_sequence or result.get("reinspect_required") is not False:
        raise WinInspectError("WinInspect observer response contract mismatch")
    canonical = []
    last = after_sequence
    for item in events:
        if not isinstance(item, dict) or set(item) != OBSERVER_FRAME_KEYS:
            raise WinInspectError("WinInspect observer response contract mismatch")
        seq = _observer_sequence(item.get("sequence"))
        kind = item.get("kind")
        if (item.get("contract") != OBSERVER_EVENT_CONTRACT
                or item.get("stream") != stream
                or item.get("source") != "win32.setwineventhook"
                or item.get("status") != "observed"
                or not isinstance(kind, str) or not 1 <= len(kind) <= 64
                or not last < seq <= next_sequence):
            raise WinInspectError("WinInspect observer response contract mismatch")
        last = seq
        canonical.append({
            "contract": OBSERVER_EVENT_CONTRACT, "stream": stream,
            "source": "win32.setwineventhook", "sequence": seq,
            "status": "observed", "kind": kind,
        })
    if events and last != next_sequence:
        raise WinInspectError("WinInspect observer response contract mismatch")
    return {
        "contract": OBSERVER_READ_CONTRACT,
        "status": status, "next_sequence": next_sequence,
        "events": canonical, "reinspect_required": False,
    }


def health() -> dict[str, Any]:
    return request("daemon.health")["result"]


def status() -> dict[str, Any]:
    return request("daemon.status")["result"]


def screen_info() -> dict[str, Any]:
    return request("screen.desktopInfo")["result"]


def list_top_windows() -> list[dict[str, Any]]:
    result = request("window.listTop")["result"]
    return result if isinstance(result, list) else []


def window_info(hwnd: str) -> dict[str, Any]:
    result = request("window.getInfo", {"hwnd": hwnd})["result"]
    return result if isinstance(result, dict) else {"hwnd": hwnd, "raw": result}


def window_tree(hwnd: str | None = None) -> dict[str, Any]:
    params = {"hwnd": hwnd} if hwnd else {}
    result = request("window.getTree", params)["result"]
    return result if isinstance(result, dict) else {"raw": result}


def find_windows(
    title_regex: str | None = None, class_regex: str | None = None
) -> list[dict[str, Any]]:
    params: dict[str, Any] = {}
    if title_regex:
        params["title_regex"] = title_regex
    if class_regex:
        params["class_regex"] = class_regex
    result = request("window.findRegex", params)["result"]
    return result if isinstance(result, list) else []


def pick_at_point(x: int, y: int) -> dict[str, Any]:
    result = request("window.pickAtPoint", {"x": x, "y": y})["result"]
    return result if isinstance(result, dict) else {"raw": result}


def list_children(hwnd: str) -> list[dict[str, Any]]:
    """List child windows of an HWND through WinInspect."""
    result = request("window.listChildren", {"hwnd": hwnd})["result"]
    return result if isinstance(result, list) else []


# ── Mutation methods (must be called through brokered endpoints) ──────────


def control_click(hwnd: str, x: int | None = None, y: int | None = None,
                  button: str = "left") -> dict[str, Any]:
    """Send a click to a window control at optional coordinates."""
    params: dict[str, Any] = {"hwnd": hwnd, "button": button}
    if x is not None:
        params["x"] = x
    if y is not None:
        params["y"] = y
    return request("window.controlClick", params)["result"]


def mouse_click(x: int, y: int, button: str = "left") -> dict[str, Any]:
    """Click at screen coordinates."""
    return request("input.mouseClick", {"x": x, "y": y, "button": button})["result"]


def send_text(text: str) -> dict[str, Any]:
    """Type text into the foreground window."""
    return request("input.text", {"text": text})["result"]


def send_hotkey(keys: str) -> dict[str, Any]:
    """Send a keyboard hotkey combination."""
    return request("input.hotkey", {"keys": keys})["result"]
