#!/usr/bin/env python3
"""Bounded loopback-only WineBot API /input/key and /screenshot qualification.

Must run inside an offline, disposable Xvfb container with a public synthetic
Win32 fixture. Emits allowlisted stage verdicts only, never captured frames,
raw diagnostic text, machine identity, window identifiers or tokens.
"""
import contextlib
import json
import os
import pathlib
import signal
import subprocess
import sys
import time
import urllib.error
import urllib.request

API = "http://127.0.0.1:8765"
TOKEN = "winebot-rdte-public-synthetic"
SESSION = pathlib.Path("/tmp/winebot-cpu-api-session")
WINDOW = "Synthetic GL fixture"


class Unqualified(Exception):
    pass


def verdict(value):
    print(value, flush=True)


def request(method, path, payload=None, authorized=True):
    body = json.dumps(payload).encode() if payload is not None else None
    headers = {"Content-Type": "application/json"}
    if authorized:
        headers["X-API-Key"] = TOKEN
    req = urllib.request.Request(API + path, data=body, headers=headers, method=method)
    try:
        with urllib.request.urlopen(req, timeout=8) as response:
            raw = response.read(5_000_000)
            return response.status, raw
    except urllib.error.HTTPError as exc:
        return exc.code, b""
    except (OSError, TimeoutError) as exc:
        raise Unqualified("api_transport") from exc


def command(argv, timeout=8):
    try:
        return subprocess.run(argv, stdout=subprocess.DEVNULL,
                              stderr=subprocess.DEVNULL, timeout=timeout).returncode == 0
    except (OSError, subprocess.TimeoutExpired):
        return False


def wait_for_marker(path, marker, seconds):
    limit = time.monotonic() + seconds
    while time.monotonic() < limit:
        try:
            if marker in path.read_text(errors="replace"):
                return True
        except OSError:
            pass
        time.sleep(0.15)
    return False


def main():
    SESSION.mkdir(parents=True, exist_ok=True)
    (SESSION / "logs").mkdir(exist_ok=True)
    (SESSION / "scripts").mkdir(exist_ok=True)
    sys.path.insert(0, "/")  # /api is present in the WineBot runtime image.
    from api.utils.files import write_session_dir
    write_session_dir(str(SESSION))
    env = os.environ.copy()
    env.update({
        "API_TOKEN": TOKEN,
        "PYTHONPATH": "/",
        "MODE": "headless",
        "WINEBOT_INSTANCE_CONTROL_MODE": "agent-only",
        "WINEBOT_SESSION_CONTROL_MODE": "agent-only",
        "WINEDEBUG": "-all",
        "LIBGL_ALWAYS_SOFTWARE": "1",
        "GALLIUM_DRIVER": "llvmpipe",
        "LP_NUM_THREADS": "2",
        "WINEPREFIX": "/tmp/winebot-api-fixture-prefix",
    })
    local_dir = pathlib.Path("/tmp")
    win_log = local_dir / "winebot-api-fixture-local.log"
    api_log = local_dir / "winebot-api-server-local.log"
    wine_proc = None
    api_proc = None
    try:
        with win_log.open("w") as output:
            wine_proc = subprocess.Popen(
                ["wine", "/fixture.exe", "1", "1", "320", "0", "1"],
                env=env, stdout=output, stderr=subprocess.DEVNULL,
                start_new_session=True,
            )
        if not wait_for_marker(win_log, "WINE_SYNTHETIC_INPUT_READY", 30):
            raise Unqualified("fixture_not_ready")
        verdict("PASS: Win32 graphics fixture ready")

        with api_log.open("w") as output:
            api_proc = subprocess.Popen(
                [sys.executable, "-m", "uvicorn", "api.server:app",
                 "--host", "127.0.0.1", "--port", "8765", "--no-access-log"],
                env=env, cwd="/", stdout=output, stderr=subprocess.STDOUT,
                start_new_session=True,
            )
        ready = False
        for _ in range(100):
            if api_proc.poll() is not None:
                raise Unqualified("api_start_failed")
            try:
                status, _ = request("GET", "/health")
                if status == 200:
                    ready = True
                    break
            except Unqualified:
                pass
            time.sleep(0.15)
        if not ready:
            raise Unqualified("api_unavailable")
        verdict("PASS: loopback WineBot API readiness")

        code, _ = request("GET", "/health", authorized=False)
        if code != 401:
            raise Unqualified("authentication_not_enforced")
        verdict("PASS: unauthenticated request rejected")

        # Capture through the *actual API endpoint*. Bytes are never printed
        # or uploaded; only their strict PNG header and bounded size are tested.
        code, image = request("GET", "/screenshot")
        if code != 200 or not image.startswith(b"\x89PNG\r\n\x1a\n") or len(image) < 200:
            raise Unqualified("api_screenshot_invalid")
        verdict("PASS: authenticated API screenshot PNG")

        if not command(["xdotool", "search", "--onlyvisible", "--name", WINDOW]):
            raise Unqualified("fixture_window_missing")
        # Window focus is setup. Key submission occurs via WineBot API only.
        found = subprocess.run(
            ["xdotool", "search", "--onlyvisible", "--name", WINDOW],
            capture_output=True, text=True, timeout=5, check=False,
        )
        values = [x for x in found.stdout.splitlines() if x.isdecimal()]
        if not values or not command(["xdotool", "windowfocus", values[0]]):
            raise Unqualified("fixture_focus_failed")
        code, payload = request(
            "POST", "/input/key", {"keys": "Down", "backend": "xdotool"}
        )
        try:
            result = json.loads(payload)
        except (ValueError, TypeError):
            raise Unqualified("api_key_response_invalid") from None
        if code != 200 or result.get("status") != "sent" or result.get("backend") != "xdotool":
            raise Unqualified("api_key_unqualified")
        verdict("PASS: authenticated brokered API key accepted")

        if not wait_for_marker(win_log, "WINE_SYNTHETIC_INPUT_ACK_RGB_OK", 8):
            raise Unqualified("win32_rgb_ack_not_observed")
        try:
            if wine_proc.wait(timeout=8) != 0:
                raise Unqualified("fixture_exit_failed")
        except subprocess.TimeoutExpired as exc:
            raise Unqualified("fixture_did_not_exit") from exc
        verdict("PASS: API key to Win32 event and expected GL RGB readback")
        return 0
    except Unqualified as exc:
        verdict("UNQUALIFIED: " + str(exc))
        return 2
    except Exception:
        # Do not leak raw host/process diagnostics to public Actions logs.
        verdict("UNQUALIFIED: unexpected_harness_exception")
        return 2
    finally:
        for proc in (api_proc, wine_proc):
            if proc is not None and proc.poll() is None:
                try:
                    os.killpg(proc.pid, signal.SIGTERM)
                    proc.wait(timeout=4)
                except (OSError, subprocess.TimeoutExpired):
                    with contextlib.suppress(OSError):
                        os.killpg(proc.pid, signal.SIGKILL)
        command(["wineserver", "-k"], timeout=5)


if __name__ == "__main__":
    sys.exit(main())
