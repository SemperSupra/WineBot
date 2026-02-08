import pytest
import asyncio
import os
from fastapi.testclient import TestClient
from api.server import app, broker, ControlMode, UserIntent, AgentStatus

client = TestClient(app)

@pytest.mark.anyio
async def test_policy_default_mode():
    """Test that default mode is USER in interactive session."""
    # Simulate interactive session start
    await broker.update_session("test-session", interactive=True)
    state = broker.get_state()
    assert state.control_mode == ControlMode.USER
    
    # Verify agent blocked
    response = client.post("/input/mouse/click", json={"x": 0, "y": 0})
    assert response.status_code == 423  # Locked

@pytest.mark.anyio
async def test_policy_grant_control():
    """Test granting control to agent."""
    await broker.update_session("test-session", interactive=True)
    
    # User grants control
    response = client.post("/sessions/test-session/control/grant", json={"lease_seconds": 10})
    assert response.status_code == 200
    data = response.json()
    assert data["control_mode"] == ControlMode.AGENT
    
    # Agent should now be allowed (mocking the check logic since we can't easily mock async internal calls in TestClient without more setup)
    # But we can verify state
    assert broker.get_state().control_mode == ControlMode.AGENT

@pytest.mark.anyio
async def test_policy_user_override():
    """Test that user input revokes agent control."""
    await broker.update_session("test-session", interactive=True)
    await broker.grant_agent(30)
    
    assert broker.get_state().control_mode == ControlMode.AGENT
    
    # Simulate user input
    response = client.post("/input/client/event", json={"event": "mousemove"})
    assert response.status_code == 200
    
    # Agent should be revoked
    state = broker.get_state()
    assert state.control_mode == ControlMode.USER
    assert state.agent_status == AgentStatus.STOPPING

@pytest.mark.anyio
async def test_policy_stop_now():
    """Test STOP_NOW intent."""
    await broker.update_session("test-session", interactive=True)
    await broker.grant_agent(30)
    
    response = client.post("/sessions/test-session/user_intent", json={"intent": "STOP_NOW"})
    assert response.status_code == 200
    
    state = broker.get_state()
    assert state.control_mode == ControlMode.USER
    assert state.user_intent == UserIntent.STOP_NOW
