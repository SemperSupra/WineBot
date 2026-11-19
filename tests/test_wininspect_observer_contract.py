"""Synthetic, transport-independent WineBot consumer tests for observer.read.v0."""

import json
import struct
from types import SimpleNamespace
from unittest.mock import patch

import pytest

from api.core import wininspect as wi


def _result(value):
    return {"result": value, "metrics": None, "hello": {"name": "NEVER_RETURN_IDENTITY"}}


def _event(stream="stream-one", sequence=1):
    return {
        "contract": "observer.portable.v0", "stream": stream,
        "source": "win32.setwineventhook", "sequence": sequence,
        "status": "observed", "kind": "window.shown",
    }


def _poll(events=None, next_sequence=1):
    return {
        "contract": "wininspect.observer.read.v0", "scope": "desktop",
        "status": "observed", "next_sequence": next_sequence,
        "events": events if events is not None else [_event()],
        "reinspect_required": False,
    }


def test_observer_methods_are_passive_only():
    methods = {"observer.capabilities", "observer.open", "observer.poll"}
    assert methods <= wi.READ_ONLY_METHODS
    assert not (methods & wi.MUTATION_METHODS)


def test_open_and_poll_use_versioned_cursor_without_hello_identity(monkeypatch):
    calls = []

    def fake_request(method, params=None):
        calls.append((method, params))
        if method == "observer.open":
            return _result({
                "contract": "wininspect.observer.read.v0",
                "stream": "stream-one", "after_sequence": 0,
                "cursor_mode": "explicit_stream_and_offset",
                "identity": "NEVER_RETURN_IDENTITY",
            })
        if method == "observer.poll":
            return _result(_poll())
        return _result({
            "contract": "wininspect.observer.read.v0", "state": "registered",
            "runtime": "wine", "event_delivery": "unverified",
            "identity": "NEVER_RETURN_IDENTITY",
        })

    monkeypatch.setattr(wi, "request", fake_request)
    assert wi.observer_capabilities()["event_delivery"] == "unverified"
    opened = wi.observer_open()
    assert opened["stream"] == "stream-one"
    assert opened["after_sequence"] == 0
    observed = wi.observer_poll(opened["stream"], opened["after_sequence"], 2)
    assert observed["events"][0]["kind"] == "window.shown"
    assert observed["next_sequence"] == 1
    assert calls[-1] == ("observer.poll", {
        "stream": "stream-one", "after_sequence": 0, "max_events": 2,
    })
    assert "NEVER_RETURN_IDENTITY" not in str((opened, observed, wi.observer_capabilities()))


@pytest.mark.parametrize("stream,after,limit", [
    ("", 0, 1), ("x" * 97, 0, 1), ("one", -1, 1),
    ("one", True, 1), ("one", 1.5, 1), ("one", 2**53, 1),
    ("one", 0, 0), ("one", 0, True), ("one", 0, 129),
])
def test_invalid_cursor_never_dispatches(monkeypatch, stream, after, limit):
    def no_dispatch(*args, **kwargs):
        raise AssertionError("client validation failed to deny malformed cursor")
    monkeypatch.setattr(wi, "request", no_dispatch)
    with pytest.raises(wi.WinInspectError):
        wi.observer_poll(stream, after, limit)


@pytest.mark.parametrize("payload", [
    {"contract": "other", "status": "idle", "next_sequence": 0,
     "events": [], "reinspect_required": False},
    _poll(events=[_event("wrong-stream")]),
    _poll(events=[_event(sequence=2), _event(sequence=1)], next_sequence=2),
    _poll(events=[{**_event(), "hwnd": "0x123"}]),
    _poll(events=[_event()], next_sequence=0),
    {"contract": "wininspect.observer.read.v0", "status": "idle",
     "next_sequence": 1, "events": [_event()], "reinspect_required": False},
])
def test_malformed_event_envelope_fails_closed(monkeypatch, payload):
    monkeypatch.setattr(wi, "request", lambda *a, **kw: _result(payload))
    with pytest.raises(wi.WinInspectError, match="contract mismatch"):
        wi.observer_poll("stream-one", 0, 32)


class Socket:
    def __init__(self, response):
        self.data = bytearray()
        for message in ({"type": "hello", "name": "NEVER_RETURN_IDENTITY"}, response):
            raw = json.dumps(message).encode("utf-8")
            self.data += struct.pack("!I", len(raw)) + raw

    def recv(self, count):
        out = bytes(self.data[:count])
        del self.data[:count]
        return out

    def sendall(self, payload):
        return None

    def settimeout(self, seconds):
        return None

    def __enter__(self):
        return self

    def __exit__(self, *args):
        return False


def test_observer_rpc_error_preserves_code_but_redacts_identity():
    sock = Socket({
        "id": "winebot-123456abcdef", "ok": False,
        "error": {
            "code": "E_OBSERVER_OVERFLOW",
            "message": "NEVER_RETURN_IDENTITY",
        },
    })
    with (
        patch.object(wi, "ensure_daemon", return_value={"running": True}),
        patch.object(wi.socket, "create_connection", return_value=sock),
        patch.object(wi.uuid, "uuid4", return_value=SimpleNamespace(hex="123456abcdef9999")),
    ):
        with pytest.raises(wi.WinInspectRPCError) as err:
            wi.observer_poll("stream-one", 0)
    assert err.value.code == "E_OBSERVER_OVERFLOW"
    assert str(err.value) == "WinInspect observer RPC rejected"
    assert "NEVER_RETURN_IDENTITY" not in str(err.value)
