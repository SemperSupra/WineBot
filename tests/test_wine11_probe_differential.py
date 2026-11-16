"""Synthetic offline Wine 11 discriminator regression; no real Wine or Docker."""

import os
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def test_fake_docker_failure_categories_are_fixed_and_redacted(tmp_path: Path) -> None:
    fake = tmp_path / "docker"
    fake.write_text(
        "#!/bin/sh\n"
        "echo SYNTHETIC_PRIVATE_CANARY >&2\n"
        "echo SYNTHETIC_PRIVATE_CANARY\n"
        "exit 22\n",
        encoding="utf-8",
    )
    fake.chmod(0o755)
    env = os.environ.copy()
    env["PATH"] = str(tmp_path) + os.pathsep + env.get("PATH", "")
    result = subprocess.run(
        ["bash", str(ROOT / "scripts/ci/probe-wine11-prefix.sh")],
        env=env,
        capture_output=True,
        text=True,
        check=False,
        timeout=10,
    )
    assert result.returncode == 1
    assert "SYNTHETIC_PRIVATE_CANARY" not in result.stdout + result.stderr
    assert result.stdout.count("stage=boot_nonzero_registry_missing") == 4
    assert result.stdout.count("stage=target_mode_unqualified") == 1


def test_only_exact_target_can_qualify(tmp_path: Path) -> None:
    fake = tmp_path / "docker"
    fake.write_text(
        "#!/bin/sh\n"
        "case \" $* \" in\n"
        "  *\" WINEPREFIX=/wineprefix \"*) exit 22 ;;\n"
        "  *) exit 0 ;;\n"
        "esac\n",
        encoding="utf-8",
    )
    fake.chmod(0o755)
    env = os.environ.copy()
    env["PATH"] = str(tmp_path) + os.pathsep + env.get("PATH", "")
    result = subprocess.run(
        ["bash", str(ROOT / "scripts/ci/probe-wine11-prefix.sh")],
        env=env,
        capture_output=True,
        text=True,
        check=False,
        timeout=10,
    )
    assert result.returncode != 0
    assert "WINE_PREFIX_PROBE profile=alternate_prefix stage=pass" in result.stdout
    assert "WINE_PREFIX_PROBE profile=prewarmed_control stage=pass" in result.stdout
    assert "WINE_PREFIX_PROBE stage=target_mode_unqualified" in result.stdout


def test_image_cell_requires_owner_preparation_then_identity_drop() -> None:
    cell = (ROOT / "scripts/ci/wine11-prefix-cell.sh").read_text(encoding="utf-8")
    assert 'chown winebot:winebot "$WINEPREFIX"' in cell
    assert 'exec gosu winebot /bin/sh "$0" "$profile"' in cell
    assert '[ "$(id -u)" -eq 1000 ] || exit 31' in cell
    assert cell.index('exec gosu winebot') < cell.index('Xvfb :97')
    assert "wineboot -i >/dev/null 2>&1" in cell
    assert "exit 30" in cell and "exit 31" in cell
    assert "echo $WINEPREFIX" not in cell
