"""vNext public evidence is fixed, count-only, and opt-in to upload."""
from __future__ import annotations

import json
import runpy
from pathlib import Path

PROJECT = runpy.run_path("scripts/ci/project-vnext-public.py")["project_slices"]
LABELS = ("portable_core_candidate", "capability_extension_candidate",
          "implementation_specific", "obsolete_contract", "unresolved")


def test_fixed_five_slices_and_missing(tmp_path: Path) -> None:
    data = PROJECT(tmp_path)
    assert data["native_acceptance"] is False
    assert [x["slice"] for x in data["slices"]] == list(LABELS)
    assert all(x["status"] == "missing" for x in data["slices"])


def test_only_numeric_counts_survive_untrusted_fields(tmp_path: Path) -> None:
    summary = {"total": 2, "passed": 1, "failed": 1, "skipped": 0,
               "xfailed": 0, "xpassed": 0, "errors": 0}
    source = {"summary": summary, "failures": [
        {"test": "PRIVATE_TEST_MARKER", "message": "SECRET_HOST_SENTINEL"}],
        "environment": {"token": "SECRET_TOKEN_SENTINEL"}}
    (tmp_path / "vnext-internal-unresolved.json").write_text(
        json.dumps(source), encoding="utf-8"
    )
    data = PROJECT(tmp_path)
    rendered = json.dumps(data)
    assert "PRIVATE_TEST_MARKER" not in rendered
    assert "SECRET_HOST_SENTINEL" not in rendered
    assert "SECRET_TOKEN_SENTINEL" not in rendered
    assert data["slices"][-1] == {
        "slice": "unresolved", "status": "validated", "summary": summary
    }


def test_invalid_and_symlink_fail_closed(tmp_path: Path) -> None:
    path = tmp_path / "vnext-internal-unresolved.json"
    path.write_text('{"summary":{"total":2},"failures":[]}', encoding="utf-8")
    assert PROJECT(tmp_path)["slices"][-1]["status"] == "invalid"
    path.unlink()
    target = tmp_path / "synthetic-private.json"
    target.write_text("SECRET_TOKEN_SENTINEL", encoding="utf-8")
    path.symlink_to(target)
    assert PROJECT(tmp_path)["slices"][-1]["status"] == "invalid"


def test_legacy_gate_and_public_upload_hold() -> None:
    source = Path(".github/workflows/ci.yml").read_text(encoding="utf-8")
    assert "Run conformance tests" in source
    assert "Project safe public conformance evidence" in source
    assert "Run provisional vNext classified evidence slices" in source
    assert "WINEBOT_PUBLIC_VNEXT_SUMMARY_ENABLED == 'true'" in source
    assert "path: vnext-slices-public.json" in source
    assert "path: conformance-results.json" not in source
    assert "vnext-internal-*.json" not in source


def test_restart_health_wait_covers_docker_start_period() -> None:
    source = Path("scripts/ci/run-vnext-slices.sh").read_text(encoding="utf-8")
    compose = Path("compose/docker-compose.yml").read_text(encoding="utf-8")
    assert "start_period: 30s" in compose
    assert 'wait-for-container-health.sh "$compose" headless winebot 60 2' in source
    assert 'wait-for-container-health.sh "$compose" headless winebot 25 1' not in source


def test_runtime_logs_and_raw_results_stay_job_local() -> None:
    source = Path("scripts/ci/run-vnext-slices.sh").read_text(encoding="utf-8")
    assert 'raw="vnext-internal-$label.json"' in source
    assert '> "$local_log" 2>&1' in source
    assert "--tb=no --show-capture=no -rN" in source
    assert 'printf \'::add-mask::%s\\n\' "$token"' in source
    assert source.count('emit_stage') == 3  # declaration + two failure gates
    assert 'python3 winebot/scripts/ci/classify-startup-logs.py < "$health_log"' in source
    assert 'cat "$health_log"' not in source
    assert 'tail "$health_log"' not in source
