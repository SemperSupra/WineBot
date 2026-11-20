"""Deterministic red-team witness of the current input check-to-effect race.

This records existing behavior without injecting a real mouse event. It is a
known-unsafe witness, not a green assertion that production is fenced.
"""
import asyncio
import time
from unittest.mock import patch

from api.core.broker import InputBroker
from api.core.models import ClickModel, ControlMode, ControlPolicyMode, UserIntent
from api.routers import input as input_router


def test_stop_now_between_window_search_and_click_exposes_unfenced_effect():
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
            result = await asyncio.wait_for(task, timeout=3)

        return observed, result

    observed, result = asyncio.run(exercise())
    # RED witness: input effect occurred after STOP_NOW had revoked access.
    # Replace this expected failure scenario with a rejection assertion once
    # the real input dispatcher is epoch-fenced at its effect boundary.
    assert len(observed) == 1
    assert observed[0][1] == UserIntent.STOP_NOW
    assert result["status"] == "clicked"
