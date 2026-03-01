import json
from types import SimpleNamespace

from api.core.models import ControlMode
from api.core.monitor import (
    resolve_inactivity_pause_seconds,
    manual_pause_locked,
    set_manual_pause_lock,
)
from api.utils.files import append_performance_metric, performance_metrics_log_path


def test_resolve_inactivity_pause_seconds_human_override(monkeypatch):
    monkeypatch.setenv("WINEBOT_INACTIVITY_PAUSE_SECONDS", "180")
    monkeypatch.setenv("WINEBOT_INACTIVITY_PAUSE_SECONDS_HUMAN", "240")

    from api.core import monitor

    monkeypatch.setattr(
        monitor,
        "broker",
        SimpleNamespace(get_state=lambda: SimpleNamespace(control_mode=ControlMode.USER)),
    )
    assert resolve_inactivity_pause_seconds() == 240


def test_resolve_inactivity_pause_seconds_agent_override(monkeypatch):
    monkeypatch.setenv("WINEBOT_INACTIVITY_PAUSE_SECONDS", "180")
    monkeypatch.setenv("WINEBOT_INACTIVITY_PAUSE_SECONDS_AGENT", "90")

    from api.core import monitor

    monkeypatch.setattr(
        monitor,
        "broker",
        SimpleNamespace(get_state=lambda: SimpleNamespace(control_mode=ControlMode.AGENT)),
    )
    assert resolve_inactivity_pause_seconds() == 90


def test_append_performance_metric_writes_jsonl(tmp_path):
    session_dir = tmp_path / "session-1"
    (session_dir / "logs").mkdir(parents=True)

    append_performance_metric(
        str(session_dir),
        metric="recording.api_pause.latency",
        value_ms=123.45,
        source="test",
        extra={"ok": True},
    )

    path = performance_metrics_log_path(str(session_dir))
    with open(path, "r", encoding="utf-8") as handle:
        payload = json.loads(handle.read().strip())
    assert payload["event"] == "performance_metric"
    assert payload["metric"] == "recording.api_pause.latency"
    assert payload["source"] == "test"
    assert payload["extra"]["ok"] is True


def test_manual_pause_lock_roundtrip(tmp_path):
    session_dir = str(tmp_path / "session-lock")
    (tmp_path / "session-lock").mkdir(parents=True)
    set_manual_pause_lock(session_dir, True)
    assert manual_pause_locked(session_dir) is True
    set_manual_pause_lock(session_dir, False)
    assert manual_pause_locked(session_dir) is False
