import subprocess
from pathlib import Path


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
