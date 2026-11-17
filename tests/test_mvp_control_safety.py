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
from api.core.models import ControlMode, UserIntent


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
