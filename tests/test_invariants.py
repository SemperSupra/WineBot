import os
from unittest.mock import patch

import pytest
from fastapi.testclient import TestClient

from api.core.models import (
    AgentStatus,
    ControlMode,
    ControlPolicyMode,
    ControlState,
    UserIntent,
)
from api.core.config_guard import validate_runtime_configuration
from api.routers.lifecycle import _validate_session_transition
from api.server import app
from api.utils.files import write_session_state


client = TestClient(app)


@pytest.mark.parametrize(
    "state,target,session_mode,expected_error",
    [
        ("active", "suspend", "persistent", False),
        ("suspended", "resume", "persistent", False),
        ("completed", "suspend", "persistent", True),
        ("completed", "resume", "oneshot", True),
    ],
)
def test_session_transition_invariants(state, target, session_mode, expected_error):
    if expected_error:
        with pytest.raises(Exception):
            _validate_session_transition(state, target, session_mode)
    else:
        _validate_session_transition(state, target, session_mode)


@pytest.mark.parametrize(
    "runtime,instance_control,session_control,allow_headless_hybrid,ok",
    [
        ("interactive", "hybrid", "hybrid", False, True),
        ("headless", "agent-only", "agent-only", False, True),
        ("headless", "human-only", "human-only", False, False),
        ("headless", "hybrid", "hybrid", False, False),
        ("headless", "hybrid", "hybrid", True, True),
    ],
)
def test_runtime_mode_control_invariants(
    runtime, instance_control, session_control, allow_headless_hybrid, ok
):
    errors = validate_runtime_configuration(
        runtime_mode=runtime,
        instance_lifecycle_mode="persistent",
        session_lifecycle_mode="persistent",
        instance_control_mode=instance_control,
        session_control_mode=session_control,
        build_intent="rel",
        allow_headless_hybrid=allow_headless_hybrid,
    )
    assert (len(errors) == 0) is ok


def test_health_invariants_surfaces_control_violation():
    violating_state = ControlState(
        session_id="s1",
        interactive=True,
        control_mode=ControlMode.AGENT,
        lease_expiry=10.0,
        user_intent=UserIntent.WAIT,
        agent_status=AgentStatus.RUNNING,
        instance_control_mode=ControlPolicyMode.HUMAN_ONLY,
        session_control_mode=ControlPolicyMode.HYBRID,
        effective_control_mode=ControlPolicyMode.HUMAN_ONLY,
    )
    with patch.dict(os.environ, {"API_TOKEN": "test-token"}):
        with patch("api.routers.health.broker.get_state", return_value=violating_state):
            response = client.get(
                "/health/invariants",
                headers={"X-API-Key": "test-token"},
            )
    assert response.status_code == 200
    body = response.json()
    assert body["ok"] is False
    codes = {v["code"] for v in body["violations"]}
    assert "control_human_only_violated" in codes


def test_critical_state_write_is_fail_closed(tmp_path):
    session_dir = tmp_path / "s1"
    session_dir.mkdir()
    with patch("api.utils.files.os.replace", side_effect=OSError("disk failure")):
        with pytest.raises(OSError):
            write_session_state(str(session_dir), "active")
