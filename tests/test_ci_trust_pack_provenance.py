"""Guard exact Git source-versus-checkout provenance in public trust packs."""

from __future__ import annotations

import os
import subprocess
from pathlib import Path

import pytest

GENERATOR = Path(__file__).resolve().parents[1] / "scripts/ci/generate-trust-pack.sh"
WORKFLOW = (
    Path(__file__).resolve().parents[1] / ".github/workflows/reusable-build-smoke-gate.yml"
)
CHECKOUT = "b" * 40
SOURCE = "a" * 40


@pytest.fixture
def workspace(tmp_path: Path) -> Path:
    bin_dir = tmp_path / "bin"
    bin_dir.mkdir()
    fake_git = bin_dir / "git"
    fake_git.write_text(
        "#!/bin/sh\n"
        'if [ "$1" = "rev-parse" ] && [ "$2" = "HEAD" ]; then\n'
        '  printf "%s\\n" "$FAKE_CHECKOUT_SHA"\n'
        'elif [ "$1" = "rev-parse" ] && [ "$2" = "--abbrev-ref" ]; then\n'
        '  printf "HEAD\\n"\n'
        "else\n"
        "  exit 7\n"
        "fi\n",
        encoding="utf-8",
    )
    fake_git.chmod(0o755)
    return tmp_path


def generate(workspace: Path, source: str | None = SOURCE, checkout: str = CHECKOUT):
    env = {
        **os.environ,
        "PATH": f"{workspace / 'bin'}:{os.environ.get('PATH', '')}",
        "FAKE_CHECKOUT_SHA": checkout,
    }
    if source is None:
        env.pop("WINEBOT_SOURCE_HEAD_SHA", None)
    else:
        env["WINEBOT_SOURCE_HEAD_SHA"] = source
    output = workspace / "pack"
    result = subprocess.run(
        ["bash", str(GENERATOR), str(output)],
        cwd=workspace,
        env=env,
        text=True,
        capture_output=True,
        check=False,
        timeout=30,
    )
    return result, output


def test_merged_checkout_not_misrepresented_as_source(workspace: Path) -> None:
    result, out = generate(workspace)
    assert result.returncode == 0, result.stderr
    summary = (out / "summary.md").read_text(encoding="utf-8")
    assert f"- Tested checkout commit: {CHECKOUT}" in summary
    assert f"- Source head commit: {SOURCE}" in summary
    assert "- Commit: " not in summary
    assert (out / "inventory.json").is_file()


def test_direct_checkout_defaults_source_to_tested_commit(workspace: Path) -> None:
    result, out = generate(workspace, source=None)
    assert result.returncode == 0, result.stderr
    summary = (out / "summary.md").read_text(encoding="utf-8")
    assert f"- Source head commit: {CHECKOUT}" in summary


@pytest.mark.parametrize(
    ("source", "checkout"),
    [("not-a-commit", CHECKOUT), (SOURCE, "invalid-checkout")],
)
def test_invalid_identity_fails_before_publishing(
    workspace: Path, source: str, checkout: str
) -> None:
    result, out = generate(workspace, source=source, checkout=checkout)
    assert result.returncode != 0
    assert not (out / "summary.md").exists()


def test_reusable_workflow_supplies_pr_source_head() -> None:
    workflow = WORKFLOW.read_text(encoding="utf-8")
    assert "WINEBOT_SOURCE_HEAD_SHA: ${{ github.event.pull_request.head.sha || github.sha }}" in workflow
