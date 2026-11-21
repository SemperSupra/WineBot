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
            {"type": "hello", "version": "0.3.0"},
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
    assert sent_payload["params"]["protocol_version"] == "0.3.0"



@pytest.mark.parametrize(
    "reply",
    [
        {"id": "", "ok": True, "result": {"features": {}}},
        {"ok": True, "result": {"features": {}}},
        {"id": "other-actor-request", "ok": True, "result": {"features": {}}},
        {"id": "", "ok": False, "error": {"code": "E_BAD_METHOD"}},
        {"id": "other-actor-request", "ok": False, "error": {"code": "E_BAD_METHOD"}},
    ],
)
def test_wininspect_fails_closed_on_missing_or_foreign_rpc_correlation(reply):
    """A real daemon's empty handler ID must never be accepted or leaked."""
    fake = FakeSocket([{"type": "hello", "version": "0.3.0"}, reply])
    with (
        patch("api.core.wininspect.ensure_daemon", return_value={"running": True}),
        patch("api.core.wininspect.uuid.uuid4") as mock_uuid,
        patch("api.core.wininspect.socket.create_connection", return_value=fake),
    ):
        mock_uuid.return_value.hex = "abc1234567890"
        with pytest.raises(wininspect.WinInspectError, match="response correlation failed") as err:
            wininspect.request("daemon.capabilities")
    assert "other-actor-request" not in str(err.value)
    assert fake.sent


def test_wininspect_accepts_exact_correlation_on_failed_rpc_before_returning_error():
    fake = FakeSocket(
        [
            {"type": "hello", "version": "0.3.0"},
            {"id": "winebot-abc123456789", "ok": False,
             "error": {"code": "E_BAD_REQUEST", "message": "synthetic-denial"}},
        ]
    )
    with (
        patch("api.core.wininspect.ensure_daemon", return_value={"running": True}),
        patch("api.core.wininspect.uuid.uuid4") as mock_uuid,
        patch("api.core.wininspect.socket.create_connection", return_value=fake),
    ):
        mock_uuid.return_value.hex = "abc1234567890"
        with pytest.raises(wininspect.WinInspectError, match="synthetic-denial"):
            wininspect.request("daemon.capabilities")



@pytest.mark.parametrize(
    "body",
    [b"[]", b"null", b"true", b'"raw"', b"12", b"not-json", bytes([255])],
)
def test_wininspect_rejects_untrusted_nonobject_or_malformed_rpc_frames(body):
    """A malformed daemon frame cannot turn into an uncaught API exception."""
    framed = struct.pack("!I", len(body)) + body

    class OneFrameSocket:
        def __init__(self):
            self.data = bytearray(framed)

        def recv(self, size):
            chunk = bytes(self.data[:size])
            del self.data[:size]
            return chunk
    with pytest.raises(wininspect.WinInspectError, match="invalid WinInspect JSON frame"):
        wininspect._read_frame(OneFrameSocket())


def test_wininspect_rejects_truncated_rpc_frame_without_payload_disclosure():
    class TruncatedSocket:
        def __init__(self):
            self.data = bytearray(struct.pack("!I", 4) + b"{")

        def recv(self, size):
            chunk = bytes(self.data[:size])
            del self.data[:size]
            return chunk
    with pytest.raises(wininspect.WinInspectError, match="connection closed while reading frame"):
        wininspect._read_frame(TruncatedSocket())



@pytest.mark.parametrize(
    "hello",
    [
        {"type": "unexpected", "version": "0.3.0"},
        {"type": "hello", "version": "0.4.0"},
        {"type": "hello"},
        {"version": "0.3.0"},
        {},
    ],
)
def test_wininspect_rejects_invalid_daemon_hello_before_sending_request(hello):
    fake = FakeSocket([hello])
    with (
        patch("api.core.wininspect.ensure_daemon", return_value={"running": True}),
        patch("api.core.wininspect.socket.create_connection", return_value=fake),
    ):
        with pytest.raises(wininspect.WinInspectError, match="hello protocol mismatch"):
            wininspect.request("daemon.capabilities")
    assert fake.sent == b""


def test_wininspect_caller_cannot_override_pinned_rpc_protocol_version():
    fake = FakeSocket(
        [
            {"type": "hello", "version": "0.3.0"},
            {"id": "winebot-abc123456789", "ok": True, "result": {"features": {}}},
        ]
    )
    with (
        patch("api.core.wininspect.ensure_daemon", return_value={"running": True}),
        patch("api.core.wininspect.uuid.uuid4") as mock_uuid,
        patch("api.core.wininspect.socket.create_connection", return_value=fake),
    ):
        mock_uuid.return_value.hex = "abc1234567890"
        result = wininspect.request(
            "daemon.capabilities", {"protocol_version": "0.4.0"}
        )
    assert result["result"] == {"features": {}}
    sent_length = struct.unpack("!I", fake.sent[:4])[0]
    sent_payload = json.loads(fake.sent[4 : 4 + sent_length].decode("utf-8"))
    assert sent_payload["params"]["protocol_version"] == "0.3.0"



@pytest.mark.parametrize(
    "reply",
    [
        {"ok": "false", "result": {}},
        {"ok": 1, "result": {}},
        {"ok": None, "result": {}},
        {"result": {}},
    ],
)
def test_wininspect_refuses_nonboolean_or_missing_rpc_status(reply):
    response = {"id": "winebot-abc123456789", **reply}
    fake = FakeSocket([{"type": "hello", "version": "0.3.0"}, response])
    with (
        patch("api.core.wininspect.ensure_daemon", return_value={"running": True}),
        patch("api.core.wininspect.uuid.uuid4") as mock_uuid,
        patch("api.core.wininspect.socket.create_connection", return_value=fake),
    ):
        mock_uuid.return_value.hex = "abc1234567890"
        with pytest.raises(wininspect.WinInspectError, match="response status invalid"):
            wininspect.request("daemon.capabilities")


@pytest.mark.parametrize(
    "error",
    [None, [], "unexpected raw daemon error", 0, {"message": ["unexpected"]}],
)
def test_wininspect_refuses_malformed_rpc_error_envelope(error):
    reply = {"id": "winebot-abc123456789", "ok": False, "error": error}
    fake = FakeSocket([{"type": "hello", "version": "0.3.0"}, reply])
    with (
        patch("api.core.wininspect.ensure_daemon", return_value={"running": True}),
        patch("api.core.wininspect.uuid.uuid4") as mock_uuid,
        patch("api.core.wininspect.socket.create_connection", return_value=fake),
    ):
        mock_uuid.return_value.hex = "abc1234567890"
        with pytest.raises(wininspect.WinInspectError) as exc:
            wininspect.request("daemon.capabilities")
    assert str(exc.value) in {
        "WinInspect response error invalid",
        "WinInspect request failed",
    }
    assert "unexpected" not in str(exc.value)


def test_wininspect_blocks_mutating_methods():
    with pytest.raises(wininspect.WinInspectError):
        wininspect.request("input.text", {"text": "blocked"})


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
