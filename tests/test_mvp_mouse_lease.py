"""Fail-closed mouse input when the lease is revoked during preparation.

Synthetic invocation only; no pointer movement, Wine or user state accessed.
"""

import asyncio
from unittest.mock import AsyncMock, patch

import pytest
from fastapi import HTTPException

from api.core.broker import broker
from api.core.models import ClickModel
from api.routers.input import click_at


def test_mouse_dispatch_refuses_revoked_lease_before_pointer_motion():
    with (
        patch.object(broker, "check_access", new_callable=AsyncMock) as access,
        patch("api.routers.input._require_active_session", return_value="/tmp/fake-session"),
        patch("api.routers.input.append_input_event"),
        patch("api.routers.input.run_async_command", new_callable=AsyncMock) as command,
    ):
        access.side_effect = [True, False]
        with pytest.raises(HTTPException) as denied:
            asyncio.run(click_at(ClickModel(x=20, y=20, window_id="1234")))

    assert denied.value.status_code == 423
    assert access.await_count == 2
    command.assert_not_called()


def test_mouse_discovery_refuses_revoked_lease_before_lookup_motion():
    with (
        patch.object(broker, "check_access", new_callable=AsyncMock) as access,
        patch("api.routers.input.run_async_command", new_callable=AsyncMock) as command,
    ):
        # Initial admission then discovery preflight, no caller-selected window.
        access.side_effect = [True, False]
        with pytest.raises(HTTPException) as denied:
            asyncio.run(click_at(ClickModel(x=20, y=20)))

    assert denied.value.status_code == 423
    assert access.await_count == 2
    command.assert_not_called()
