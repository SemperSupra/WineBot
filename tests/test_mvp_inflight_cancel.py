"""Synthetic bounded STOP_NOW cancellation of asynchronous input dispatch.

The test holds an in-flight asyncio backend, revokes ownership and verifies
the pending input cannot complete. It does not send real keystrokes, inspect
users or claim cancellation of already-delivered X11/AHK effects.
"""
import asyncio
import contextlib
import os
import signal
import sys
from unittest.mock import patch

import pytest
from fastapi import HTTPException

from api.core.broker import InputBroker, broker
from api.core.models import ClickModel, ControlMode, ControlPolicyMode, KeyModel, UserIntent
from api.routers.input import click_at, key_press


def test_broker_revocation_cancels_registered_async_input():
    async def run():
        guard = InputBroker()
        with guard._lock:
            guard.state.interactive = True
            guard.state.control_mode = ControlMode.AGENT
            guard.state.user_intent = UserIntent.WAIT
            guard.state.effective_control_mode = ControlPolicyMode.HYBRID
        entered = asyncio.Event()

        async def held():
            with guard.track_async_input():
                entered.set()
                await asyncio.Event().wait()

        task = asyncio.create_task(held())
        await asyncio.wait_for(entered.wait(), timeout=2)
        await guard.set_user_intent(UserIntent.STOP_NOW)
        with pytest.raises(asyncio.CancelledError):
            await asyncio.wait_for(task, timeout=2)
        assert not guard._active_async_input
        assert guard.get_state().control_mode == ControlMode.USER

    asyncio.run(run())


@pytest.mark.parametrize("path", ["key", "mouse"])
def test_inflight_xdotool_path_interrupted_by_human_stop(path):
    async def run():
        saved = broker.get_state()
        entered = asyncio.Event()

        async def held_backend(*args, **kwargs):
            entered.set()
            await asyncio.Event().wait()
            return {"ok": True, "stdout": "", "stderr": ""}

        try:
            with broker._lock:
                broker.state.interactive = True
                broker.state.control_mode = ControlMode.AGENT
                broker.state.user_intent = UserIntent.WAIT
                broker.state.effective_control_mode = ControlPolicyMode.HYBRID
                broker.state.lease_expiry = None

            with (
                patch("api.routers.input._require_active_session", return_value="/tmp/synthetic"),
                patch("api.routers.input.append_input_event"),
                patch("api.routers.input.emit_operation_timing"),
                patch("api.routers.input._send_keys", side_effect=held_backend),
                patch("api.routers.input.run_async_command", side_effect=held_backend),
            ):
                if path == "key":
                    task = asyncio.create_task(
                        key_press(KeyModel(keys="a", backend="xdotool"))
                    )
                else:
                    task = asyncio.create_task(
                        click_at(ClickModel(x=20, y=20, window_id="123"))
                    )
                await asyncio.wait_for(entered.wait(), timeout=2)
                await broker.set_user_intent(UserIntent.STOP_NOW)
                with pytest.raises(HTTPException) as denied:
                    await asyncio.wait_for(task, timeout=2)
                assert denied.value.status_code == 423
                assert broker.get_state().control_mode == ControlMode.USER
                assert not broker._active_async_input
        finally:
            with broker._lock:
                broker.state = saved

    asyncio.run(run())


def test_cancelled_real_async_child_is_terminated_and_reaped(tmp_path):
    """A revoked asynchronous input waiter must not leave its direct child alive.

    Real local Python subprocess, synthetic fixture, no desktop/input/network.
    This is not a guarantee about process groups or already emitted X11 events.
    """
    from api.utils.process import run_async_command

    pid_file = tmp_path / "synthetic-child.pid"

    async def run():
        command = [
            sys.executable,
            "-c",
            (
                "import os, sys, time; from pathlib import Path; "
                "Path(sys.argv[1]).write_text(str(os.getpid()), encoding='ascii'); "
                "time.sleep(30)"
            ),
            str(pid_file),
        ]
        task = asyncio.create_task(run_async_command(command, timeout=3))
        child_pid = None
        try:
            # Wait for the actual child to acknowledge readiness. Bounded to
            # two seconds; no assumed spawn delay or hard-coded process ID.
            for _ in range(200):
                if pid_file.exists():
                    raw = pid_file.read_text(encoding="ascii")
                    if raw.isdecimal():
                        child_pid = int(raw)
                        break
                await asyncio.sleep(0.01)
            assert child_pid is not None and child_pid > 0
            task.cancel()
            with pytest.raises(asyncio.CancelledError):
                await asyncio.wait_for(task, timeout=2)

            # A successfully reaped direct child must no longer have a PID.
            with pytest.raises(ProcessLookupError):
                os.kill(child_pid, 0)
        finally:
            if not task.done():
                task.cancel()
                with contextlib.suppress(asyncio.CancelledError, TimeoutError):
                    await asyncio.wait_for(task, timeout=2)
            if child_pid is not None:
                # Safety net in case a regression leaves the synthetic child.
                with contextlib.suppress(ProcessLookupError):
                    os.kill(child_pid, signal.SIGKILL)

    asyncio.run(run())
