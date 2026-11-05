"""Synthetic WineBot visual-profile selection and fail-closed CLI tests."""

import subprocess
from pathlib import Path

SCRIPT = Path(__file__).resolve().parents[1] / "scripts" / "wb"


def run(*args):
    return subprocess.run(
        ["bash", str(SCRIPT), "profile", "up", *args, "--dry-run"],
        capture_output=True, text=True, check=False, timeout=10,
    )


def test_human_readable_is_144_dpi_and_grayscale():
    p = run("human-interactive", "--visual", "human-readable")
    assert p.returncode == 0, p.stderr
    assert "WINE_DPI=144" in p.stdout
    assert "WINE_FONT_SMOOTHING=grayscale" in p.stdout
    assert "WINEBOT_INSTANCE_CONTROL_MODE=human-only" in p.stdout


def test_assistive_readable_does_not_grant_new_control():
    p = run("supervised-agent", "--visual", "assistive-readable")
    assert p.returncode == 0, p.stderr
    assert "WINE_DPI=144" in p.stdout
    assert "WINEBOT_INSTANCE_CONTROL_MODE=hybrid" in p.stdout


def test_deterministic_cv_does_not_change_agent_permissions():
    p = run("agent-batch", "--visual", "deterministic-cv")
    assert p.returncode == 0, p.stderr
    assert "WINE_DPI=96" in p.stdout
    assert "WINE_FONT_SMOOTHING=grayscale" in p.stdout
    assert "WINEBOT_INSTANCE_CONTROL_MODE=agent-only" in p.stdout


def test_visual_and_performance_axes_compose_independently():
    p = run("human-exploratory", "--performance", "low-latency",
            "--visual", "human-readable")
    assert p.returncode == 0, p.stderr
    assert "WINEBOT_PERFORMANCE_PROFILE=low-latency" in p.stdout
    assert "WINE_DPI=144" in p.stdout


def test_default_behavior_retains_existing_config_values():
    p = run("ci-gate")
    assert p.returncode == 0, p.stderr
    assert "WINE_DPI=" not in p.stdout
    assert "WINE_FONT_SMOOTHING=" not in p.stdout


def test_unknown_visual_profile_fails_closed():
    p = run("human-interactive", "--visual", "do-not-exist")
    assert p.returncode != 0
    assert "WINE_DPI=" not in p.stdout


def test_missing_visual_argument_fails_closed():
    p = run("human-interactive", "--visual")
    assert p.returncode != 0


def test_unknown_base_profile_stays_blocked():
    p = run("bad-control-profile", "--visual", "human-readable")
    assert p.returncode != 0


def test_list_exposes_each_visual_profile():
    p = subprocess.run(["bash", str(SCRIPT), "profile", "list"],
                       capture_output=True, text=True, check=False, timeout=10)
    assert p.returncode == 0
    for name in ("human-readable", "assistive-readable", "deterministic-cv"):
        assert name in p.stdout
