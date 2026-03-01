import json
from types import SimpleNamespace

from automation.recorder import __main__ as recorder_main


def test_cmd_stop_process_lookup_error_triggers_recovery(tmp_path, monkeypatch):
    session_dir = tmp_path / "session-recover"
    session_dir.mkdir()
    (session_dir / "recorder.pid").write_text("7777", encoding="utf-8")

    def fake_kill(_pid, _sig):
        raise ProcessLookupError

    called = {"value": False}

    def fake_recover(path: str, reason: str) -> bool:
        called["value"] = True
        assert path == str(session_dir)
        assert reason == "process_lookup_error"
        return True

    monkeypatch.setattr(recorder_main.os, "kill", fake_kill)
    monkeypatch.setattr(recorder_main, "attempt_recover_finalize", fake_recover)

    recorder_main.cmd_stop(SimpleNamespace(session_dir=str(session_dir)))
    assert called["value"] is True


def test_load_input_trace_events_redacts_sensitive_fields(tmp_path, monkeypatch):
    session_dir = tmp_path / "session-trace"
    logs_dir = session_dir / "logs"
    logs_dir.mkdir(parents=True)
    (session_dir / "session.json").write_text(
        json.dumps({"start_time_epoch": 1.0}), encoding="utf-8"
    )
    (logs_dir / "input_events.jsonl").write_text(
        json.dumps(
            {
                "event": "key_press",
                "timestamp_epoch_ms": 2000,
                "key": "A",
                "token": "secret-token",
                "x": 10,
                "y": 20,
            }
        )
        + "\n",
        encoding="utf-8",
    )

    monkeypatch.setenv("WINEBOT_INPUT_TRACE_RECORD", "1")
    monkeypatch.setenv("WINEBOT_RECORDING_INCLUDE_INPUT_TRACES", "1")
    monkeypatch.setenv("WINEBOT_RECORDING_REDACT_SENSITIVE", "1")

    events = recorder_main.load_input_trace_events(str(session_dir))
    assert len(events) == 1
    event = events[0]
    assert event.extra["token"] == "<redacted>"
    assert event.extra["key"] == "<redacted>"
