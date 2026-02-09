import json
import os
import threading
import time
from pathlib import Path
from unittest.mock import patch

from fastapi.testclient import TestClient

from api.core.models import InputTraceStartModel, InputTraceStopModel
from api.routers import input as input_router
from api.server import app


client = TestClient(app)


def _write_jsonl(path: Path, rows):
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w") as f:
        for row in rows:
            if isinstance(row, str):
                f.write(row + "\n")
            else:
                f.write(json.dumps(row) + "\n")


def test_input_events_tail_is_bounded_and_filtered(tmp_path):
    session_dir = tmp_path / "session-1"
    log_path = session_dir / "logs" / "input_events.jsonl"
    rows = [
        {"timestamp_epoch_ms": 1, "origin": "agent", "event": "a1"},
        {"timestamp_epoch_ms": 2, "origin": "user", "event": "u1"},
        {"timestamp_epoch_ms": 3, "origin": "agent", "event": "a2"},
        {"timestamp_epoch_ms": 4, "origin": "user", "event": "u2"},
        {"timestamp_epoch_ms": 5, "origin": "agent", "event": "a3"},
        "not-json",
        {"timestamp_epoch_ms": 6, "origin": "agent", "event": "a4"},
    ]
    _write_jsonl(log_path, rows)

    with patch.dict(os.environ, {"API_TOKEN": "test-token"}):
        with patch("api.routers.input.read_session_dir", return_value=str(session_dir)):
            response = client.get(
                "/input/events?limit=3&origin=agent",
                headers={"X-API-Key": "test-token"},
            )

    assert response.status_code == 200
    payload = response.json()
    assert payload["log_path"].endswith("input_events.jsonl")
    assert [item["event"] for item in payload["events"]] == ["a3", "a4"]


def test_lifecycle_events_tail_ignores_invalid_json(tmp_path):
    session_dir = tmp_path / "session-2"
    log_path = session_dir / "logs" / "lifecycle.jsonl"
    rows = [
        {"kind": "k1"},
        {"kind": "k2"},
        {"kind": "k3"},
        "bad-json",
        {"kind": "k4"},
    ]
    _write_jsonl(log_path, rows)

    with patch.dict(os.environ, {"API_TOKEN": "test-token"}):
        with patch("api.routers.lifecycle.read_session_dir", return_value=str(session_dir)):
            response = client.get(
                "/lifecycle/events?limit=3",
                headers={"X-API-Key": "test-token"},
            )

    assert response.status_code == 200
    payload = response.json()
    assert [item["kind"] for item in payload["events"]] == ["k3", "k4"]


def test_input_trace_start_concurrent_calls_spawn_once(tmp_path):
    session_dir = tmp_path
    state = {"running": False}
    results = []

    class FakeProc:
        pid = 4242

    def fake_running(_session_dir):
        return state["running"]

    def fake_popen(_cmd):
        # Delay helps overlap thread execution and exercise the lock path.
        time.sleep(0.02)
        state["running"] = True
        return FakeProc()

    def invoke_start():
        result = input_router.input_trace_start(
            InputTraceStartModel(session_dir=str(session_dir))
        )
        results.append(result["status"])

    with patch("api.routers.input.input_trace_running", side_effect=fake_running):
        with patch("api.routers.input.input_trace_pid", return_value=4242):
            with patch("api.routers.input.subprocess.Popen", side_effect=fake_popen) as mock_popen:
                with patch("api.routers.input.manage_process"):
                    with patch("api.routers.input.append_lifecycle_event"):
                        t1 = threading.Thread(target=invoke_start)
                        t2 = threading.Thread(target=invoke_start)
                        t1.start()
                        t2.start()
                        t1.join()
                        t2.join()

    assert mock_popen.call_count == 1
    assert sorted(results) == ["already_running", "started"]


def test_input_trace_stop_concurrent_calls_stop_once(tmp_path):
    session_dir = tmp_path
    state = {"running": True}
    results = []

    def fake_running(_session_dir):
        return state["running"]

    def fake_safe_command(_cmd):
        state["running"] = False
        return {"ok": True}

    def invoke_stop():
        result = input_router.input_trace_stop(
            InputTraceStopModel(session_dir=str(session_dir))
        )
        results.append(result["status"])

    with patch("api.routers.input.input_trace_running", side_effect=fake_running):
        with patch("api.routers.input.safe_command", side_effect=fake_safe_command) as mock_safe:
            with patch("api.routers.input.append_lifecycle_event"):
                t1 = threading.Thread(target=invoke_stop)
                t2 = threading.Thread(target=invoke_stop)
                t1.start()
                t2.start()
                t1.join()
                t2.join()

    assert mock_safe.call_count == 1
    assert sorted(results) == ["already_stopped", "stopped"]

