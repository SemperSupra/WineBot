"""Bounded MVP human-override and single-writer broker regressions.

Only invented sessions; no X11/Wine, host automation, human biometric checks,
or physical hardware are involved.
"""

import asyncio
import time
from unittest.mock import patch

import pytest
from fastapi import HTTPException

from api.core.broker import InputBroker
from api.core.models import ControlMode, ControlPolicyMode, UserIntent


def _broker() -> InputBroker:
    with patch("api.core.broker.get_instance_control_mode", return_value="hybrid"):
        b = InputBroker()
        asyncio.run(b.update_session("synthetic-ic1", interactive=True))
    return b


def _grant(b: InputBroker, seconds: int = 60) -> None:
    challenge = asyncio.run(b.issue_grant_challenge())
    asyncio.run(
        b.grant_agent(seconds, user_ack=True, challenge_token=challenge["token"])
    )


def test_human_stop_cannot_be_overridden_by_new_acknowledgement():
    b = _broker()
    _grant(b)
    asyncio.run(b.set_user_intent(UserIntent.STOP_NOW))
    assert b.get_state().control_mode == ControlMode.USER
    assert asyncio.run(b.check_access()) is False

    token = asyncio.run(b.issue_grant_challenge())["token"]
    with pytest.raises(HTTPException) as stopped:
        asyncio.run(b.grant_agent(60, user_ack=True, challenge_token=token))
    assert stopped.value.status_code == 403
    assert b.get_state().user_intent == UserIntent.STOP_NOW
    assert b.get_state().control_mode == ControlMode.USER

    # Only a new explicit human WAIT intent can clear an emergency stop.
    asyncio.run(b.set_user_intent(UserIntent.WAIT))
    _grant(b)
    assert b.get_state().control_mode == ControlMode.AGENT


def test_second_active_agent_grant_is_refused_without_lease_extension():
    b = _broker()
    _grant(b)
    first_expiry = b.get_state().lease_expiry
    assert first_expiry is not None
    second = asyncio.run(b.issue_grant_challenge())["token"]

    with pytest.raises(HTTPException) as already_held:
        asyncio.run(b.grant_agent(600, user_ack=True, challenge_token=second))
    assert already_held.value.status_code == 409
    assert b.get_state().control_mode == ControlMode.AGENT
    assert b.get_state().lease_expiry == first_expiry


def test_expired_lease_cannot_be_renewed_without_new_human_grant():
    b = _broker()
    _grant(b)
    with b._lock:
        b.state.lease_expiry = time.time() - 1

    with pytest.raises(HTTPException) as expired:
        asyncio.run(b.renew_agent(600))
    assert expired.value.status_code == 403
    assert b.get_state().control_mode == ControlMode.USER
    assert asyncio.run(b.check_access()) is False


def test_active_lease_can_be_renewed_and_human_override_revokes():
    b = _broker()
    _grant(b)
    old_expiry = b.get_state().lease_expiry
    asyncio.run(b.renew_agent(300))
    assert b.get_state().lease_expiry > old_expiry
    asyncio.run(b.report_user_activity())
    assert b.get_state().control_mode == ControlMode.USER
    assert asyncio.run(b.check_access()) is False


def test_stale_human_challenge_cannot_grant_after_session_handover():
    b = _broker()
    previous_token = asyncio.run(b.issue_grant_challenge())["token"]
    asyncio.run(b.update_session("ic1-replacement-session", interactive=True))
    with pytest.raises(HTTPException) as stale:
        asyncio.run(b.grant_agent(60, user_ack=True, challenge_token=previous_token))
    assert stale.value.status_code == 403
    assert b.get_state().control_mode == ControlMode.USER
    new_token = asyncio.run(b.issue_grant_challenge())["token"]
    asyncio.run(b.grant_agent(60, user_ack=True, challenge_token=new_token))
    assert b.get_state().control_mode == ControlMode.AGENT


def test_active_agent_lease_is_revoked_across_session_handover():
    b = _broker()
    _grant(b)
    assert b.get_state().lease_expiry is not None
    asyncio.run(b.update_session("ic1-next-session", interactive=True))
    state = b.get_state()
    assert state.session_id == "ic1-next-session"
    assert state.control_mode == ControlMode.USER
    assert state.lease_expiry is None
    assert asyncio.run(b.check_access()) is False


@pytest.mark.parametrize(
    "policy",
    [ControlPolicyMode.HYBRID, ControlPolicyMode.AGENT_ONLY],
)
def test_stop_now_is_absolute_veto_in_headless_policy_modes(policy):
    """A fresh request after emergency stop cannot use implicit access."""
    with patch("api.core.broker.get_instance_control_mode", return_value="hybrid"):
        b = InputBroker()
    with b._lock:
        b.state.interactive = False
        b.state.control_mode = ControlMode.AGENT
        b.state.effective_control_mode = policy
    assert asyncio.run(b.check_access()) is True

    asyncio.run(b.set_user_intent(UserIntent.STOP_NOW))
    assert b.get_state().control_mode == ControlMode.USER
    assert asyncio.run(b.check_access()) is False
    # Even switching policy after STOP_NOW must not resurrect access.
    asyncio.run(b.set_session_control_mode(ControlPolicyMode.AGENT_ONLY))
    assert asyncio.run(b.check_access()) is False
    with pytest.raises(HTTPException) as stopped:
        token = asyncio.run(b.issue_grant_challenge())["token"]
        asyncio.run(b.grant_agent(30, user_ack=True, challenge_token=token))
    assert stopped.value.status_code == 403


def test_stop_now_cancels_tracked_async_input_in_headless_mode():
    """Fail-stop semantics also apply to already-admitted async input waits."""
    async def exercise():
        with patch("api.core.broker.get_instance_control_mode", return_value="hybrid"):
            b = InputBroker()
        with b._lock:
            b.state.interactive = False
            b.state.control_mode = ControlMode.AGENT
            b.state.effective_control_mode = ControlPolicyMode.AGENT_ONLY
        started = asyncio.Event()

        async def held():
            with b.track_async_input():
                started.set()
                await asyncio.Event().wait()

        task = asyncio.create_task(held())
        await asyncio.wait_for(started.wait(), timeout=2)
        await b.set_user_intent(UserIntent.STOP_NOW)
        with pytest.raises(asyncio.CancelledError):
            await asyncio.wait_for(task, timeout=2)
        assert not b._active_async_input
        assert not await b.check_access()

    asyncio.run(exercise())
