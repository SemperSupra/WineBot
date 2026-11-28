import json
import struct
from unittest.mock import AsyncMock, patch

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from api.core import wininspect
from api.routers import automation, health

app = FastAPI()
app.include_router(health.router)
app.include_router(automation.router)
client = TestClient(app)


def _auth():
    return {"X-API-Key": "test-token"}


class FakeSocket:
    def __init__(self, frames: list[dict]):
        self._buffer = bytearray()
        self.sent = bytearray()
        self.timeout = None
        for frame in frames:
            payload = json.dumps(frame).encode("utf-8")
            self._buffer.extend(struct.pack("!I", len(payload)))
            self._buffer.extend(payload)

    def recv(self, size: int) -> bytes:
        chunk = bytes(self._buffer[:size])
        del self._buffer[:size]
        return chunk

    def sendall(self, data: bytes) -> None:
        self.sent.extend(data)

    def settimeout(self, timeout: float) -> None:
        self.timeout = timeout

    def __enter__(self):
        return self

    def __exit__(self, *_exc):
        return False


def test_wininspect_request_uses_length_prefixed_json():
    fake = FakeSocket(
        [
            {"type": "hello", "version": "0.4.0"},
            {
                "id": "winebot-abc123456789",
                "ok": True,
                "result": {"features": {"clipboard": True}},
            },
        ]
    )

    with patch("api.core.wininspect.ensure_daemon", return_value={"running": True}):
        with patch("api.core.wininspect.uuid.uuid4") as mock_uuid:
            mock_uuid.return_value.hex = "abc1234567890"
            with patch("api.core.wininspect.socket.create_connection", return_value=fake):
                result = wininspect.request("daemon.capabilities")

    assert result["result"]["features"]["clipboard"] is True
    sent_length = struct.unpack("!I", fake.sent[:4])[0]
    sent_payload = json.loads(fake.sent[4 : 4 + sent_length].decode("utf-8"))
    assert sent_payload["id"] == "winebot-abc123456789"
    assert sent_payload["method"] == "daemon.capabilities"
    assert sent_payload["params"]["protocol_version"] == "0.4.0"


def test_wininspect_rejects_unlisted_methods_without_daemon_or_socket():
    with (
        patch.object(wininspect, "ensure_daemon") as daemon,
        patch.object(wininspect.socket, "create_connection") as connect,
    ):
        with pytest.raises(wininspect.WinInspectError, match="method is not allowed"):
            wininspect.request("input.unsupported", {"text": "blocked"})
        daemon.assert_not_called()
        connect.assert_not_called()


@pytest.mark.parametrize(("path", "payload", "rpc"), [
    ("/wininspect/key", {"keys": "test"}, "send_text"),
    ("/wininspect/hotkey", {"keys": "ctrl+s"}, "send_hotkey"),
    ("/wininspect/click", {"x": 10, "y": 10}, "mouse_click"),
])
def test_broker_denial_precedes_wininspect_mutation(path, payload, rpc):
    with (
        patch.dict("os.environ", {"API_TOKEN": "test-token"}),
        patch.object(automation.broker, "check_access", new_callable=AsyncMock,
                     return_value=False),
        patch.object(automation.broker, "report_agent_activity", new_callable=AsyncMock) as activity,
        patch.object(wininspect, "ensure_daemon") as daemon,
        patch.object(wininspect, rpc) as mutate,
    ):
        response = client.post(path, json=payload, headers=_auth())
        assert response.status_code == 423
        activity.assert_not_called()
        daemon.assert_not_called()
        mutate.assert_not_called()


def test_health_wininspect_endpoint_reports_capabilities():
    with patch.dict("os.environ", {"API_TOKEN": "test-token"}):
        with (
            patch(
                "api.routers.health.wininspect.ensure_daemon",
                return_value={"enabled": True, "installed": True, "running": True},
            ),
            patch(
                "api.routers.health.wininspect.health",
                return_value={"is_wine": True},
            ),
            patch(
                "api.routers.health.wininspect.capabilities",
                return_value={"features": {"clipboard": True}},
            ),
            patch(
                "api.routers.health.wininspect.status",
                return_value={"connections": 0},
            ),
        ):
            response = client.get("/health/wininspect", headers=_auth())

    assert response.status_code == 200
    payload = response.json()
    assert payload["ok"] is True
    assert payload["capabilities"]["features"]["clipboard"] is True


def test_wininspect_windows_endpoint_returns_enriched_windows():
    with patch.dict("os.environ", {"API_TOKEN": "test-token"}):
        with (
            patch(
                "api.routers.automation.wininspect.ensure_daemon",
                return_value={"running": True},
            ),
            patch(
                "api.routers.automation.wininspect.list_top_windows",
                return_value=[{"hwnd": "0x100"}],
            ),
            patch(
                "api.routers.automation.wininspect.window_info",
                return_value={"hwnd": "0x100", "title": "Untitled - Notepad"},
            ),
        ):
            response = client.get("/wininspect/windows", headers=_auth())

    assert response.status_code == 200
    assert response.json()["windows"] == [{"hwnd": "0x100", "title": "Untitled - Notepad"}]


def test_inspect_window_uses_wininspect_backend():
    with patch.dict("os.environ", {"API_TOKEN": "test-token"}):
        with (
            patch(
                "api.routers.automation.broker.check_access",
                new=AsyncMock(return_value=True),
            ),
            patch(
                "api.routers.automation.wininspect.ensure_daemon",
                return_value={"running": True},
            ),
            patch(
                "api.routers.automation.wininspect.find_windows",
                return_value=[{"hwnd": "0x100", "title": "Untitled - Notepad"}],
            ),
            patch(
                "api.routers.automation.wininspect.window_info",
                return_value={"hwnd": "0x100", "title": "Untitled - Notepad"},
            ),
            patch(
                "api.routers.automation.wininspect.window_tree",
                return_value={"hwnd": "0x100", "children": []},
            ),
        ):
            response = client.post(
                "/inspect/window",
                json={"title": "Untitled - Notepad", "include_controls": True},
                headers=_auth(),
            )

    assert response.status_code == 200
    payload = response.json()
    assert payload["backend"] == "wininspect"
    assert payload["handle"] == "0x100"
    assert payload["controls"] == {"hwnd": "0x100", "children": []}
