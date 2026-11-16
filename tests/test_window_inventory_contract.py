"""Portable /windows inventory contract, independent of running X11/Wine."""

from __future__ import annotations

import asyncio
from unittest.mock import patch

from api.routers import automation


def test_window_inventory_has_exact_count_and_unmodified_entries() -> None:
    with patch.object(automation, "safe_command", return_value={
        "ok": True, "stdout": "0x0001 First Window\n0x0002 Second Window\n"
    }):
        result = asyncio.run(automation.list_windows())
    assert result == {
        "windows": [
            {"id": "0x0001", "title": "First Window"},
            {"id": "0x0002", "title": "Second Window"},
        ],
        "count": 2,
    }


def test_window_inventory_failure_is_empty_without_false_count() -> None:
    with patch.object(automation, "safe_command", return_value={
        "ok": False, "stdout": "", "stderr": "SENSITIVE_HOST_SENTINEL"
    }):
        result = asyncio.run(automation.list_windows())
    assert result == {"windows": [], "count": 0}
    assert "SENSITIVE_HOST_SENTINEL" not in str(result)
