"""Fail-closed Wine trace-path retries without native Wine or private fixtures."""

import os
import subprocess
from pathlib import Path

import pytest

SCRIPT = Path("scripts/init/winepath-with-retry.sh")


@pytest.mark.parametrize(
    ("mode", "expected_rc", "expected_count"),
    [("recover", 0, 3), ("fail", 1, 4), ("multiline", 1, 4)],
)
def test_bounded_trace_path_retry(
    tmp_path: Path, mode: str, expected_rc: int, expected_count: int
) -> None:
    tool = tmp_path / "winepath"
    tool.write_text(
        "#!/bin/sh\n"
        "set -eu\n"
        'count="$(cat "$WINEPATH_COUNTER" 2>/dev/null || printf 0)"\n'
        'count=$((count + 1))\n'
        'printf "%s" "$count" > "$WINEPATH_COUNTER"\n'
        'if [ "$WINEPATH_MODE" = recover ] && [ "$count" -ge 3 ]; then\n'
        "  printf 'Z:\\\\trace.jsonl\\n'\n"
        "  exit 0\n"
        "fi\n"
        'if [ "$WINEPATH_MODE" = multiline ]; then\n'
        "  printf 'Z:\\\\trace.jsonl\\nSYNTHETIC_PRIVATE_MARKER\\n'\n"
        "  exit 0\n"
        "fi\n"
        "echo SYNTHETIC_PRIVATE_MARKER >&2\n"
        "exit 1\n",
        encoding="utf-8",
    )
    tool.chmod(0o755)
    sleep = tmp_path / "sleep"
    sleep.write_text("#!/bin/sh\nexit 0\n", encoding="utf-8")
    sleep.chmod(0o755)
    counter = tmp_path / "counter"
    env = os.environ.copy()
    env.update(
        PATH=f"{tmp_path}:{env['PATH']}",
        WINEPATH_COUNTER=str(counter),
        WINEPATH_MODE=mode,
    )
    result = subprocess.run(
        ["bash", str(SCRIPT), "/synthetic/trace.jsonl"],
        env=env,
        capture_output=True,
        text=True,
        timeout=45,
        check=False,
    )
    assert result.returncode == expected_rc
    assert int(counter.read_text(encoding="utf-8")) == expected_count
    assert "SYNTHETIC_PRIVATE_MARKER" not in result.stdout + result.stderr
    if expected_rc == 0:
        assert result.stdout == "Z:\\trace.jsonl\n"
    else:
        assert not result.stdout


def test_crlf_terminated_winepath_output_is_normalized(tmp_path: Path) -> None:
    tool = tmp_path / "winepath"
    tool.write_text(
        "#!/bin/sh\nprintf 'Z:\\\\trace.jsonl\\r\\n'\n",
        encoding="utf-8",
    )
    tool.chmod(0o755)
    env = os.environ.copy()
    env["PATH"] = f"{tmp_path}:{env['PATH']}"
    result = subprocess.run(
        ["bash", str(SCRIPT), "/synthetic/trace.jsonl"],
        env=env,
        capture_output=True,
        text=True,
        timeout=15,
        check=False,
    )
    assert result.returncode == 0
    assert result.stdout == "Z:\\trace.jsonl\n"
    assert result.stderr == ""


def test_no_input_rejected_without_wine_process() -> None:
    result = subprocess.run(
        ["bash", str(SCRIPT)],
        capture_output=True,
        text=True,
        timeout=5,
        check=False,
    )
    assert result.returncode == 2
    assert result.stdout == ""


@pytest.mark.parametrize("exit_code,expected", [(124, "timeout"), (127, "nonzero")])
def test_failed_winepath_reports_bounded_reason_without_secret(
    tmp_path: Path, exit_code: int, expected: str
) -> None:
    tool = tmp_path / "winepath"
    tool.write_text("#!/bin/sh\necho PRIVATE_SECRET_SENTINEL >&2\nexit 1\n")
    tool.chmod(0o755)
    timeout_tool = tmp_path / "timeout"
    timeout_tool.write_text(f"#!/bin/sh\nexit {exit_code}\n")
    timeout_tool.chmod(0o755)
    sleep_tool = tmp_path / "sleep"
    sleep_tool.write_text("#!/bin/sh\nexit 0\n")
    sleep_tool.chmod(0o755)
    env = dict(os.environ)
    env["PATH"] = f"{tmp_path}:{env['PATH']}"
    result = subprocess.run(
        ["bash", str(SCRIPT), "/synthetic/SECRET_PATH_SENTINEL"],
        env=env, capture_output=True, text=True, timeout=12, check=False
    )
    assert result.returncode == 1
    assert result.stdout == ""
    assert result.stderr.strip() == f"WINEPATH_DIAGNOSTIC stage={expected}"
    assert "SECRET_PATH_SENTINEL" not in result.stdout + result.stderr
    assert "PRIVATE_SECRET_SENTINEL" not in result.stdout + result.stderr


def test_trace_classifier_projects_fixed_winepath_cause_only() -> None:
    result = subprocess.run(
        ["python3", "scripts/ci/classify-startup-logs.py"],
        input=("SENSITIVE_TOKEN_SENTINEL\n"
               "WINEPATH_DIAGNOSTIC stage=timeout\n"
               "WINEBOT_STARTUP_ERROR stage=services/trace-log-path rc=1\n"),
        text=True, capture_output=True, timeout=8, check=True
    )
    assert result.stdout.splitlines() == [
        "STARTUP_DIAGNOSTIC stage=failed_trace_log_path",
        "STARTUP_DIAGNOSTIC winepath=timeout",
    ]
    assert "SENSITIVE_TOKEN_SENTINEL" not in result.stdout
