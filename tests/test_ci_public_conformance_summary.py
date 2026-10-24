"""Regression checks for minimizing public conformance evidence."""

from __future__ import annotations

import json
import runpy
import subprocess
import sys
from pathlib import Path

import pytest

PROJECT = runpy.run_path("scripts/ci/sanitize-conformance-results.py")["project_public_result"]
SCRIPT = Path("scripts/ci/sanitize-conformance-results.py")


def sample_report() -> dict:
    return {
        "summary": {
            "total": 3,
            "passed": 1,
            "failed": 1,
            "skipped": 1,
            "xfailed": 0,
            "xpassed": 0,
            "errors": 0,
        },
        "environment": {
            "hostname": "sensitive-host-alias",
            "api_token": "SENSITIVE-TOKEN-VALUE",
        },
        "failures": [
            {
                "test": "contracts/tests/conformance/test_health.py::TestHealth::test_health",
                "message": "secret SENSITIVE-TOKEN-VALUE; actual host sensitive-host-alias",
            }
        ],
        "other_untrusted": "SENSITIVE-TOKEN-VALUE",
    }


def test_projection_preserves_counts_and_only_static_test_identifiers() -> None:
    report = PROJECT(sample_report())
    assert report["summary"]["total"] == 3
    assert report["summary"]["failed"] == 1
    assert report["failed_tests"] == [
        {"test_id": "contracts/tests/conformance/test_health.py::TestHealth::test_health"}
    ]
    rendered = json.dumps(report)
    assert "sensitive-host-alias" not in rendered
    assert "SENSITIVE-TOKEN-VALUE" not in rendered
    assert "message" not in rendered
    assert "environment" not in rendered


def test_bare_pytest_basename_is_preserved_without_runtime_text() -> None:
    raw = sample_report()
    raw["failures"][0]["test"] = "test_automation.py::TestWindows::test_windows_has_count"
    report = PROJECT(raw)
    assert report["failed_tests"] == [
        {"test_id": "test_automation.py::TestWindows::test_windows_has_count"}
    ]
    assert "SENSITIVE-TOKEN-VALUE" not in json.dumps(report)


def test_untrusted_test_id_is_redacted_instead_of_republished() -> None:
    raw = sample_report()
    raw["failures"][0]["test"] = "tests/conformance/test_health.py::test_a[param=private-token]"
    assert PROJECT(raw)["failed_tests"] == [{"test_id": "redacted"}]


@pytest.mark.parametrize(
    "change",
    [
        lambda raw: raw["summary"].update({"failed": True}),
        lambda raw: raw["summary"].update({"total": 7}),
        lambda raw: raw.update({"failures": []}),
        lambda raw: raw.update({"summary": "bad"}),
    ],
)
def test_invalid_reports_fail_closed(change) -> None:
    raw = sample_report()
    change(raw)
    with pytest.raises(ValueError):
        PROJECT(raw)


def test_command_does_not_write_artifact_if_input_invalid(tmp_path: Path) -> None:
    raw = sample_report()
    raw["summary"]["total"] = 9
    input_path = tmp_path / "raw.json"
    out = tmp_path / "public.json"
    input_path.write_text(json.dumps(raw), encoding="utf-8")
    process = subprocess.run(
        [sys.executable, str(SCRIPT), "--input", str(input_path), "--output", str(out)],
        capture_output=True,
        text=True,
        check=False,
    )
    assert process.returncode != 0
    assert not out.exists()

@pytest.mark.parametrize(
    "workflow_path",
    [".github/workflows/ci.yml", ".github/workflows/release.yml"],
)
def test_public_workflows_do_not_publish_raw_conformance_data(workflow_path: str) -> None:
    source = Path(workflow_path).read_text(encoding="utf-8")
    assert "--tb=no --show-capture=no -rN" in source
    assert "path: conformance-summary-public.json" in source
    assert "path: conformance-results.json" not in source
    assert "steps.public-conformance-summary.outcome == 'success'" in source
    assert "TOKEN:0:8" not in source

def test_quiet_pytest_console_does_not_echo_assertion_response(tmp_path: Path) -> None:
    fixture = tmp_path / "test_probe_private_payload.py"
    fixture.write_text(
        'def test_probe():\n'
        '    payload = {"value": "SYNTHETIC-UNPUBLISHED-MARKER"}\n'
        '    assert "count" in payload\n',
        encoding="utf-8",
    )
    process = subprocess.run(
        [
            sys.executable,
            "-m",
            "pytest",
            str(fixture),
            "-v",
            "--tb=no",
            "--show-capture=no",
            "-rN",
        ],
        capture_output=True,
        text=True,
        check=False,
        timeout=30,
    )
    assert process.returncode == 1
    assert "1 failed" in process.stdout
    assert "SYNTHETIC-UNPUBLISHED-MARKER" not in process.stdout
    assert "SYNTHETIC-UNPUBLISHED-MARKER" not in process.stderr
