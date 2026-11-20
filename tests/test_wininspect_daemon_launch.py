"""WineBot's WinInspect adapter must use headless TCP daemon mode.

Synthetic subprocess only: no real Wine process, network port or user files.
"""
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

from api.core import wininspect as wi


def test_rpc_daemon_uses_upstream_headless_mode(tmp_path):
    fake = SimpleNamespace(pid=42, poll=lambda: None)
    with (
        patch.object(wi, "_daemon_proc", None),
        patch.object(wi, "enabled", return_value=True),
        patch.object(wi, "installed", return_value=True),
        patch.object(wi, "_tcp_ready", side_effect=[False, False, True]),
        patch.object(wi, "daemon_exe", return_value=Path("/synthetic/wininspectd.exe")),
        patch.object(wi, "_log_path", return_value=str(tmp_path / "wininspectd.log")),
        patch.object(wi.subprocess, "Popen", return_value=fake) as launch,
        patch.object(wi, "manage_process"),
    ):
        result = wi.ensure_daemon(start=True)
    assert result["running"] is True
    assert result["started"] is True
    assert launch.call_args.args[0] == [
        "wine",
        "/synthetic/wininspectd.exe",
        "--headless",
        "--bind", "127.0.0.1", "--port", str(wi.DEFAULT_PORT),
    ]


def test_real_wine_workflow_refuses_known_unqualified_observer_binary_early():
    """The observer must not burn a Wine build on a known-failing native ZIP."""
    repo = Path(__file__).resolve().parents[1]
    workflow = (repo / ".github/workflows/mvp-ic1-windows-workloads.yml").read_text()
    gate = "Fail early on the known-unqualified WinInspect observer binary"
    assert workflow.count(gate) == 1
    assert workflow.index(gate) < workflow.index("Reclaim disposable standard-runner disk")
    assert "test -f scripts/ci/qualify-mvp-wininspect-live.py" in workflow
    assert "WinInspectPortable-v0.4.4.zip" in workflow
    assert "IC1_OBSERVER_CAUSE=upstream_binary_unqualified" in workflow
    assert "exit 1" in workflow[workflow.index(gate):workflow.index("Reclaim disposable standard-runner disk")]
