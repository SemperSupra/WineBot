"""HTTP-level fail-closed input ownership and human takeover regressions.

All commands are mocked and every session/token is invented; no X11, Wine,
filesystem mutation, human credential, or user device is accessed.
"""

import asyncio
import os
from contextlib import ExitStack
from unittest.mock import AsyncMock, patch

import pytest
from fastapi.testclient import TestClient

from api.core.broker import broker
from api.core.models import ControlMode, UserIntent
from api.server import app


@pytest.fixture
def ic1_api():
    with ExitStack() as stack:
        stack.enter_context(patch.dict(os.environ, {"API_TOKEN": "synthetic-control-token"}))
        stack.enter_context(
            patch(
                "api.routers.control.read_session_dir",
                return_value="/artifacts/sessions/ic1-test",
            )
        )
        stack.enter_context(
            patch("api.routers.input._require_active_session", return_value="/tmp/ic1-test")
        )
        stack.enter_context(
            patch("api.routers.input.append_input_event")
        )
        stack.enter_context(
            patch("api.routers.input.append_trace_event")
        )
        stack.enter_context(
            patch(
                "api.routers.input.input_trace_windows_log_path",
                return_value="/tmp/ic1-fake-windows-trace",
            )
        )
        stack.enter_context(patch("api.routers.input.emit_operation_timing"))
        stack.enter_context(patch("api.routers.control.emit_operation_timing"))
        send = stack.enter_context(
            patch("api.routers.input._send_keys", new_callable=AsyncMock)
        )
        send.return_value = {"ok": True, "backend": "xdotool"}
        asyncio.run(broker.set_user_intent(UserIntent.WAIT))
        asyncio.run(broker.update_session("ic1-test", interactive=True))
        try:
            yield TestClient(app), {"X-API-Key": "synthetic-control-token"}, send
        finally:
            asyncio.run(broker.update_session("ic1-test", interactive=True))
            asyncio.run(broker.set_user_intent(UserIntent.WAIT))


def _challenge(client, headers):
    response = client.post(
        "/sessions/ic1-test/control/challenge", headers=headers
    )
    assert response.status_code == 200
    return response.json()["token"]


def _grant(client, headers, challenge):
    return client.post(
        "/sessions/ic1-test/control/grant",
        json={
            "lease_seconds": 90,
            "user_ack": True,
            "challenge_token": challenge,
        },
        headers=headers,
    )


def test_actual_api_input_blocked_until_human_grant_then_emitted(ic1_api):
    client, headers, send = ic1_api
    blocked = client.post(
        "/input/key", json={"keys": "a", "backend": "xdotool"}, headers=headers
    )
    assert blocked.status_code == 423
    send.assert_not_called()

    token = _challenge(client, headers)
    assert _grant(client, headers, token).status_code == 200
    result = client.post(
        "/input/key", json={"keys": "a", "backend": "xdotool"}, headers=headers
    )
    assert result.status_code == 200
    assert result.json()["status"] == "sent"
    send.assert_awaited_once()
    assert broker.get_state().control_mode == ControlMode.AGENT


def test_api_emergency_stop_refuses_fresh_grant_and_real_input(ic1_api):
    client, headers, send = ic1_api
    first_token = _challenge(client, headers)
    assert _grant(client, headers, first_token).status_code == 200
    assert _grant(client, headers, first_token).status_code == 403

    competing_token = _challenge(client, headers)
    assert _grant(client, headers, competing_token).status_code == 409

    stopped = client.post(
        "/sessions/ic1-test/user_intent",
        json={"intent": "STOP_NOW"},
        headers=headers,
    )
    assert stopped.status_code == 200
    assert broker.get_state().control_mode == ControlMode.USER

    attempted = _grant(client, headers, _challenge(client, headers))
    assert attempted.status_code == 403
    blocked = client.post(
        "/input/key", json={"keys": "a", "backend": "xdotool"}, headers=headers
    )
    assert blocked.status_code == 423
    send.assert_not_called()
