"""Offline, deterministic public-runner Wine11 fault-recovery contract tests."""

import os
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts/ci/qualify-wine11-fault-recovery.sh"


def _invoke(tmp_path: Path, fake: str) -> subprocess.CompletedProcess:
    docker = tmp_path / "docker"
    docker.write_text("#!/bin/sh\n" + fake + "\n", encoding="utf-8")
    docker.chmod(0o755)
    env = os.environ.copy()
    env["PATH"] = str(tmp_path) + os.pathsep + env.get("PATH", "")
    return subprocess.run(
        ["bash", str(SCRIPT)],
        env=env,
        capture_output=True,
        text=True,
        check=False,
        timeout=12,
    )


def test_recovery_requires_new_openbox_process(tmp_path: Path) -> None:
    count = tmp_path / "counter"
    script = (
        'case " $* " in\n'
        '  *" pgrep -o -x openbox "*)\n'
        f'    n="$(cat "{count}" 2>/dev/null || echo 0)"\n'
        '    n=$((n + 1))\n'
        f'    printf "%s" "$n" > "{count}"\n'
        '    if [ "$n" -eq 1 ]; then echo 100; else echo 200; fi ;;\n'
        '  *" pkill -x openbox "*) exit 0 ;;\n'
        '  *) echo PRIVATE_CANARY >&2; exit 11 ;;\n'
        'esac'
    )
    result = _invoke(tmp_path, script)
    assert result.returncode == 0
    assert result.stdout.strip() == "WINE11_FAULT_DIAGNOSTIC stage=window_manager_recovered"
    assert "PRIVATE_CANARY" not in result.stdout + result.stderr
    assert count.read_text(encoding="utf-8") == "2"


def test_failed_injection_fails_closed_without_sensitive_output(tmp_path: Path) -> None:
    result = _invoke(
        tmp_path,
        'case " $* " in\n'
        '  *" pgrep -o -x openbox "*) echo 100 ;;\n'
        '  *" pkill -x openbox "*) echo PRIVATE_CANARY >&2; exit 42 ;;\n'
        '  *) exit 11 ;;\n'
        'esac',
    )
    assert result.returncode == 1
    assert result.stdout.strip() == "WINE11_FAULT_DIAGNOSTIC stage=bounded_injection_failed"
    assert "PRIVATE_CANARY" not in result.stdout + result.stderr


def test_missing_window_manager_fails_without_unsafe_retry(tmp_path: Path) -> None:
    result = _invoke(
        tmp_path,
        'echo PRIVATE_CANARY >&2; exit 1',
    )
    assert result.returncode == 1
    assert result.stdout.strip() == "WINE11_FAULT_DIAGNOSTIC stage=baseline_window_manager_missing"
    assert "PRIVATE_CANARY" not in result.stdout + result.stderr


def test_fault_qualification_is_ordered_after_full_soak() -> None:
    wf = (ROOT / ".github/workflows/nightly-rel-startup-qualification.yml").read_text(
        encoding="utf-8"
    )
    assert wf.index("Qualify Wine 11 sustained resource bounds for 55 minutes") < (
        wf.index("Inject bounded openbox fault and verify supervisor recovery")
    )
    assert wf.index("Inject bounded openbox fault and verify supervisor recovery") < (
        wf.index("Verify runtime health after window manager fault recovery")
    )
    assert "bash scripts/ci/qualify-wine11-fault-recovery.sh" in wf
    assert "actions/upload-artifact@" not in wf
