import subprocess
from pathlib import Path
import os


WB = Path(__file__).resolve().parent.parent / "scripts" / "wb"
WINEBOTCTL = Path(__file__).resolve().parent.parent / "scripts" / "bin" / "winebotctl"


def test_wb_help_contract():
    result = subprocess.run(
        [str(WB), "help"],
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode == 0
    assert "profile" in result.stdout
    assert "feature-map" in result.stdout


def test_wb_unknown_command_fails():
    result = subprocess.run(
        [str(WB), "no-such-command"],
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode != 0
    assert "Unknown command" in result.stdout


def test_winebotctl_help_contract():
    result = subprocess.run(
        [str(WINEBOTCTL), "--help"],
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode == 0
    assert "api METHOD PATH" in result.stdout
    assert "lifecycle status|events|shutdown" in result.stdout


def test_wb_profile_list_includes_use_case_and_performance_profiles():
    result = subprocess.run(
        [str(WB), "profile", "list"],
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode == 0
    assert "human-interactive" in result.stdout
    assert "agent-batch" in result.stdout
    assert "low-latency" in result.stdout
    assert "diagnostic" in result.stdout


def test_wb_profile_up_dry_run_renders_environment():
    result = subprocess.run(
        [
            str(WB),
            "profile",
            "up",
            "supervised-agent",
            "--performance",
            "balanced",
            "--dry-run",
        ],
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode == 0
    assert "MODE=interactive" in result.stdout
    assert "WINEBOT_USE_CASE_PROFILE=supervised-agent" in result.stdout
    assert "WINEBOT_PERFORMANCE_PROFILE=balanced" in result.stdout


def test_wb_profile_up_rejects_invalid_use_case_performance_combo():
    result = subprocess.run(
        [
            str(WB),
            "profile",
            "up",
            "ci-gate",
            "--performance",
            "diagnostic",
            "--dry-run",
        ],
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode != 0
    combined = f"{result.stdout}\n{result.stderr}"
    assert "invalid profile selection" in combined


def test_winebotctl_config_profile_set_supports_performance_flag(tmp_path):
    env = os.environ.copy()
    env["HOME"] = str(tmp_path)
    env["HOSTNAME"] = "testhost"
    result = subprocess.run(
        [
            str(WINEBOTCTL),
            "config",
            "profile",
            "set",
            "human-interactive",
            "--performance",
            "low-latency",
        ],
        capture_output=True,
        text=True,
        check=False,
        env=env,
    )
    assert result.returncode == 0
    assert "Applied use-case profile 'human-interactive'" in result.stdout
    cfg = tmp_path / ".config" / "winebot" / "env"
    assert cfg.exists()
    contents = cfg.read_text(encoding="utf-8")
    assert "WINEBOT_USE_CASE_PROFILE='human-interactive'" in contents
    assert "WINEBOT_PERFORMANCE_PROFILE='low-latency'" in contents


def test_winebotctl_config_profile_set_rejects_invalid_combo(tmp_path):
    env = os.environ.copy()
    env["HOME"] = str(tmp_path)
    env["HOSTNAME"] = "testhost"
    result = subprocess.run(
        [
            str(WINEBOTCTL),
            "config",
            "profile",
            "set",
            "ci-gate",
            "--performance",
            "diagnostic",
        ],
        capture_output=True,
        text=True,
        check=False,
        env=env,
    )
    assert result.returncode != 0
    combined = f"{result.stdout}\n{result.stderr}"
    assert "Unknown or invalid profile selection" in combined
