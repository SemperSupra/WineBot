import json

from api.core import telemetry
from api.core.telemetry import emit_operation_timing
from api.utils.files import performance_metrics_log_path


def test_telemetry_feature_filter_blocks(monkeypatch, tmp_path):
    session_dir = tmp_path / "session-1"
    (session_dir / "logs").mkdir(parents=True)
    monkeypatch.setenv("WINEBOT_TELEMETRY", "1")
    monkeypatch.setenv("WINEBOT_TELEMETRY_FEATURES", "recording")

    emit_operation_timing(
        str(session_dir),
        feature="input",
        capability="mouse_click",
        feature_set="control_input_automation",
        operation="api_click",
        duration_ms=12.3,
    )
    assert not (session_dir / "logs" / "perf_metrics.jsonl").exists()


def test_telemetry_feature_filter_allows(monkeypatch, tmp_path):
    session_dir = tmp_path / "session-1"
    (session_dir / "logs").mkdir(parents=True)
    monkeypatch.setenv("WINEBOT_TELEMETRY", "1")
    monkeypatch.setenv("WINEBOT_TELEMETRY_FEATURES", "recording,input")
    monkeypatch.setenv("WINEBOT_TELEMETRY_SAMPLE_RATE", "1.0")

    emit_operation_timing(
        str(session_dir),
        feature="input",
        capability="mouse_click",
        feature_set="control_input_automation",
        operation="api_click",
        duration_ms=12.3,
        metric_name="input.api_click.latency",
    )
    path = performance_metrics_log_path(str(session_dir))
    with open(path, "r", encoding="utf-8") as handle:
        payload = json.loads(handle.read().strip())
    assert payload["feature"] == "input"
    assert payload["capability"] == "mouse_click"
    assert payload["metric"] == "input.api_click.latency"


def test_telemetry_sample_rate_zero(monkeypatch, tmp_path):
    session_dir = tmp_path / "session-1"
    (session_dir / "logs").mkdir(parents=True)
    monkeypatch.setenv("WINEBOT_TELEMETRY", "1")
    monkeypatch.setenv("WINEBOT_TELEMETRY_SAMPLE_RATE", "0")
    monkeypatch.setattr(telemetry.random, "random", lambda: 0.5)

    emit_operation_timing(
        str(session_dir),
        feature="recording",
        capability="pause_resume",
        feature_set="recording_and_artifacts",
        operation="api_pause",
        duration_ms=10.0,
    )
    assert not (session_dir / "logs" / "perf_metrics.jsonl").exists()
