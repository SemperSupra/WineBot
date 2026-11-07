"""Public soak diagnostics reveal bounded numeric state, never raw runtime identity."""

from __future__ import annotations

import os
import subprocess
from pathlib import Path

SCRIPT = Path("scripts/diagnostics/diagnose-trace-soak.sh")


def test_zero_duration_soak_never_prints_private_endpoint() -> None:
    env = os.environ.copy()
    env.update(
        API_URL="http://SENSITIVE_HOST_SENTINEL:8000",
        API_TOKEN="SENSITIVE_TOKEN_SENTINEL",
        DURATION_SECONDS="0",
        INTERVAL_SECONDS="1",
        MAX_LOG_MB="10",
        MAX_SESSION_MB="10",
        MAX_PID1_RSS_MB="10",
    )
    result = subprocess.run(
        ["bash", str(SCRIPT)], env=env, text=True, capture_output=True,
        timeout=10, check=False
    )
    assert result.returncode == 0
    assert "[soak] PASS:" in result.stdout
    assert "SENSITIVE_HOST_SENTINEL" not in result.stdout + result.stderr
    assert "SENSITIVE_TOKEN_SENTINEL" not in result.stdout + result.stderr


def test_invalid_numeric_budget_fails_closed_without_echoing_value() -> None:
    env = os.environ.copy()
    env.update(DURATION_SECONDS="SENSITIVE_BUDGET_SENTINEL")
    result = subprocess.run(
        ["bash", str(SCRIPT)], env=env, text=True, capture_output=True,
        timeout=10, check=False
    )
    assert result.returncode == 2
    assert "INVALID_CONFIG key=DURATION_SECONDS" in result.stderr
    assert "SENSITIVE_BUDGET_SENTINEL" not in result.stdout + result.stderr


def test_soak_progress_excludes_raw_session_identifiers() -> None:
    source = SCRIPT.read_text(encoding="utf-8")
    assert "session_state=${session_state}" in source
    assert "session_dir=${session_dir" not in source
    assert "api=${API_URL}" not in source
    assert "session_state=present" in source
    assert "session_state=absent" in source


def test_soak_curl_failure_prints_only_fixed_stage(tmp_path: Path) -> None:
    # The fake curl exits without making a network connection; no Wine required.
    command = tmp_path / "curl"
    command.write_text("#!/bin/sh\nexit 7\n", encoding="utf-8")
    command.chmod(0o755)
    env = os.environ.copy()
    env.update(
        PATH=str(tmp_path) + os.pathsep + env.get("PATH", ""),
        API_URL="http://SENSITIVE_HOST_SENTINEL:8000",
        API_TOKEN="SENSITIVE_TOKEN_SENTINEL",
        DURATION_SECONDS="2",
        INTERVAL_SECONDS="1",
        MAX_LOG_MB="10",
        MAX_SESSION_MB="10",
        MAX_PID1_RSS_MB="10",
    )
    result = subprocess.run(
        ["bash", str(SCRIPT)], env=env, text=True, capture_output=True,
        timeout=10, check=False
    )
    assert result.returncode == 1
    assert "[soak] FAIL stage=health_request" in result.stderr
    for secret in ("SENSITIVE_HOST_SENTINEL", "SENSITIVE_TOKEN_SENTINEL"):
        assert secret not in result.stdout + result.stderr


def test_soak_health_failures_never_request_verbose_curl_errors() -> None:
    source = SCRIPT.read_text(encoding="utf-8")
    assert "curl -fsS " not in source
    for stage in ("health_request", "system_health_request",
                  "recording_health_request", "recording_metadata_invalid",
                  "log_usage_unavailable", "session_usage_unavailable"):
        assert "FAIL stage=" + stage in source
