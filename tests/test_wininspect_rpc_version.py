"""Pinned WinInspect v0.4.4 RPC protocol compatibility, synthetic-only."""

import json
import struct
from unittest.mock import patch

import pytest

from api.core import wininspect


class FakeSocket:
    def __init__(self, responses):
        self.recv_bytes = bytearray()
        self.sent = bytearray()
        for response in responses:
            raw = json.dumps(response).encode("utf-8")
            self.recv_bytes.extend(struct.pack("!I", len(raw)) + raw)

    def recv(self, length):
        chunk = self.recv_bytes[:length]
        del self.recv_bytes[:length]
        return bytes(chunk)

    def sendall(self, data):
        self.sent.extend(data)

    def settimeout(self, _timeout):
        pass

    def __enter__(self):
        return self

    def __exit__(self, *_args):
        return False


def _invoke(response, params=None):
    sock = FakeSocket([{"type": "hello", "version": "0.3.0"}, response])
    with (
        patch.object(wininspect, "ensure_daemon", return_value={"running": True}),
        patch.object(wininspect.uuid, "uuid4") as uid,
        patch.object(wininspect.socket, "create_connection", return_value=sock),
    ):
        uid.return_value.hex = "abc123456789abcdef"
        if response["ok"]:
            outcome = wininspect.request("daemon.capabilities", params)
        else:
            with pytest.raises(wininspect.WinInspectError, match="expected 0.3.0"):
                wininspect.request("daemon.capabilities", params)
            outcome = None
    length = struct.unpack("!I", sock.sent[:4])[0]
    return outcome, json.loads(sock.sent[4:4 + length])


def test_release_v044_uses_rpc_v030_in_params():
    result, wire = _invoke({
        "id": "winebot-abc123456789", "ok": True,
        "result": {"features": {"ui": True}},
    })
    assert wininspect.WININSPECT_PROTOCOL_VERSION == "0.3.0"
    assert wire["params"]["protocol_version"] == "0.3.0"
    assert "protocol_version" not in {k: v for k, v in wire.items() if k != "params"}
    assert result["result"]["features"]["ui"] is True


def test_rpc_version_cannot_be_overridden_by_caller_params():
    _, wire = _invoke({
        "id": "winebot-abc123456789", "ok": True,
        "result": {},
    }, {"protocol_version": "0.4.0", "title_regex": "synthetic"})
    assert wire["params"]["protocol_version"] == "0.3.0"
    assert wire["params"]["title_regex"] == "synthetic"


def test_server_version_error_fails_closed():
    _, wire = _invoke({
        "id": "winebot-abc123456789", "ok": False,
        "error": {"code": "E_PROTOCOL_VERSION", "message": "expected 0.3.0, got 0.4.0"},
    })
    assert wire["params"]["protocol_version"] == "0.3.0"
