"""API conformance tests for POST /input/key keyboard injection endpoint.

Validates contract, validation, error paths, trace events, and telemetry
without requiring a running Wine instance.  Fits in the fast CI gate.
"""

import os
from unittest.mock import patch

import pytest
from fastapi.testclient import TestClient

from api.server import app

client = TestClient(app)


@pytest.fixture
def auth_headers():
    return {"X-API-Key": "test-token"}


@pytest.fixture
def valid_payload():
    return {"keys": "Hello", "window_title": "Notepad"}


def _setup_session_dir(tmp_path):
    """Create a real session dir with scripts/ subdirectory."""
    session_dir = str(tmp_path / "session")
    scripts_dir = os.path.join(session_dir, "scripts")
    logs_dir = os.path.join(session_dir, "logs")
    os.makedirs(scripts_dir, exist_ok=True)
    os.makedirs(logs_dir, exist_ok=True)
    return session_dir


# ---------------------------------------------------------------------------
# Contract: success path
# ---------------------------------------------------------------------------

def test_key_press_returns_sent(auth_headers, valid_payload, tmp_path):
    session_dir = _setup_session_dir(tmp_path)

    with patch("api.routers.input.broker.check_access", return_value=True):
        with patch("api.routers.input.broker.report_agent_activity"):
            with patch("api.routers.input._require_active_session", return_value=session_dir):
                with patch("api.routers.input.append_input_event"):
                    with patch("api.routers.input.append_trace_event"):
                        with patch("api.routers.input.emit_operation_timing"):
                            with patch("api.routers.input.safe_command") as mock_safe:
                                with patch("api.routers.input.run_async_command") as mock_run_async:
                                    mock_safe.return_value = {"ok": True, "stdout": "", "stderr": ""}
                                    mock_run_async.return_value = {"ok": True, "stdout": "12345\n", "stderr": ""}

                                    with patch.dict(os.environ, {"API_TOKEN": "test-token"}):
                                        response = client.post("/input/key", json=valid_payload, headers=auth_headers)

    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "sent"
    assert body["keys"] == "Hello"
    assert body["backend"] == "ahk"
    assert "trace_id" in body


# ---------------------------------------------------------------------------
# Contract: error paths
# ---------------------------------------------------------------------------

def test_key_press_denied_by_policy(auth_headers, valid_payload):
    with patch("api.routers.input.broker.check_access", return_value=False):
        with patch.dict(os.environ, {"API_TOKEN": "test-token"}):
            response = client.post("/input/key", json=valid_payload, headers=auth_headers)

    assert response.status_code == 423
    assert "denied by policy" in response.json()["detail"]


def test_key_press_invalid_backend(auth_headers, tmp_path):
    session_dir = _setup_session_dir(tmp_path)
    with patch("api.routers.input.broker.check_access", return_value=True):
        with patch("api.routers.input.broker.report_agent_activity"):
            with patch("api.routers.input._require_active_session", return_value=session_dir):
                with patch("api.routers.input.run_async_command") as mock_run:
                    mock_run.return_value = {"ok": True, "stdout": "", "stderr": ""}
                    with patch.dict(os.environ, {"API_TOKEN": "test-token"}):
                        response = client.post(
                            "/input/key",
                            json={"keys": "test", "backend": "invalid"},
                            headers=auth_headers,
                        )
    assert response.status_code == 400
    assert "Invalid backend" in response.json()["detail"]


def test_key_press_missing_keys_field(auth_headers):
    with patch.dict(os.environ, {"API_TOKEN": "test-token"}):
        response = client.post(
            "/input/key", json={"window_title": "Notepad"}, headers=auth_headers
        )
    assert response.status_code == 422


# ---------------------------------------------------------------------------
# Trace event verification
# ---------------------------------------------------------------------------

