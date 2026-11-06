"""WinInspect correlation diagnostics must not disclose daemon hello identity."""

import json
import struct
from unittest.mock import patch

import pytest

from api.core import wininspect as wi


class Socket:
    def __init__(self, response):
        hello = {
            "type": "hello", "version": "0.3.0",
            "hostname": "SYNTHETIC_HOST_NEVER_ECHO",
            "name": "SYNTHETIC_PERSON_NEVER_ECHO",
            "uuid": "SYNTHETIC_UUID_NEVER_ECHO",
        }
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
        pass

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
