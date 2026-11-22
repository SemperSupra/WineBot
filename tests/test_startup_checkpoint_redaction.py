"""Fail-closed fixed-category WineBot startup log classification."""

import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
CLASSIFIER = ROOT / "scripts/ci/classify-startup-logs.py"


@pytest.mark.parametrize(
    ("diagnostic", "expected"),
    [
        ("WINEBOT_INFRA_CHECKPOINT=begin", "infra_begin"),
        ("WINEBOT_INFRA_CHECKPOINT=session_dirs_ready", "infra_session_ready"),
        ("WINEBOT_INFRA_CHECKPOINT=xvfb_ready", "infra_xvfb_ready"),
        ("WINEBOT_INFRA_CHECKPOINT=completed", "infra_completed"),
        ("WINEBOT_WRITER_ADMISSION=SESSION_ROOT_UNAVAILABLE", "unadmitted_root_rejected"),
        ("Pass 3: Wine Environment", "reached_wine"),
        ("Pass 4: Services", "reached_services"),
    ],
)
def test_checkpoint_classified_without_log_leak(diagnostic, expected):
    raw = f"SECRET_TOKEN=not-for-export /private/path\n{diagnostic}\n"
    result = subprocess.run(
        [sys.executable, str(CLASSIFIER)],
        input=raw,
        text=True,
        capture_output=True,
        timeout=5,
        check=True,
    )
    assert result.stdout == f"STARTUP_DIAGNOSTIC stage={expected}\n"
    assert result.stderr == ""
    assert "SECRET_TOKEN" not in result.stdout
    assert "/private/path" not in result.stdout


def test_later_infrastructure_checkpoint_wins_over_earlier():
    raw = "\n".join(
        (
            "Pass 2: Infrastructure",
            "WINEBOT_INFRA_CHECKPOINT=begin",
            "WINEBOT_INFRA_CHECKPOINT=session_dirs_ready",
            "WINEBOT_INFRA_CHECKPOINT=xvfb_ready",
        )
    )
    result = subprocess.run(
        [sys.executable, str(CLASSIFIER)],
        input=raw,
        capture_output=True,
        text=True,
        timeout=5,
        check=True,
    )
    assert result.stdout == "STARTUP_DIAGNOSTIC stage=infra_xvfb_ready\n"


def test_explicit_fail_closed_root_override_takes_priority_over_progress():
    raw = "\n".join(
        (
            "WINEBOT_INFRA_CHECKPOINT=session_dirs_ready",
            "WINEBOT_WRITER_ADMISSION=SESSION_ROOT_UNAVAILABLE",
            "SECRET_TOKEN=never-print",
        )
    )
    result = subprocess.run(
        [sys.executable, str(CLASSIFIER)],
        input=raw,
        capture_output=True,
        text=True,
        timeout=5,
        check=True,
    )
    assert result.stdout == "STARTUP_DIAGNOSTIC stage=unadmitted_root_rejected\n"
    assert "SECRET_TOKEN" not in result.stdout


def test_no_enumerated_marker_does_not_echo_untrusted_content():
    result = subprocess.run(
        [sys.executable, str(CLASSIFIER)],
        input="my-private-credential\n",
        capture_output=True,
        text=True,
        timeout=5,
        check=True,
    )
    assert result.stdout == "STARTUP_DIAGNOSTIC stage=unknown\n"
