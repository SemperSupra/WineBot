#!/usr/bin/env python3
"""Real WineBot FastAPI lifespan → owned Wine → session GET synthetic smoke.

No listener, network, raw event publication, screenshot, model or host
identity. Only allowlisted PASS/FAIL classifications leave the container.
"""
import asyncio
import contextlib
import os
import subprocess
import tempfile
import time
from unittest.mock import patch

from fastapi.testclient import TestClient


TOKEN = "synthetic-winebot-session-token"
FIXTURE = "/opt/winebot/rdte/win_event_fixture.exe"


async def idle():
    await asyncio.sleep(100)


def emit(status, name):
    print(status + ": " + name, flush=True)


def fixture_env():
    return {
        "PATH": "/usr/local/bin:/usr/bin:/bin",
        "HOME": os.environ.get("HOME", "/home/winebot"),
        "DISPLAY": os.environ["DISPLAY"],
        "WINEPREFIX": os.environ["WINEPREFIX"],
        "WINEARCH": "win64",
        "WINEDEBUG": "-all",
        "WINEDLLOVERRIDES": "mscoree,mshtml=",
        "XDG_RUNTIME_DIR": os.environ["XDG_RUNTIME_DIR"],
    }


def visible_fixture():
    r = subprocess.run(
        ["xdotool", "search", "--onlyvisible", "--name", "WineBot RDTE Fixture"],
        stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL, timeout=2, check=False, env=fixture_env(),
    )
    return r.returncode == 0


def main():
    # Set before import so the actual API startup route gets its opt-in gate.
    os.environ["API_TOKEN"] = TOKEN
    os.environ["WINEBOT_WINE_EVENTS_RDTE_ENABLED"] = "1"
    os.environ["WINEBOT_WINE_EVENTS_PROCESS_RDTE_ENABLED"] = "1"
    from api.server import app
    from api.core.wine_events_rdte import registry
    from api.core.wine_events_service_rdte import service

    with tempfile.TemporaryDirectory(prefix="synthetic-winebot-session-") as session_dir:
        session_id = os.path.basename(session_dir)
        path = "/sessions/" + session_id + "/observations/wine-events"
        headers = {"X-API-Key": TOKEN}
        fixture = None

        try:
            with contextlib.ExitStack() as stack:
                for name, val in (
                    ("api.server.validate_current_environment", []),
                    ("api.server.read_session_dir", session_dir),
                    ("api.utils.files.read_session_dir", session_dir),
                    ("api.routers.wine_events_rdte.read_session_dir", session_dir),
                    ("api.server.read_session_control_mode", "hybrid"),
                ):
                    stack.enter_context(patch(name, return_value=val))
                for name in (
                    "api.server.ensure_user_profile",
                    "api.server.link_wine_user_dir",
                    "api.server.write_instance_state",
                    "api.server.append_lifecycle_event",
                    "api.server.discovery_manager.start",
                    "api.server.discovery_manager.stop",
                    "api.server.reap_finished_tracked_processes",
                ):
                    stack.enter_context(patch(name))
                stack.enter_context(patch("api.server.inactivity_monitor_task", new=idle))

                with TestClient(app) as client:
                    ready = False
                    for _ in range(120):
                        response = client.get(path, headers=headers)
                        if response.status_code != 200:
                            emit("FAIL", "service_session_authorization")
                            return 1
                        if response.json().get("state") == "ready":
                            ready = True
                            break
                        time.sleep(0.1)
                    if not ready:
                        emit("FAIL", "service_observer_ready")
                        return 1
                    emit("PASS", "service_lifespan_observer_ready")

                    if client.get(path, headers={"X-API-Key": "wrong"}).status_code != 401:
                        emit("FAIL", "service_token_enforcement")
                        return 1
                    if client.get(
                        "/sessions/session-other/observations/wine-events", headers=headers,
                    ).status_code != 404:
                        emit("FAIL", "service_cross_session")
                        return 1
                    emit("PASS", "service_token_session_isolation")

                    # Old probe expired at 12s. Remain READY past that bound
                    # before any fixture activity. This is actual Wine/Xvfb,
                    # not just a mocked Python lifespan timer.
                    time.sleep(14)
                    aged = client.get(path, headers=headers)
                    if aged.status_code != 200 or aged.json().get("state") != "ready":
                        verdict = service.last_verdict
                        # Emit only a fixed status identifier, never raw frames,
                        # application context, exception contents or host info.
                        reasons = frozenset({
                            "clean_eof", "nonzero_exit", "timeout", "cancelled",
                            "missing_ready", "source_rejected", "source_overflow",
                            "source_launch_or_read_failure", "owner_exception",
                            "session_handover", "unqualified",
                        })
                        if verdict in reasons:
                            emit("FAIL", "service_early_exit_" + verdict)
                        elif service._thread is not None and service._thread.is_alive():
                            emit("FAIL", "service_worker_alive_without_ready")
                        else:
                            emit("FAIL", "service_early_exit_unknown")
                        emit("FAIL", "service_long_lived_after_12s")
                        return 1
                    emit("PASS", "service_long_lived_after_12s")

                    fixture = subprocess.Popen(
                        ["wine", FIXTURE], stdin=subprocess.DEVNULL,
                        stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                        start_new_session=True, env=fixture_env(),
                    )
                    observed = False
                    x11_visible = False
                    for _ in range(150):
                        state = client.get(path, headers=headers)
                        if state.status_code != 200:
                            emit("FAIL", "service_observation_http")
                            return 1
                        payload = state.json()
                        if payload.get("state") == "ready":
                            kinds = {item["kind"] for item in payload["events"]}
                            observed = {"show", "location"}.issubset(kinds)
                        x11_visible = x11_visible or visible_fixture()
                        if observed and x11_visible:
                            break
                        time.sleep(0.075)

                    if not x11_visible:
                        emit("FAIL", "service_x11_fixture")
                        return 1
                    if not observed:
                        emit("FAIL", "service_event_not_visible")
                        return 1
                    emit("PASS", "service_http_live_wine_events")

                    if fixture.wait(timeout=8) != 0:
                        emit("FAIL", "service_fixture_exit")
                        return 1
                    # End the actual FastAPI lifespan while owner is active.
                    # Owner cancellation and stream scrub are required.
                if not service._stopped:
                    emit("FAIL", "service_shutdown_not_requested")
                    return 1
                if registry.observe(session_id)["state"] != "unavailable":
                    emit("FAIL", "service_shutdown_not_scrubbed")
                    return 1
                emit("PASS", "service_shutdown_erases_stream")
                return 0
        except (OSError, ValueError, subprocess.TimeoutExpired):
            emit("FAIL", "service_runtime_exception")
            return 1
        finally:
            if fixture is not None and fixture.poll() is None:
                fixture.terminate()
                try:
                    fixture.wait(timeout=2)
                except subprocess.TimeoutExpired:
                    fixture.kill()
                    fixture.wait(timeout=2)


if __name__ == "__main__":
    raise SystemExit(main())
