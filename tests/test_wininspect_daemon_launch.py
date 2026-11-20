"""WineBot's WinInspect adapter must use headless TCP daemon mode.

Synthetic subprocess only: no real Wine process, network port or user files.
"""
from pathlib import Path
import runpy

import pytest
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
    # A superficial rename must not evade the known bad archive digest.
    assert "6ac0a65f774ffe69672f1c459254931ebfddb1e52c9fbec14b5db1348ccaad04" in workflow
    assert "IC1_OBSERVER_CAUSE=upstream_binary_unqualified" in workflow
    assert "exit 1" in workflow[workflow.index(gate):workflow.index("Reclaim disposable standard-runner disk")]

@pytest.mark.parametrize(
    ("match", "info", "expected"),
    [
        (
            {"hwnd": "0xA1"},
            {"hwnd": "0xA1", "title": "sample.txt - Notepad++",
             "visible": True, "pid": 193.0},
            True,
        ),
        ({"hwnd": "0xA1"}, {"hwnd": "0xB2", "title": "Notepad++",
                              "visible": True, "pid": 193}, False),
        ({"hwnd": "0xA1"}, {"hwnd": "0xA1", "raw": "opaque"}, False),
        ({"hwnd": "0xA1"}, {"hwnd": "0xA1", "title": "Other editor",
                              "visible": True, "pid": 193}, False),
        ({"hwnd": "0xA1"}, {"hwnd": "0xA1", "title": "Notepad++",
                              "visible": False, "pid": 193}, False),
        ({"hwnd": "0xA1"}, {"hwnd": "0xA1", "title": "Notepad++",
                              "visible": True, "pid": 0}, False),
        ({"hwnd": "0xA1"}, {"hwnd": "0xA1", "title": "Notepad++",
                              "visible": True, "pid": True}, False),
        ({"hwnd": "0x0"}, {"hwnd": "0x0", "title": "Notepad++",
                             "visible": True, "pid": 193}, False),
        ({"hwnd": "not-a-handle"}, {"hwnd": "not-a-handle",
                                     "title": "Notepad++", "visible": True,
                                     "pid": 193}, False),
        ("malformed", {"hwnd": "0xA1", "title": "Notepad++",
                        "visible": True, "pid": 193}, False),
        ({"hwnd": "0xA1"}, ["malformed"], False),
    ],
)
def test_live_observer_requires_same_visible_notepad_hwnd(match, info, expected):
    """Read-only live acceptance must not pass on fallback, stale or hidden windows."""
    repo = Path(__file__).resolve().parents[1]
    probe = runpy.run_path(
        str(repo / "scripts/ci/qualify-mvp-wininspect-live.py")
    )["qualified_notepad_window"]
    assert probe(match, info) is expected
