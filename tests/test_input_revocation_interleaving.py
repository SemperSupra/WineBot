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


def test_stop_now_between_key_window_lookup_and_dispatch_blocks_key_effect():
    from api.core.models import KeyModel

    async def exercise():
        entered_lookup = asyncio.Event()
        resume_lookup = asyncio.Event()
        effects = []
        broker = InputBroker()
        broker.state.interactive = True
        broker.state.control_mode = ControlMode.AGENT
        broker.state.effective_control_mode = ControlPolicyMode.HYBRID
        broker.state.user_intent = UserIntent.WAIT
        broker.state.lease_expiry = time.time() + 60

        async def lookup(command, **_kwargs):
            if "search" in command:
                entered_lookup.set()
                await asyncio.wait_for(resume_lookup.wait(), timeout=3)
            return {"ok": True, "stdout": "42", "stderr": ""}

        async def dispatch(**_kwargs):
            effects.append("key-sent")
            return {"ok": True, "backend": "xdotool"}

        with (
            patch.object(input_router, "broker", broker),
            patch.object(input_router, "run_async_command", side_effect=lookup),
            patch.object(input_router, "_send_keys", side_effect=dispatch),
            patch.object(input_router, "_require_active_session", return_value="/tmp/synthetic"),
            patch.object(input_router, "append_input_event"),
            patch.object(input_router, "append_trace_event"),
            patch.object(input_router, "emit_operation_timing"),
        ):
            task = asyncio.create_task(
                input_router.key_press(
                    KeyModel(keys="F1", window_title="Synthetic", backend="xdotool")
                )
            )
            await asyncio.wait_for(entered_lookup.wait(), timeout=3)
            await broker.set_user_intent(UserIntent.STOP_NOW)
            resume_lookup.set()
            try:
                await asyncio.wait_for(task, timeout=3)
            except HTTPException as exc:
                status = exc.status_code
            else:
                status = 200
        return status, effects

    status, effects = asyncio.run(exercise())
    assert status == 423
    assert effects == []


def test_input_ticket_invalidates_on_session_handover_and_lease_expiry():
    async def exercise():
        broker = InputBroker()
        broker.state.interactive = True
        broker.state.control_mode = ControlMode.AGENT
        broker.state.effective_control_mode = ControlPolicyMode.HYBRID
        broker.state.lease_expiry = time.time() + 60
        ticket = await broker.issue_input_ticket()
        assert ticket is not None
        assert await broker.validate_input_ticket(ticket)
        await broker.update_session("new-session", interactive=True)
        assert not await broker.validate_input_ticket(ticket)

        broker.state.interactive = True
        broker.state.control_mode = ControlMode.AGENT
        broker.state.effective_control_mode = ControlPolicyMode.HYBRID
        broker.state.lease_expiry = time.time() + 60
        new_ticket = await broker.issue_input_ticket()
        assert new_ticket is not None
        broker.state.lease_expiry = time.time() - 1
        assert not await broker.validate_input_ticket(new_ticket)

    asyncio.run(exercise())
