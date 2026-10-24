"""WinInspect daemon must be local-only and non-mutating until broker-qualified."""

from unittest.mock import MagicMock, patch

from api.core import wininspect as wi


def test_daemon_spawn_is_explicit_loopback_and_read_only(tmp_path):
    proc = MagicMock()
    proc.pid = 1234
    proc.poll.return_value = None
    with (
        patch.object(wi, "enabled", return_value=True),
        patch.object(wi, "installed", return_value=True),
        patch.object(wi, "_tcp_ready", side_effect=[False, False, True]),
        patch.object(wi, "_log_path", return_value=str(tmp_path / "local-daemon.log")),
        patch.object(wi, "manage_process"),
        patch.object(wi.subprocess, "Popen", return_value=proc) as spawn,
    ):
        result = wi.ensure_daemon(start=True)
    assert result["running"] is True
    assert result["started"] is True
    args = spawn.call_args.args[0]
    assert args[:2] == ["wine", str(wi.daemon_exe())]
    for flag in ("--no-config", "--ipv4", "--no-discovery", "--no-mdns", "--headless", "--read-only"):
        assert flag in args
    assert args[args.index("--bind") + 1] == "127.0.0.1"
    assert args[args.index("--port") + 1] == str(wi.port())
    assert "0.0.0.0" not in args
    assert "::" not in args
    assert spawn.call_args.kwargs["start_new_session"] is True


def test_not_installed_never_attempts_process_spawn():
    with (
        patch.object(wi, "enabled", return_value=True),
        patch.object(wi, "installed", return_value=False),
        patch.object(wi.subprocess, "Popen") as spawn,
    ):
        result = wi.ensure_daemon(start=True)
    assert result["installed"] is False
    assert result["running"] is False
    spawn.assert_not_called()


def test_read_only_state_probe_never_spawns_daemon():
    with (
        patch.object(wi, "enabled", return_value=True),
        patch.object(wi, "installed", return_value=True),
        patch.object(wi, "_tcp_ready", return_value=False),
        patch.object(wi, "_process_running", return_value=False),
        patch.object(wi.subprocess, "Popen") as spawn,
    ):
        result = wi.ensure_daemon(start=False)
    assert result["running"] is False
    spawn.assert_not_called()
