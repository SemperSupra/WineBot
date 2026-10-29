"""Fail closed on automatic Docker BuildKit record publication from public CI."""

from __future__ import annotations

import re
from pathlib import Path

WORKFLOW_DIR = Path(__file__).resolve().parents[1] / ".github" / "workflows"
BUILD_ACTION = "uses: docker/build-push-action@"
WORKFLOW_GUARD = "\nenv:\n  DOCKER_BUILD_RECORD_UPLOAD: 'false'\n"
DECLARATION = re.compile(r"(?m)^\s*DOCKER_BUILD_RECORD_UPLOAD:\s*(.*?)\s*$")


def _has_fail_closed_record_policy(source: str) -> bool:
    header, boundary, _ = source.partition("\njobs:\n")
    if not boundary:
        return False
    return WORKFLOW_GUARD in (header + "\n") and DECLARATION.findall(source) == ["'false'"]


def test_public_build_workflows_disable_automatic_build_record_upload() -> None:
    workflows = sorted(WORKFLOW_DIR.glob("*.yml"))
    build_workflows = [p for p in workflows if BUILD_ACTION in p.read_text(encoding="utf-8")]
    assert build_workflows, "No Docker build workflows found; re-evaluate policy scope"
    missing = [
        p.name
        for p in build_workflows
        if not _has_fail_closed_record_policy(p.read_text(encoding="utf-8"))
    ]
    assert not missing, f"Automatic unreviewed .dockerbuild publication enabled: {missing}"


def test_record_policy_fails_closed_on_missing_or_overridden_guard() -> None:
    protected = (
        "name: Build\n"
        "env:\n"
        "  DOCKER_BUILD_RECORD_UPLOAD: 'false'\n"
        "jobs:\n"
        "  build:\n"
        "    steps:\n"
        "      - uses: docker/build-push-action@v6\n"
    )
    assert _has_fail_closed_record_policy(protected)
    assert not _has_fail_closed_record_policy(protected.replace("env:\n", "not-env:\n"))
    assert not _has_fail_closed_record_policy(
        protected.replace("'false'\n", "'true'\n")
    )
    assert not _has_fail_closed_record_policy(
        protected + "      - env:\n          DOCKER_BUILD_RECORD_UPLOAD: 'true'\n"
    )

if __name__ == "__main__":
    test_public_build_workflows_disable_automatic_build_record_upload()
    test_record_policy_fails_closed_on_missing_or_overridden_guard()
