"""Preserve truthful WineBot inspect responses without bypassing broker policy.

These are isolated offline tests; no WinInspect daemon or X11/Wine process starts.
"""

import asyncio
from unittest.mock import AsyncMock, patch

import pytest
from fastapi import HTTPException

from api.core.models import InspectWindowModel
from api.routers import automation


def test_empty_inspect_returns_contract_response_not_fake_success():
    with patch.object(
        automation.broker, "check_access", new_callable=AsyncMock, return_value=True
    ), patch.object(automation, "_wininspect_or_503") as daemon:
        result = asyncio.run(automation.inspect_window(InspectWindowModel()))
        assert result == {
            "status": "invalid_target",
            "detail": "Must provide title or handle",
        }
        daemon.assert_not_called()


def test_broker_denial_still_precedes_invalid_target_response():
    with patch.object(
        automation.broker, "check_access", new_callable=AsyncMock, return_value=False
    ), patch.object(automation, "_wininspect_or_503") as daemon:
        with pytest.raises(HTTPException) as exc:
            asyncio.run(automation.inspect_window(InspectWindowModel()))
        assert exc.value.status_code == 423
        daemon.assert_not_called()


def test_authorized_list_only_inspection_is_real_read_only_enumeration():
    with patch.object(
        automation.broker, "check_access", new_callable=AsyncMock, return_value=True
    ), patch.object(automation, "_wininspect_or_503") as daemon, patch.object(
        automation.wininspect,
        "list_top_windows",
        return_value=[{"hwnd": "101"}],
    ) as listing:
        result = asyncio.run(
            automation.inspect_window(InspectWindowModel(list_only=True))
        )
        assert result == {
            "status": "ok",
            "backend": "wininspect",
            "windows": [{"hwnd": "101"}],
            "count": 1,
        }
        daemon.assert_called_once()
        listing.assert_called_once()


def test_real_handle_info_is_not_synthesized():
    with patch.object(
        automation.broker, "check_access", new_callable=AsyncMock, return_value=True
    ), patch.object(automation, "_wininspect_or_503"), patch.object(
        automation.wininspect,
        "window_info",
        return_value={"title": "fixture"},
    ) as info:
        result = asyncio.run(
            automation.inspect_window(
                InspectWindowModel(handle="101", include_controls=False)
            )
        )
        assert result["status"] == "ok"
        assert result["details"] == {"title": "fixture"}
        info.assert_called_once_with("101")
