"""Synthetic long-soak diagnostic custody: no real hosts, Wine or tokens."""

import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
CLASSIFIER = ROOT / "scripts/ci/classify-wine11-soak.py"


def _run(tmp_path: Path, line: str) -> str:
    sample = tmp_path / "job-local.txt"
    sample.write_text("SYNTHETIC_PRIVATE_CANARY\n" + line + "\n", encoding="utf-8")
    result = subprocess.run(
        [sys.executable, str(CLASSIFIER), str(sample)],
        capture_output=True, text=True, check=True, timeout=10,
    )
    assert "SYNTHETIC_PRIVATE_CANARY" not in result.stdout + result.stderr
    return result.stdout.strip()


def test_fixed_failure_categories(tmp_path: Path) -> None:
    assert _run(tmp_path, "[soak] FAIL stage=health_request") == (
        "WINE11_SOAK_DIAGNOSTIC stage=health_request"
    )
    assert _run(tmp_path, "[soak] FAIL: log size 32 exceeds 16") == (
        "WINE11_SOAK_DIAGNOSTIC stage=log_limit"
    )
    assert _run(tmp_path, "[soak] FAIL: session size 32 exceeds 16") == (
        "WINE11_SOAK_DIAGNOSTIC stage=session_limit"
    )
    assert _run(tmp_path, "[soak] FAIL: pid1 VmRSS 2049kB exceeds 1024kB") == (
        "WINE11_SOAK_DIAGNOSTIC stage=memory_limit"
    )


def test_unknown_and_symlink_fail_closed(tmp_path: Path) -> None:
    assert _run(tmp_path, "[soak] FAIL stage=SYNTHETIC_PRIVATE_CANARY") == (
        "WINE11_SOAK_DIAGNOSTIC stage=unknown"
    )
    source = tmp_path / "private.txt"
    source.write_text("SYNTHETIC_SECRET", encoding="utf-8")
    symlink = tmp_path / "reference.txt"
    symlink.symlink_to(source)
    result = subprocess.run(
        [sys.executable, str(CLASSIFIER), str(symlink)],
        capture_output=True, text=True, check=True, timeout=10,
    )
    assert result.stdout.strip() == "WINE11_SOAK_DIAGNOSTIC stage=unknown"
    assert "SYNTHETIC_SECRET" not in result.stdout + result.stderr


def test_workflow_remains_public_and_draft_only() -> None:
    wf = (ROOT / ".github/workflows/nightly-rel-startup-qualification.yml").read_text(
        encoding="utf-8"
    )
    assert "runs-on: ubuntu-24.04" in wf
    assert "timeout-minutes: 90" in wf
    assert "DURATION_SECONDS=3300" in wf
    assert "INTERVAL_SECONDS=30" in wf
    assert "MAX_PID1_RSS_MB=2048" in wf
    assert "classify-wine11-soak.py rel-long-soak-job-local.log" in wf
    assert wf.index("Sample live REL trace resource bounds for 90 seconds") < (
        wf.index("Qualify Wine 11 sustained resource bounds for 55 minutes")
    )
    assert wf.index("Qualify Wine 11 sustained resource bounds for 55 minutes") < (
        wf.index("Verify container remains healthy after sustained soak")
    )
    assert "actions/upload-artifact@" not in wf
    assert "push: true" not in wf
