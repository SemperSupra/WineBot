import json

from api.core import telemetry
from api.core.telemetry import emit_operation_timing
from api.utils.files import performance_metrics_log_path


def _read_one(path: str):
    with open(path, "r", encoding="utf-8") as handle:
        return json.loads(handle.read().strip())


def test_telemetry_payload_contract(monkeypatch, tmp_path):
    session_dir = tmp_path / "session-telemetry"
    (session_dir / "logs").mkdir(parents=True)
    monkeypatch.setenv("WINEBOT_TELEMETRY", "1")
    monkeypatch.setenv("WINEBOT_TELEMETRY_SAMPLE_RATE", "1.0")

    emit_operation_timing(
        str(session_dir),
        feature="recording",
        capability="pause_resume",
        feature_set="recording_and_artifacts",
        operation="api_pause",
        duration_ms=12.34,
        result="ok",
        source="api",
        tags={"status": "paused"},
    )
    payload = _read_one(performance_metrics_log_path(str(session_dir)))
    required = {
        "schema_version",
        "timestamp_utc",
        "timestamp_epoch_ms",
        "event",
        "metric",
        "value_ms",
        "feature",
        "capability",
        "feature_set",
        "operation",
        "result",
        "source",
        "session_id",
    }
    missing = required.difference(payload.keys())
    assert not missing, f"missing keys: {sorted(missing)}"
    assert payload["event"] == "performance_metric"


def test_telemetry_rate_limit(monkeypatch, tmp_path):
    session_dir = tmp_path / "session-telemetry"
    (session_dir / "logs").mkdir(parents=True)
    monkeypatch.setenv("WINEBOT_TELEMETRY", "1")
    monkeypatch.setenv("WINEBOT_TELEMETRY_SAMPLE_RATE", "1.0")
    monkeypatch.setenv("WINEBOT_TELEMETRY_MAX_EVENTS_PER_MIN", "1")
    telemetry._event_timestamps.clear()

    emit_operation_timing(
        str(session_dir),
        feature="input",
        capability="mouse_click",
        feature_set="control_input_automation",
        operation="api_click",
        duration_ms=1.0,
    )
    emit_operation_timing(
        str(session_dir),
        feature="input",
        capability="mouse_click",
        feature_set="control_input_automation",
        operation="api_click",
        duration_ms=2.0,
    )

    with open(performance_metrics_log_path(str(session_dir)), "r", encoding="utf-8") as handle:
        lines = [line for line in handle.read().splitlines() if line.strip()]
    assert len(lines) == 1
