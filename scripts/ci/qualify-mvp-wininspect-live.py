#!/usr/bin/env python3
"""Read-only Windows HWND observation of an actual running Notepad++ in Wine.

Designed for the isolated IC1 public-hosted runner. Do not publish application
titles, screenshots, registry, user paths or raw WinInspect RPC responses.
"""
import os
import time

from api.core import wininspect


def fail(stage: str) -> None:
    raise RuntimeError("IC1_OBSERVER_CAUSE=" + stage)


def classify_daemon_startup() -> str:
    """Reduce a local daemon log to a fixed, non-identifying public cause."""
    try:
        # Never include log content or paths in a public CI result.
        raw = wininspect._log_path()
        with open(raw, "rb") as handle:
            data = handle.read(131072).decode("utf-8", errors="replace")
    except (OSError, ValueError):
        return "daemon_log_unavailable"
    if "TCP Server: Winsock not initialized" in data:
        return "tcp_winsock_unavailable"
    if "TCP Server: No sockets could be bound" in data:
        return "tcp_no_sockets"
    if "TCP Server: bind failed" in data or "TCP Server: listen failed" in data:
        return "tcp_bind_or_listen_failed"
    if "TCP Server listening on [" in data:
        return "tcp_listener_reported_unreachable"
    if "Starting TCP Server" in data:
        return "tcp_start_requested_no_listener"
    if "WinInspect Daemon " in data:
        return "daemon_initialized_no_tcp"
    if not data:
        return "daemon_no_output"
    return "daemon_log_preinit_only"


def main() -> None:
    if os.environ.get("GITHUB_ACTIONS") != "true" or os.environ.get("GITHUB_EVENT_NAME") != "pull_request" or os.environ.get("WINEBOT_STATE_MODEL") != "layered":
        fail("unqualified_venue")
    if not wininspect.installed():
        fail("binary_missing")
    # First Wine 11 process launch on a fresh disposable prefix can be slower
    # than the adapter's interactive 10-second default. Bound the RDTE window,
    # retain fail-closed TCP readiness and classify process exit vs timeout.
    os.environ["WINEBOT_WININSPECT_START_TIMEOUT_SECONDS"] = "35"
    try:
        state = wininspect.ensure_daemon(start=True)
    except Exception:
        fail("daemon_exception")
    if not state.get("running"):
        if "exit_code" in state:
            fail("daemon_exited")
        if state.get("started"):
            fail(classify_daemon_startup())
        fail("daemon_unavailable")
    try:
        capabilities = wininspect.capabilities()
        if not isinstance(capabilities, dict) or not capabilities:
            fail("capabilities_missing")
    except Exception:
        fail("capabilities_unavailable")

    deadline = time.monotonic() + 25
    while time.monotonic() < deadline:
        try:
            matches = wininspect.find_windows(title_regex=r"Notepad[+][+]")
        except Exception:
            fail("observer_rpc_error")
        for match in matches:
            hwnd = str(match.get("hwnd") or "").strip()
            if not hwnd:
                continue
            try:
                info = wininspect.window_info(hwnd)
            except Exception:
                fail("window_info_rpc_error")
            if isinstance(info, dict) and info:
                print("IC1_OBSERVER=real_notepad_hwnd_readonly_pass")
                return
        time.sleep(1)
    fail("real_window_not_observed")


if __name__ == "__main__":
    try:
        main()
    except Exception as exc:
        if isinstance(exc, RuntimeError) and str(exc).startswith("IC1_OBSERVER_CAUSE="):
            print(str(exc))
        else:
            # Never publish Wine/desktop responses, paths or raw tracebacks.
            print("IC1_OBSERVER_CAUSE=unexpected_harness_exception")
        raise SystemExit(1) from None
