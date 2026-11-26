"""WinInspect correlation diagnostics must not disclose daemon hello identity."""

import json
import struct
from unittest.mock import patch

import pytest

from api.core import wininspect as wi


class Socket:
    def __init__(self, response, hello=None):
        if hello is None:
            hello = {
                "type": "hello", "version": "0.4.0",
                "hostname": "SYNTHETIC_HOST_NEVER_ECHO",
                "name": "SYNTHETIC_PERSON_NEVER_ECHO",
                "uuid": "SYNTHETIC_UUID_NEVER_ECHO",
            }
        self.sent = bytearray()
        self.incoming = bytearray()
        for item in (hello, response):
            raw = json.dumps(item).encode()
            self.incoming.extend(struct.pack("!I", len(raw)) + raw)

    def recv(self, size):
        value = bytes(self.incoming[:size])
        del self.incoming[:size]
        return value

    def settimeout(self, timeout):
        pass

    def sendall(self, value):
        self.sent.extend(value)

    def __enter__(self):
        return self

    def __exit__(self, *args):
        return False


@pytest.mark.parametrize("bad_reply", [
    {"ok": True, "result": {"capabilities": {}}, "id": ""},
    {"ok": True, "result": {}, "id": "different-request"},
    {"ok": False, "error": {"message": "should not bypass ID check"}},
])
def test_mismatched_correlation_refuses_without_hello_disclosure(bad_reply):
    sock = Socket(bad_reply)
    with (
        patch.object(wi, "ensure_daemon", return_value={"running": True}),
        patch.object(wi.socket, "create_connection", return_value=sock),
    ):
        with pytest.raises(wi.WinInspectError) as error:
            wi.request("daemon.capabilities")
    assert str(error.value) == "WinInspect response correlation failed"
    for token in ("SYNTHETIC_HOST", "SYNTHETIC_PERSON", "SYNTHETIC_UUID",
                  "different-request"):
        assert token not in str(error.value)



@pytest.mark.parametrize("hello", [
    {},
    {"type": "not-hello", "version": "0.4.0"},
    {"type": "hello", "version": "0.3.0"},
    {"type": "hello", "version": "SYNTHETIC_VERSION_NEVER_ECHO"},
    {"type": "hello", "version": ["0.4.0"]},
    {"type": "hello"},
])
def test_wrong_hello_refuses_before_any_rpc(hello):
    sock = Socket({}, hello=hello)
    with (
        patch.object(wi, "ensure_daemon", return_value={"running": True}),
        patch.object(wi.socket, "create_connection", return_value=sock),
    ):
        with pytest.raises(wi.WinInspectError) as error:
            wi.request("daemon.capabilities")
    assert str(error.value) == "WinInspect hello protocol mismatch"
    assert not sock.sent


@pytest.mark.parametrize("version", ["0.3.0", "0.5.0", None, True, ["0.4.0"]])
def test_protocol_override_refuses_before_process_or_socket(version):
    with (
        patch.object(wi, "ensure_daemon") as ensure,
        patch.object(wi.socket, "create_connection") as connect,
    ):
        with pytest.raises(wi.WinInspectError) as error:
            wi.request("daemon.capabilities", {"protocol_version": version})
    assert str(error.value) == "WinInspect request protocol mismatch"
    ensure.assert_not_called()
    connect.assert_not_called()


def test_exact_protocol_and_correlation_are_required():
    sock = Socket({"id": "winebot-abc123456789", "ok": True, "result": {}})
    with (
        patch.object(wi, "ensure_daemon", return_value={"running": True}),
        patch.object(wi.socket, "create_connection", return_value=sock),
        patch.object(wi.uuid, "uuid4") as mock_uuid,
    ):
        mock_uuid.return_value.hex = "abc1234567890"
        result = wi.request("daemon.capabilities", {"protocol_version": "0.4.0"})
    assert result["result"] == {}
    size = struct.unpack("!I", sock.sent[:4])[0]
    assert size == len(sock.sent) - 4
    request = json.loads(sock.sent[4:])
    assert request["params"]["protocol_version"] == "0.4.0"


@pytest.mark.parametrize("status", [None, 0, 1, "true", {}, []])
def test_non_boolean_reply_status_refuses(status):
    sock = Socket({"id": "winebot-abc123456789", "ok": status, "result": {}})
    with (
        patch.object(wi, "ensure_daemon", return_value={"running": True}),
        patch.object(wi.socket, "create_connection", return_value=sock),
        patch.object(wi.uuid, "uuid4") as mock_uuid,
    ):
        mock_uuid.return_value.hex = "abc1234567890"
        with pytest.raises(wi.WinInspectError) as error:
            wi.request("daemon.capabilities")
    assert str(error.value) == "WinInspect response status invalid"