def test_key_press_writes_request_and_complete_trace_events(
    auth_headers, valid_payload, tmp_path
):
    session_dir = _setup_session_dir(tmp_path)

    captured = []

    def capture_append(session_dir, event):
        captured.append(dict(event))
        return None

    with patch("api.routers.input.broker.check_access", return_value=True):
        with patch("api.routers.input.broker.report_agent_activity"):
            with patch("api.routers.input._require_active_session", return_value=session_dir):
                with patch("api.routers.input.append_input_event", side_effect=capture_append):
                    with patch("api.routers.input.append_trace_event"):
                        with patch("api.routers.input.emit_operation_timing"):
                            with patch("api.routers.input.safe_command") as mock_safe:
                                with patch("api.routers.input.run_async_command") as mock_run:
                                    mock_safe.return_value = {"ok": True, "stdout": "", "stderr": ""}
                                    mock_run.return_value = {"ok": True, "stdout": "12345\n", "stderr": ""}

                                    with patch.dict(os.environ, {"API_TOKEN": "test-token"}):
                                        response = client.post("/input/key", json=valid_payload, headers=auth_headers)

    assert response.status_code == 200
    request_events = [e for e in captured if e.get("phase") == "request"]
    complete_events = [e for e in captured if e.get("phase") == "complete"]

    assert len(request_events) == 1, f"Expected 1 request event, got {len(request_events)}"
    req = request_events[0]
    assert req["event"] == "agent_key"
    assert req["keys"] == "Hello"
    assert req["tool"] == "api:/input/key"
    assert req["origin"] == "agent"
    assert req["via"] == "ahk"

    assert len(complete_events) == 1, f"Expected 1 complete event, got {len(complete_events)}"
    comp = complete_events[0]
    assert comp["status"] == "sent"
    assert comp["event"] == "agent_key"


def test_key_press_writes_windows_cross_layer_event(
    auth_headers, valid_payload, tmp_path
):
    session_dir = _setup_session_dir(tmp_path)

    cross_layer_events = []

    def capture_cross(session_dir, event):
        cross_layer_events.append(dict(event))

    with patch("api.routers.input.broker.check_access", return_value=True):
        with patch("api.routers.input.broker.report_agent_activity"):
            with patch("api.routers.input._require_active_session", return_value=session_dir):
                with patch("api.routers.input.append_input_event"):
                    with patch("api.routers.input.append_trace_event", side_effect=capture_cross):
                        with patch("api.routers.input.emit_operation_timing"):
                            with patch("api.routers.input.safe_command") as mock_safe:
                                with patch("api.routers.input.run_async_command") as mock_run:
                                    mock_safe.return_value = {"ok": True, "stdout": "", "stderr": ""}
                                    mock_run.return_value = {"ok": True, "stdout": "12345\n", "stderr": ""}

                                    with patch.dict(os.environ, {"API_TOKEN": "test-token"}):
                                        client.post("/input/key", json=valid_payload, headers=auth_headers)

    key_sent_events = [e for e in cross_layer_events if e.get("event") == "key_sent"]
    assert len(key_sent_events) == 1, f"Expected 1 cross-layer key_sent, got {len(key_sent_events)}"
    assert key_sent_events[0]["source"] == "windows"
    assert key_sent_events[0]["origin"] == "agent"
    assert key_sent_events[0]["backend"] == "ahk"


# ---------------------------------------------------------------------------
# Telemetry verification
# ---------------------------------------------------------------------------

def test_key_press_emits_success_telemetry(
    auth_headers, valid_payload, tmp_path
):
    session_dir = _setup_session_dir(tmp_path)

    telemetry_calls = []

    def capture_telemetry(session_dir, **kwargs):
        telemetry_calls.append(dict(kwargs))

    with patch("api.routers.input.broker.check_access", return_value=True):
        with patch("api.routers.input.broker.report_agent_activity"):
            with patch("api.routers.input._require_active_session", return_value=session_dir):
                with patch("api.routers.input.append_input_event"):
                    with patch("api.routers.input.append_trace_event"):
                        with patch("api.routers.input.emit_operation_timing", side_effect=capture_telemetry):
                            with patch("api.routers.input.safe_command") as mock_safe:
                                with patch("api.routers.input.run_async_command") as mock_run:
                                    mock_safe.return_value = {"ok": True, "stdout": "", "stderr": ""}
                                    mock_run.return_value = {"ok": True, "stdout": "12345\n", "stderr": ""}

                                    with patch.dict(os.environ, {"API_TOKEN": "test-token"}):
                                        client.post("/input/key", json=valid_payload, headers=auth_headers)

    ok_calls = [c for c in telemetry_calls if c.get("result") == "ok"]
    assert len(ok_calls) == 1, f"Expected 1 ok telemetry call, got {len(ok_calls)}"
    assert ok_calls[0]["feature"] == "input"
    assert ok_calls[0]["capability"] == "key_press"
    assert ok_calls[0]["operation"] == "api_key"
    assert ok_calls[0]["metric_name"] == "input.api_key.latency"


