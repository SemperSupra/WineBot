import pytest
import os
from fastapi.testclient import TestClient
from unittest.mock import patch
from api.server import app
from api.core.broker import broker
from api.core.models import ControlMode, UserIntent, AgentStatus

client = TestClient(app)


@pytest.fixture
def auth_headers():
    token = "test-token"
    os.environ["API_TOKEN"] = token
    return {"X-API-Key": token}


@pytest.mark.anyio
async def test_policy_default_mode(auth_headers):
    """Test that default mode is USER in interactive session."""
    # Simulate interactive session start
    await broker.update_session("test-session", interactive=True)
    state = broker.get_state()
    assert state.control_mode == ControlMode.USER

    # Verify agent blocked
    response = client.post(
        "/input/mouse/click", json={"x": 0, "y": 0}, headers=auth_headers
    )
    assert response.status_code == 423  # Locked


@pytest.mark.anyio
async def test_policy_grant_control(auth_headers):
    """Test granting control to agent."""
    await broker.update_session("test-session", interactive=True)

    # User grants control
    with patch("api.routers.control.read_session_dir", return_value="/artifacts/sessions/test-session"):
        response = client.post(
            "/sessions/test-session/control/challenge",
            headers=auth_headers,
        )
        assert response.status_code == 200
        challenge = response.json()["token"]

        response = client.post(
            "/sessions/test-session/control/grant",
            json={"lease_seconds": 10, "user_ack": True, "challenge_token": challenge},
            headers=auth_headers,
        )
        assert response.status_code == 200
        data = response.json()
        assert data["control_mode"] == ControlMode.AGENT

    # Agent should now be allowed (mocking the check logic since we can't easily mock async internal calls in TestClient without more setup)
    # But we can verify state
    assert broker.get_state().control_mode == ControlMode.AGENT


@pytest.mark.anyio
async def test_policy_user_override(auth_headers):
    """Test that user input revokes agent control."""
    await broker.update_session("test-session", interactive=True)
    challenge = await broker.issue_grant_challenge()
    await broker.grant_agent(30, user_ack=True, challenge_token=challenge["token"])

    assert broker.get_state().control_mode == ControlMode.AGENT

    # Simulate user input
    response = client.post(
        "/input/client/event", json={"event": "mousemove"}, headers=auth_headers
    )
    assert response.status_code == 200

    # Agent should be revoked
    state = broker.get_state()
    assert state.control_mode == ControlMode.USER
    assert state.agent_status == AgentStatus.STOPPING


@pytest.mark.anyio
async def test_policy_stop_now(auth_headers):
    """Test STOP_NOW intent."""
    await broker.update_session("test-session", interactive=True)
    challenge = await broker.issue_grant_challenge()
    await broker.grant_agent(30, user_ack=True, challenge_token=challenge["token"])

    with patch("api.routers.control.read_session_dir", return_value="/artifacts/sessions/test-session"):
        response = client.post(
            "/sessions/test-session/user_intent",
            json={"intent": "STOP_NOW"},
            headers=auth_headers,
        )
    assert response.status_code == 200

    state = broker.get_state()
    assert state.control_mode == ControlMode.USER
    assert state.user_intent == UserIntent.STOP_NOW
