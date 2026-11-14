"""Synthetic failure-closure test for the Wine 11 Docker base prefix prewarmer.

The test never launches Wine or X11: injected fake tools only exercise the
Dockerfile shell control flow. No Wine stderr, paths or identity are published.
"""

from __future__ import annotations

import os
import subprocess
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def _prewarm_command() -> str:
    content = (ROOT / "docker/base.Dockerfile").read_text(encoding="utf-8")
    region = content.split("RUN set -eu; ", 1)[1].split("# 4. Final Base Layer", 1)[0]
    return "set -eu; " + region.replace("\\\n", " ")


def _fake_tool(directory: Path, name: str, source: str) -> None:
    target = directory / name
    target.write_text("#!/bin/sh\n" + source, encoding="utf-8")
    target.chmod(0o755)


def test_base_prefix_warmer_is_fail_closed_and_bounded() -> None:
    source = _prewarm_command()
    assert "|| true" not in source
    assert "timeout -k 5s 120s wineboot -i" in source
    assert "timeout -k 5s 60s wineserver -w" in source
    assert 'if [ ! -s "$WINEPREFIX/system.reg" ]; then' in source
    assert "WINE_BASE_PREFIX_DIAGNOSTIC stage=wineboot_failed" in source
    assert source.index('xdpyinfo -display "$DISPLAY"') < source.index("wineboot -i")
    assert source.index("wineboot -i") < source.index('"$WINEPREFIX/system.reg"')


def test_failed_wineboot_cannot_be_masked_by_cleanup(tmp_path: Path) -> None:
    source = _prewarm_command()
    theme = tmp_path / "synthetic-theme.sh"
    theme.write_text("#!/bin/sh\nexit 0\n", encoding="utf-8")
    theme.chmod(0o755)
    prefix = tmp_path / "synthetic-prefix"

    # Rewrite only the two absolute fixture paths for this offline shell test.
    # The production Dockerfile is left unchanged.
    source = source.replace(
        "/scripts/setup/install-theme.sh", str(theme)
    ).replace("/opt/winebot/prefix-template", str(prefix))
    _fake_tool(tmp_path, "Xvfb", "exec /bin/sleep 3\n")
    _fake_tool(tmp_path, "xdpyinfo", "exit 0\n")
    _fake_tool(
        tmp_path, "wineboot",
        "echo SYNTHETIC_PRIVATE_OUTPUT_MARKER >&2\nexit 57\n"
    )
    _fake_tool(tmp_path, "wineserver", "exit 0\n")
    _fake_tool(tmp_path, "wine", "exit 0\n")

    env = os.environ.copy()
    env["PATH"] = str(tmp_path) + os.pathsep + env.get("PATH", "")
    env["WINEPREFIX"] = str(prefix)
    result = subprocess.run(
        ["/bin/sh", "-ec", source],
        env=env,
        text=True,
        capture_output=True,
        timeout=10,
        check=False,
    )
    assert result.returncode != 0
    assert "WINE_BASE_PREFIX_DIAGNOSTIC stage=wineboot_failed" in result.stderr
    assert "SYNTHETIC_PRIVATE_OUTPUT_MARKER" not in result.stderr + result.stdout
