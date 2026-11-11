"""Fail-closed, X11-only window focus qualification with no Wine/X server."""
from __future__ import annotations

import asyncio
from unittest.mock import AsyncMock, patch

import pytest
from fastapi import HTTPException

from api.core.models import FocusModel
from api.routers import automation


def _run(data: FocusModel, listing: dict | None = None, focus: dict | None = None):
    responses = []
    if listing is not None:
        responses.append(listing)
    if focus is not None:
        responses.append(focus)
    with patch.object(automation.broker, "check_access", new_callable=AsyncMock, return_value=True), \
         patch.object(automation, "safe_command", side_effect=responses) as command:
        return asyncio.run(automation.focus_window(data)), command.call_args_list


def test_focus_by_id_uses_existing_x11_helper_subcommand():
    result, calls = _run(FocusModel(window_id="12345"), focus={"ok": True})
    assert result == {"status": "focused"}
    assert calls[0].args[0] == ["/automation/bin/x11.sh", "focus", "12345"]


def test_focus_exact_title_resolves_visible_x11_id_without_regex_interpretation():
    result, calls = _run(
        FocusModel(title="Window (Test)"),
        listing={"ok": True, "stdout": "123 Other Window\n456 Window (Test)\n"},
        focus={"ok": True},
    )
    assert result == {"status": "focused"}
    assert len(calls) == 2
    assert calls[0].args[0] == ["/automation/bin/x11.sh", "list-windows"]
    assert calls[1].args[0] == ["/automation/bin/x11.sh", "focus", "456"]


def test_missing_or_empty_target_is_noop_without_command():
    for data in (FocusModel(), FocusModel(title="")):
        result, calls = _run(data)
        assert result == {"status": "invalid_target"}
        assert calls == []


def test_nonexistent_title_and_failed_lookup_do_not_focus():
    result, calls = _run(
        FocusModel(title="missing"), listing={"ok": True, "stdout": "123 Present\n"}
    )
    assert result == {"status": "not_found"}
    assert len(calls) == 1
    result, calls = _run(FocusModel(title="missing"), listing={"ok": False})
    assert result == {"status": "unavailable"}
    assert len(calls) == 1


def test_non_numeric_window_id_rejected_without_process_invocation():
    result, calls = _run(FocusModel(window_id="123;touch /tmp/nope"))
    assert result == {"status": "invalid_target"}
    assert calls == []


def test_failed_focus_never_reports_success_or_leaks_command_stderr():
    result, calls = _run(
        FocusModel(window_id="123"), focus={"ok": False, "stderr": "HOST_PRIVATE_SENTINEL"}
    )
    assert result == {"status": "failed"}
    assert "HOST_PRIVATE_SENTINEL" not in str(result)
    assert len(calls) == 1


def test_policy_denial_still_blocks_focus():
    with patch.object(automation.broker, "check_access", new_callable=AsyncMock, return_value=False):
        with patch.object(automation, "safe_command") as cmd:
            with pytest.raises(HTTPException) as exc:
                asyncio.run(automation.focus_window(FocusModel(window_id="123")))
            assert exc.value.status_code == 423
            cmd.assert_not_called()
