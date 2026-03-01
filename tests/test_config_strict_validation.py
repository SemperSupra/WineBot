import os
import subprocess
import sys
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parent.parent


def _run_import_with_env(extra_env: dict[str, str]) -> subprocess.CompletedProcess[str]:
    env = os.environ.copy()
    env.update(extra_env)
    return subprocess.run(
        [sys.executable, "-c", "import api.utils.config"],
        cwd=str(REPO_ROOT),
        env=env,
        capture_output=True,
        text=True,
        check=False,
    )


def test_config_validation_fails_closed_for_invalid_int():
    result = _run_import_with_env({"WINEBOT_MAX_LOG_SIZE_MB": "not-an-int"})
    assert result.returncode != 0
    combined = f"{result.stdout}\n{result.stderr}"
    assert "Configuration validation failed" in combined
    assert "WINEBOT_MAX_LOG_SIZE_MB must be an integer" in combined


def test_config_validation_fails_closed_for_invalid_bool():
    result = _run_import_with_env({"WINEBOT_PERF_METRICS": "sometimes"})
    assert result.returncode != 0
    combined = f"{result.stdout}\n{result.stderr}"
    assert "Configuration validation failed" in combined
    assert "WINEBOT_PERF_METRICS must be a boolean" in combined