def test_key_press_emits_error_telemetry_on_backend_failure(
    auth_headers, valid_payload, tmp_path
):
    session_dir = _setup_session_dir(tmp_path)

    telemetry_calls = []

    def capture_telemetry(session_dir, **kwargs):
        telemetry_calls.append(dict(kwargs))

    with patch("api.routers.input.broker.check_access", return_value=True):
        with patch("api.routers.input.broker.report_agent_activity"):
            with patch("api.routers.input._require_active_session", return_value=session_dir):
                with patch("api.routers.input.append_input_event"):
                    with patch("api.routers.input.append_trace_event"):
                        with patch("api.routers.input.emit_operation_timing", side_effect=capture_telemetry):
                            with patch("api.routers.input.safe_command") as mock_safe:
                                with patch("api.routers.input.run_async_command") as mock_run:
                                    mock_safe.return_value = {"ok": False, "stdout": "", "stderr": "AHK crashed"}
                                    mock_run.return_value = {"ok": True, "stdout": "12345\n", "stderr": ""}

                                    with patch.dict(os.environ, {"API_TOKEN": "test-token"}):
                                        response = client.post("/input/key", json=valid_payload, headers=auth_headers)

    assert response.status_code == 500
    error_calls = [c for c in telemetry_calls if c.get("result") == "error"]
    assert len(error_calls) == 1, f"Expected 1 error telemetry call, got {len(error_calls)}"
    assert error_calls[0]["feature"] == "input"
    assert error_calls[0]["capability"] == "key_press"


# ---------------------------------------------------------------------------
# Key translation conformance (xdotool -> AHK)
# ---------------------------------------------------------------------------

class TestKeyTranslationConformance:
    """Validate _xdotool_to_ahk_keys() against the documented key mapping."""

    def test_modifier_chords_basic(self):
        from api.routers.input import _xdotool_to_ahk_keys
        assert _xdotool_to_ahk_keys("ctrl+c") == "^c"
        assert _xdotool_to_ahk_keys("alt+F4") == "!{F4}"
        assert _xdotool_to_ahk_keys("shift+Tab") == "+{Tab}"
        assert _xdotool_to_ahk_keys("super+r") == "#r"

    def test_modifier_chords_composite(self):
        from api.routers.input import _xdotool_to_ahk_keys
        assert _xdotool_to_ahk_keys("ctrl+shift+a") == "^+a"
        assert _xdotool_to_ahk_keys("ctrl+alt+Delete") == "^!{Delete}"

    def test_named_keys_all(self):
        from api.routers.input import _xdotool_to_ahk_keys
        named = {
            "Return": "{Enter}", "Escape": "{Esc}", "Tab": "{Tab}",
            "BackSpace": "{BS}", "space": "{Space}", "Delete": "{Delete}",
            "Home": "{Home}", "End": "{End}", "PgUp": "{PgUp}", "PgDn": "{PgDn}",
            "Up": "{Up}", "Down": "{Down}", "Left": "{Left}", "Right": "{Right}",
        }
        for xdo, ahk in named.items():
            assert _xdotool_to_ahk_keys(xdo) == ahk, f"{xdo} -> expected {ahk}"

    def test_function_keys(self):
        from api.routers.input import _xdotool_to_ahk_keys
        for fk in range(1, 13):
            xdo = f"F{fk}"
            ahk = f"{{F{fk}}}"
            assert _xdotool_to_ahk_keys(xdo) == ahk

    def test_plain_text_passthrough(self):
        from api.routers.input import _xdotool_to_ahk_keys
        assert _xdotool_to_ahk_keys("Hello World") == "Hello World"
        assert _xdotool_to_ahk_keys("test@example.com") == "test@example.com"

    def test_empty_raises(self):
        from api.routers.input import _xdotool_to_ahk_keys
        with pytest.raises(ValueError):
            _xdotool_to_ahk_keys("")
        with pytest.raises(ValueError):
            _xdotool_to_ahk_keys("   ")

    def test_ahk_special_escaped(self):
        from api.routers.input import _xdotool_to_ahk_keys
        assert "{+}" in _xdotool_to_ahk_keys("+")
        assert "{^}" in _xdotool_to_ahk_keys("^")
        assert "{!}" in _xdotool_to_ahk_keys("!")
        assert "{#}" in _xdotool_to_ahk_keys("#")
