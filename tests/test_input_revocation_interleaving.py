"""Deterministic safety regression for broker revocation before input dispatch.

No external xdotool, Wine, or real input processes are executed.
"""
import asyncio
import time
from unittest.mock import patch

from fastapi import HTTPException

from api.core.broker import InputBroker
from api.core.models import ClickModel, ControlMode, ControlPolicyMode, UserIntent
from api.routers import input as input_router


def test_stop_now_between_window_search_and_click_blocks_stale_effect():
    async def exercise():
        admitted = asyncio.Event()
        release_search = asyncio.Event()
        observed = []
        broker = InputBroker()
        broker.state.interactive = True
        broker.state.control_mode = ControlMode.AGENT
        broker.state.effective_control_mode = ControlPolicyMode.HYBRID
        broker.state.user_intent = UserIntent.WAIT
        broker.state.lease_expiry = time.time() + 60

        async def synthetic_command(command, **_kwargs):
            if "search" in command:
                admitted.set()
                await asyncio.wait_for(release_search.wait(), timeout=3)
                return {"ok": True, "stdout": "42", "stderr": ""}
            if "click" in command:
                observed.append((tuple(command), broker.get_state().user_intent))
            return {"ok": True, "stdout": "42", "stderr": ""}

        with (
            patch.object(input_router, "broker", broker),
            patch.object(input_router, "run_async_command", side_effect=synthetic_command),
            patch.object(input_router, "_require_active_session", return_value="/tmp/synthetic"),
            patch.object(input_router, "append_input_event"),
            patch.object(input_router, "append_trace_event"),
            patch.object(input_router, "emit_operation_timing"),
        ):
            task = asyncio.create_task(
                input_router.click_at(
                    ClickModel(x=1, y=1, window_title="Synthetic")
                )
            )
            await asyncio.wait_for(admitted.wait(), timeout=3)
            await broker.set_user_intent(UserIntent.STOP_NOW)
            assert not await broker.check_access()
            release_search.set()
            try:
                await asyncio.wait_for(task, timeout=3)
            except HTTPException as exc:
                status = exc.status_code
            else:
                status = 200

        return observed, status

    observed, status = asyncio.run(exercise())
    assert status == 423
    assert observed == []
