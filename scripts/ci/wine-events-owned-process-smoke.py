#!/usr/bin/env python3
"""Actual Wine+Xvfb synthetic fixture receipt for OwnedWineEventProcess.

No network, screenshots, raw event frames, HWNDs, titles or host identifiers
are emitted. All output is a finite fixed PASS/FAIL classification.
"""
import os
import subprocess
import threading
import time

from api.core.wine_events_rdte import SessionObserverRegistry
from api.core.wine_events_process_rdte import OwnedWineEventProcess

SESSION = "rdte-synthetic-session"
FIXTURE = "/opt/winebot/rdte/win_event_fixture.exe"


def receipt(kind, status):
    print(kind + ": " + status, flush=True)


def fixed_env():
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
    result = subprocess.run(
        ["xdotool", "search", "--onlyvisible", "--name", "WineBot RDTE Fixture"],
        stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL, env=fixed_env(),
        timeout=2, check=False,
    )
    return result.returncode == 0


def main():
    registry = SessionObserverRegistry()
    active = [SESSION]
    broker = [SESSION]
    active_read = lambda: active[0]
    broker_read = lambda: broker[0]

    def start_owner():
        owner = OwnedWineEventProcess(
            SESSION, registry, active_read, broker_read,
            prefix=os.environ["WINEPREFIX"], display=os.environ["DISPLAY"]
        )
        outcome = []
        thread = threading.Thread(
            target=lambda: outcome.append(owner.run(deadline_seconds=18.0)),
            daemon=False,
        )
        thread.start()
        return owner, thread, outcome

    owner, thread, result = start_owner()
    fixture = None
    try:
        for _ in range(100):
            if registry.observe(SESSION)["state"] == "ready":
                receipt("PASS", "owned_observer_ready")
                break
            if not thread.is_alive():
                receipt("FAIL", "owner_exited_before_ready")
                return 1
            time.sleep(0.1)
        else:
            receipt("FAIL", "owner_ready_timeout")
            return 1

        fixture = subprocess.Popen(
            ["wine", FIXTURE], stdin=subprocess.DEVNULL,
            stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
            env=fixed_env(), start_new_session=True,
        )
        observed = False
        x11_visible = False
        for _ in range(130):
            state = registry.observe(SESSION)
            if state["state"] == "ready":
                kinds = {event["kind"] for event in state["events"]}
                observed = {"show", "location"}.issubset(kinds)
            if not x11_visible:
                x11_visible = visible_fixture()
            if observed and x11_visible:
                break
            if not thread.is_alive() and not observed:
                break
            time.sleep(0.075)

        if not x11_visible:
            receipt("FAIL", "x11_fixture_invisible")
            return 1
        receipt("PASS", "owned_x11_fixture_visible")

        if not observed:
            receipt("FAIL", "owned_event_not_observed")
            return 1
        receipt("PASS", "owned_live_read_only_events")

        if fixture.wait(timeout=8) != 0:
            receipt("FAIL", "fixture_nonzero_exit")
            return 1
        thread.join(timeout=20)
        if thread.is_alive() or result != ["clean_eof"]:
            receipt("FAIL", "owned_observer_eof")
            return 1
        if registry.observe(SESSION)["state"] != "unavailable":
            receipt("FAIL", "owned_observer_not_cleared")
            return 1
        receipt("PASS", "owned_clean_eof_erasure")

        # A new local observer is allowed only as a new owner. Changing session
        # while it is running must terminate it and scrub the stream.
        replacement, handover_thread, handover_result = start_owner()
        for _ in range(100):
            if registry.observe(SESSION)["state"] == "ready":
                break
            if not handover_thread.is_alive():
                receipt("FAIL", "owned_restart_missing_ready")
                return 1
            time.sleep(0.1)
        else:
            receipt("FAIL", "owned_restart_timeout")
            return 1
        receipt("PASS", "owned_restart_new_process")
        active[0] = "session-next"
        handover_thread.join(timeout=6)
        if handover_thread.is_alive() or handover_result != ["session_handover"]:
            receipt("FAIL", "owned_handover_drain")
            return 1
        if registry.observe(SESSION)["state"] != "unavailable":
            receipt("FAIL", "owned_handover_not_scrubbed")
            return 1
        receipt("PASS", "owned_handover_erasure")
        return 0
    except (OSError, ValueError, subprocess.TimeoutExpired):
        receipt("FAIL", "owned_execution_exception")
        return 1
    finally:
        active[0] = "session-next"
        if fixture is not None and fixture.poll() is None:
            fixture.terminate()
            try:
                fixture.wait(timeout=2)
            except subprocess.TimeoutExpired:
                fixture.kill()
                fixture.wait(timeout=2)
        thread.join(timeout=4)
        registry.clear()


if __name__ == "__main__":
    raise SystemExit(main())
