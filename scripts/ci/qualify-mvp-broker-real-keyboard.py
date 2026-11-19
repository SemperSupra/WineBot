#!/usr/bin/env python3
"""IC1 public-runner-only real Wine keyboard dispatch acceptance.

The TestClient exercises real FastAPI routing and real xdotool→Wine input.
Only session path/evidence bookkeeping is isolated; keyboard dispatch is NEVER
mocked. No user environment, network service, screenshot or raw trace upload.
This is not a test of live-server process isolation or in-flight cancellation.
"""

import asyncio
import os
import subprocess
import time
from contextlib import ExitStack
from pathlib import Path
from unittest.mock import patch

from fastapi.testclient import TestClient

from api.core.broker import broker
from api.core.models import UserIntent
from api.server import app

PROOF = Path("/userdata/ic1-editor.txt")
SESSION = "/artifacts/sessions/ic1-broker-live"
HEADER = {"X-API-Key": "ic1-public-runner-synthetic-token-only"}


def fail(stage: str) -> None:
    raise RuntimeError(f"IC1_BROKER_CAUSE={stage}")


def main() -> None:
    if (
        os.environ.get("GITHUB_ACTIONS") != "true"
        or os.environ.get("GITHUB_EVENT_NAME") != "pull_request"
        or os.environ.get("WINEBOT_STATE_MODEL") != "layered"
    ):
        fail("unqualified_venue")
    if not PROOF.is_file() or "IC1-APP-INPUT-PROOF" not in PROOF.read_text():
        fail("missing_real_editor_baseline")
    found = subprocess.run(
        ["xdotool", "search", "--onlyvisible", "--name", "Notepad++"],
        capture_output=True, text=True, timeout=10, check=False,
    )
    window = next(
        (x for x in found.stdout.splitlines() if x.isdecimal() and len(x) <= 16),
        None,
    )
    if not window:
        fail("real_window_missing")
    active = subprocess.run(
        ["xdotool", "windowactivate", "--sync", window],
        capture_output=True, timeout=15, check=False,
    )
    if active.returncode:
        fail("real_window_focus")

    with ExitStack() as stack:
        stack.enter_context(patch.dict(os.environ, {
            "API_TOKEN": HEADER["X-API-Key"],
            "MODE": "interactive",
        }))
        # Only session metadata and trace persistence are test-isolated.
        # Input execution remains the actual API implementation and xdotool.
        # Middleware and lifespan must see the same synthetic session ID as
        # the control router; otherwise they can silently rebind the broker
        # to an unrelated active recorder session on every API request.
        stack.enter_context(patch("api.server.read_session_dir", return_value=SESSION))
        stack.enter_context(patch("api.routers.control.read_session_dir", return_value=SESSION))
        stack.enter_context(patch("api.routers.input._require_active_session", return_value=SESSION))
        stack.enter_context(patch("api.routers.input.append_input_event"))
        stack.enter_context(patch("api.routers.input.append_trace_event"))
        stack.enter_context(patch("api.routers.input.input_trace_windows_log_path", return_value="/tmp/ic1-fake-trace"))
        stack.enter_context(patch("api.routers.input.emit_operation_timing"))
        stack.enter_context(patch("api.routers.control.emit_operation_timing"))

        asyncio.run(broker.set_user_intent(UserIntent.WAIT))
        asyncio.run(broker.update_session("ic1-broker-live", interactive=True))

        # Use the same in-process route harness as the proven HTTP unit tests.
        # Entering TestClient lifespan would mutate unrelated real service state.
        client = TestClient(app)
        def key(keys: str):
            return client.post(
                "/input/key",
                json={"keys": keys, "window_id": window, "backend": "xdotool"},
                headers=HEADER,
            )

        if key("z").status_code != 423:
            fail("unguarded_input")
        challenge = client.post(
            "/sessions/ic1-broker-live/control/challenge", headers=HEADER
        )
        if challenge.status_code != 200:
            fail("challenge_denied")
        grant = client.post(
            "/sessions/ic1-broker-live/control/grant",
            headers=HEADER,
            json={
                "lease_seconds": 90,
                "user_ack": True,
                "challenge_token": challenge.json()["token"],
            },
        )
        if grant.status_code != 200:
            fail("grant_denied")
        for chord in ("ctrl+End", "z", "ctrl+s"):
            if key(chord).status_code != 200:
                fail("real_key_dispatch")
        deadline = time.monotonic() + 15
        while time.monotonic() < deadline:
            if "IC1-APP-INPUT-PROOFz" in PROOF.read_text():
                break
            time.sleep(0.25)
        else:
            fail("real_wine_save_postcondition")
        stopped = client.post(
            "/sessions/ic1-broker-live/user_intent",
            headers=HEADER, json={"intent": "STOP_NOW"},
        )
        if stopped.status_code != 200 or key("z").status_code != 423:
            fail("emergency_stop_not_enforced")
    print("IC1_BROKER=real_wine_keyboard_and_stop_pass")


if __name__ == "__main__":
    try:
        main()
    except Exception as exc:
        # Do not leak paths, tokens, desktop text or Wine output in CI logs.
        if not isinstance(exc, RuntimeError) or not str(exc).startswith("IC1_BROKER_CAUSE="):
            print("IC1_BROKER_CAUSE=unexpected_harness_exception")
        raise
