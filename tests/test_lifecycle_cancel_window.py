"""Regression for cancellable, deferred graceful shutdown.

No test sends a real process signal or stops live Wine services.
"""

import asyncio
from contextlib import ExitStack
from unittest.mock import AsyncMock, patch

from api.routers import lifecycle


def _mock_shutdown_side_effects(stack: ExitStack):
    """Guard every external effect, especially PID 1 signalling."""
    stack.enter_context(patch.object(lifecycle, "read_session_dir", return_value=None))
    stack.enter_context(patch.object(lifecycle, "append_lifecycle_event"))
    stack.enter_context(patch.object(lifecycle, "write_instance_state"))
    stack.enter_context(patch.object(lifecycle, "emit_operation_timing"))
    stack.enter_context(
        patch.object(lifecycle, "create_operation", new=AsyncMock(return_value="synthetic-op"))
    )
    stack.enter_context(patch.object(lifecycle, "heartbeat_operation", new=AsyncMock()))
    complete = stack.enter_context(
        patch.object(lifecycle, "complete_operation", new=AsyncMock())
    )
    stack.enter_context(patch.object(lifecycle, "fail_operation", new=AsyncMock()))
    atomic = stack.enter_context(
        patch.object(lifecycle, "atomic_shutdown", new=AsyncMock(return_value={"ok": True}))
    )
    signal = stack.enter_context(patch.object(lifecycle, "schedule_shutdown"))
    return atomic, signal, complete


def _reset_synthetic_transition():
    task = lifecycle._pending_shutdown_task
    if task is not None and not task.done():
        task.cancel()
    lifecycle._pending_shutdown_task = None
    lifecycle._pending_shutdown_operation = None
    lifecycle._shutdown_in_progress = False
    lifecycle._shutdown_mode = ""
    lifecycle._shutdown_started_at = 0.0
    lifecycle._shutdown_due_at = 0.0
    lifecycle._shutdown_generation += 1


def test_cancel_before_expiry_does_not_teardown_or_signal():
    async def scenario():
        _reset_synthetic_transition()
        with ExitStack() as stack:
            atomic, signal, complete = _mock_shutdown_side_effects(stack)
            response = await lifecycle.lifecycle_shutdown(delay=0.04)
            assert response["status"] == "shutting_down"
            atomic.assert_not_awaited()
            signal.assert_not_called()
            cancelled = await lifecycle.lifecycle_cancel()
            assert cancelled == {"status": "cancelled"}
            await asyncio.sleep(0.06)
            atomic.assert_not_awaited()
            signal.assert_not_called()
            assert await lifecycle.lifecycle_cancel() == {"status": "no_pending"}
            assert any(
                call.kwargs.get("result", {}).get("status") == "cancelled"
                for call in complete.await_args_list
            )
        _reset_synthetic_transition()

    asyncio.run(scenario())


def test_grace_period_commits_teardown_only_after_expiry():
    async def scenario():
        _reset_synthetic_transition()
        with ExitStack() as stack:
            atomic, signal, _ = _mock_shutdown_side_effects(stack)
            response = await lifecycle.lifecycle_shutdown(delay=0.04)
            assert response["delay_seconds"] == 0.04
            atomic.assert_not_awaited()
            signal.assert_not_called()
            await asyncio.sleep(0.08)
            atomic.assert_awaited_once()
            signal.assert_called_once_with(None, 0.0, lifecycle.signal.SIGTERM)
            assert await lifecycle.lifecycle_cancel() == {"status": "no_pending"}
        _reset_synthetic_transition()

    asyncio.run(scenario())


def test_duplicate_shutdown_does_not_schedule_second_worker():
    async def scenario():
        _reset_synthetic_transition()
        with ExitStack() as stack:
            atomic, signal, _ = _mock_shutdown_side_effects(stack)
            first = await lifecycle.lifecycle_shutdown(delay=0.08)
            duplicate = await lifecycle.lifecycle_shutdown(delay=0.08)
            assert first["status"] == "shutting_down"
            assert duplicate["status"] == "already_shutting_down"
            assert await lifecycle.lifecycle_cancel() == {"status": "cancelled"}
            await asyncio.sleep(0.09)
            atomic.assert_not_awaited()
            signal.assert_not_called()
        _reset_synthetic_transition()

    asyncio.run(scenario())


def test_default_graceful_shutdown_advertises_real_cancel_window():
    async def scenario():
        _reset_synthetic_transition()
        with ExitStack() as stack:
            atomic, signal, _ = _mock_shutdown_side_effects(stack)
            response = await lifecycle.lifecycle_shutdown()
            assert response["delay_seconds"] >= 10
            assert response["cancel_command"] == "POST /lifecycle/cancel"
            assert response["cancel_before"] >= lifecycle.time.time() + 9
            assert await lifecycle.lifecycle_cancel() == {"status": "cancelled"}
            atomic.assert_not_awaited()
            signal.assert_not_called()
        _reset_synthetic_transition()

    asyncio.run(scenario())
