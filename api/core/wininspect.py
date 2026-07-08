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
        raise WinInspectError(
            f"unexpected WinInspect response id: {response.get('id')!r}; hello={hello!r}"
        )
    if not response.get("ok"):
        error = response.get("error") or {}
        raise WinInspectError(str(error.get("message") or error or "WinInspect request failed"))
    return {
        "result": response.get("result"),
        "metrics": response.get("metrics"),
        "hello": hello,
    }


def capabilities() -> dict[str, Any]:
    return request("daemon.capabilities")["result"]


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
