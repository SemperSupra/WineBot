import json
import asyncio

from api.utils.process import safe_command, safe_async_command
from api.core.session_context import bind_session_dir


def _read_events(path: str):
    with open(path, "r", encoding="utf-8") as handle:
        return [json.loads(line) for line in handle.read().splitlines() if line.strip()]


def test_safe_command_emits_telemetry(monkeypatch, tmp_path):
    session_dir = tmp_path / "session-1"
    logs_dir = session_dir / "logs"
    logs_dir.mkdir(parents=True)
    monkeypatch.setenv("WINEBOT_SESSION_DIR", str(session_dir))
    monkeypatch.setenv("WINEBOT_TELEMETRY", "1")
    monkeypatch.setenv("WINEBOT_TELEMETRY_FEATURES", "runtime")
    monkeypatch.setenv("WINEBOT_TELEMETRY_CAPABILITIES", "command_substrate")
    monkeypatch.setenv("WINEBOT_TELEMETRY_SAMPLE_RATE", "1.0")

    result = safe_command(["true"])
    assert result["ok"] is True

    events = _read_events(str(logs_dir / "perf_metrics.jsonl"))
    assert events
    event = events[-1]
    assert event["feature"] == "runtime"
    assert event["capability"] == "command_substrate"
    assert event["operation"] == "safe_command"
    assert event["result"] == "ok"


def test_safe_command_timeout_emits_error_class(monkeypatch, tmp_path):
    session_dir = tmp_path / "session-1"
    logs_dir = session_dir / "logs"
    logs_dir.mkdir(parents=True)
    monkeypatch.setenv("WINEBOT_SESSION_DIR", str(session_dir))
    monkeypatch.setenv("WINEBOT_TELEMETRY", "1")
    monkeypatch.setenv("WINEBOT_TELEMETRY_FEATURES", "runtime")
    monkeypatch.setenv("WINEBOT_TELEMETRY_CAPABILITIES", "command_substrate")
    monkeypatch.setenv("WINEBOT_TELEMETRY_SAMPLE_RATE", "1.0")

    result = safe_command(["sleep", "5"], timeout=1)
    assert result["ok"] is False
    assert result["error"] == "timeout"

    events = _read_events(str(logs_dir / "perf_metrics.jsonl"))
    event = events[-1]
    assert event["operation"] == "safe_command"
    assert event["result"] == "error"
    assert event["tags"]["error_class"] == "timeout"


def test_safe_async_command_emits_telemetry(monkeypatch, tmp_path):
    session_dir = tmp_path / "session-1"
    logs_dir = session_dir / "logs"
    logs_dir.mkdir(parents=True)
    monkeypatch.setenv("WINEBOT_SESSION_DIR", str(session_dir))
    monkeypatch.setenv("WINEBOT_TELEMETRY", "1")
    monkeypatch.setenv("WINEBOT_TELEMETRY_FEATURES", "runtime")
    monkeypatch.setenv("WINEBOT_TELEMETRY_CAPABILITIES", "command_substrate")
    monkeypatch.setenv("WINEBOT_TELEMETRY_SAMPLE_RATE", "1.0")

    result = asyncio.run(safe_async_command(["true"], timeout=2))
    assert result["ok"] is True

    events = _read_events(str(logs_dir / "perf_metrics.jsonl"))
    event = events[-1]
    assert event["operation"] == "safe_async_command"
    assert event["result"] == "ok"


def test_session_context_overrides_env_for_telemetry(monkeypatch, tmp_path):
    env_session_dir = tmp_path / "env-session"
    ctx_session_dir = tmp_path / "ctx-session"
    (env_session_dir / "logs").mkdir(parents=True)
    (ctx_session_dir / "logs").mkdir(parents=True)

    monkeypatch.setenv("WINEBOT_SESSION_DIR", str(env_session_dir))
    monkeypatch.setenv("WINEBOT_TELEMETRY", "1")
    monkeypatch.setenv("WINEBOT_TELEMETRY_FEATURES", "runtime")
    monkeypatch.setenv("WINEBOT_TELEMETRY_CAPABILITIES", "command_substrate")
    monkeypatch.setenv("WINEBOT_TELEMETRY_SAMPLE_RATE", "1.0")

    with bind_session_dir(str(ctx_session_dir)):
        result = safe_command(["true"])
    assert result["ok"] is True

    assert not (env_session_dir / "logs" / "perf_metrics.jsonl").exists()
    ctx_events = _read_events(str(ctx_session_dir / "logs" / "perf_metrics.jsonl"))
    assert ctx_events
    assert ctx_events[-1]["operation"] == "safe_command"


def test_concurrent_session_context_isolation(monkeypatch, tmp_path):
    fallback_session_dir = tmp_path / "fallback-session"
    session_a = tmp_path / "session-a"
    session_b = tmp_path / "session-b"
    (fallback_session_dir / "logs").mkdir(parents=True)
    (session_a / "logs").mkdir(parents=True)
    (session_b / "logs").mkdir(parents=True)

    monkeypatch.setenv("WINEBOT_SESSION_DIR", str(fallback_session_dir))
    monkeypatch.setenv("WINEBOT_TELEMETRY", "1")
    monkeypatch.setenv("WINEBOT_TELEMETRY_FEATURES", "runtime")
    monkeypatch.setenv("WINEBOT_TELEMETRY_CAPABILITIES", "command_substrate")
    monkeypatch.setenv("WINEBOT_TELEMETRY_SAMPLE_RATE", "1.0")

    async def run_many(session_dir: str, n: int):
        for _ in range(n):
            with bind_session_dir(session_dir):
                result = await safe_async_command(["true"], timeout=2)
            assert result["ok"] is True

    async def main():
        await asyncio.gather(run_many(str(session_a), 5), run_many(str(session_b), 5))

    asyncio.run(main())

    assert not (fallback_session_dir / "logs" / "perf_metrics.jsonl").exists()
    events_a = _read_events(str(session_a / "logs" / "perf_metrics.jsonl"))
    events_b = _read_events(str(session_b / "logs" / "perf_metrics.jsonl"))
    assert len(events_a) == 5
    assert len(events_b) == 5
    assert all(event["operation"] == "safe_async_command" for event in events_a)
    assert all(event["operation"] == "safe_async_command" for event in events_b)
