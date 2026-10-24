"""Synthetic/no-runtime falsification of the compatibility observation boundary."""

from __future__ import annotations

import copy
import json
from pathlib import Path

import pytest

from qualification.compare import InvalidObservation, compare, load_observation, main


def _observation(lane="windows"):
    return {
        "schema_version": "compat-observation/v0",
        "scenario": {
            "id": "synthetic-save-roundtrip", "revision": 1, "sha256": "a" * 64,
            "test_class": "workflow", "required_capabilities": ["file-roundtrip"],
        },
        "inputs": {"executable_sha256": "b" * 64, "fixture_sha256": "c" * 64},
        "execution": {
            "lane": lane, "run_id": "synthetic-run-1", "source_head_sha": "d" * 40,
            "tested_checkout_sha": "e" * 40,
        },
        "profile": {
            "architecture": "x86_64", "locale": "en-US", "display": "headless",
            "width": 1280, "height": 720, "dpi": 96, "renderer": "none",
        },
        "capabilities": ["file-roundtrip"],
        "assertions": [{"id": "save", "outcome": "PASS", "observed_sha256": "f" * 64}],
    }


def _pair():
    return _observation(), _observation("wine")


def test_identical_passes_without_raw_metadata():
    windows, wine = _pair()
    result = compare(windows, wine)
    assert result == {
        "schema_version": "compat-diff-public/v0", "verdict": "PASS",
        "reason_code": "MATCHED",
        "assertion_counts": {"matched": 1, "different": 0, "unqualified": 0},
    }
    assert "synthetic-save" not in json.dumps(result)


@pytest.mark.parametrize("field", ["executable_sha256", "fixture_sha256"])
def test_swapped_input_cannot_pass_or_fail(field):
    windows, wine = _pair()
    wine["inputs"][field] = "9" * 64
    assert compare(windows, wine)["verdict"] == "UNQUALIFIED"


def test_scenario_digest_mismatch():
    windows, wine = _pair()
    wine["scenario"]["sha256"] = "9" * 64
    assert compare(windows, wine)["reason_code"] == "MISMATCHED_INPUT"


def test_mismatched_display_is_unqualified():
    windows, wine = _pair()
    wine["profile"]["dpi"] = 144
    assert compare(windows, wine)["reason_code"] == "MISMATCHED_PROFILE"


def test_missing_capability_is_unqualified():
    windows, wine = _pair()
    wine["capabilities"] = []
    assert compare(windows, wine)["reason_code"] == "MISSING_CAPABILITY"


def test_different_observation_fails():
    windows, wine = _pair()
    wine["assertions"][0]["observed_sha256"] = "0" * 64
    assert compare(windows, wine)["reason_code"] == "DIFFERENT_OUTPUT"


def test_candidate_failed_outcome_fails():
    windows, wine = _pair()
    wine["assertions"][0].update(outcome="FAIL", observed_sha256=None)
    assert compare(windows, wine)["reason_code"] == "DIFFERENT_OUTCOME"


def test_native_windows_failed_oracle_is_not_pass():
    windows, wine = _pair()
    windows["assertions"][0].update(outcome="FAIL", observed_sha256=None)
    assert compare(windows, wine)["reason_code"] == "WINDOWS_ORACLE_FAILURE"


@pytest.mark.parametrize("status", ["SKIP", "UNQUALIFIED"])
def test_skipped_or_unqualified_candidate_never_passes(status):
    windows, wine = _pair()
    wine["assertions"][0].update(outcome=status, observed_sha256=None)
    assert compare(windows, wine)["verdict"] == "UNQUALIFIED"


def test_infra_error_never_passes():
    windows, wine = _pair()
    wine["assertions"][0].update(outcome="INFRA_ERROR", observed_sha256=None)
    assert compare(windows, wine)["verdict"] == "INFRA_ERROR"


def test_missing_assertion_is_unqualified():
    windows, wine = _pair()
    wine["assertions"] = []
    assert compare(windows, wine)["reason_code"] == "MISSING_ASSERTION"


def test_no_assertions_is_unqualified():
    windows, wine = _pair()
    windows["assertions"] = wine["assertions"] = []
    assert compare(windows, wine)["reason_code"] == "NO_ASSERTIONS"


def test_unsupported_visual_class_does_not_claim_parity():
    windows, wine = _pair()
    windows["scenario"]["test_class"] = wine["scenario"]["test_class"] = "visual"
    assert compare(windows, wine)["reason_code"] == "UNSUPPORTED_CLASS"


def test_duplicate_assertion_id_is_rejected():
    windows, wine = _pair()
    wine["assertions"].append(copy.deepcopy(wine["assertions"][0]))
    with pytest.raises(InvalidObservation):
        compare(windows, wine)


def test_extra_untrusted_field_is_rejected():
    windows, wine = _pair()
    wine["environment"] = {"hostname": "DO-NOT-ECHO"}
    with pytest.raises(InvalidObservation):
        compare(windows, wine)


def test_bool_dpi_is_rejected():
    windows, wine = _pair()
    wine["profile"]["dpi"] = True
    with pytest.raises(InvalidObservation):
        compare(windows, wine)


def test_wrong_lane_is_rejected():
    windows, wine = _pair()
    wine["execution"]["lane"] = "windows"
    with pytest.raises(InvalidObservation):
        compare(windows, wine)


def test_duplicate_json_key_rejected(tmp_path: Path):
    path = tmp_path / "synthetic.json"
    path.write_text('{"a":1,"a":2}', encoding="utf-8")
    with pytest.raises(InvalidObservation):
        load_observation(path)


def test_nan_rejected(tmp_path: Path):
    path = tmp_path / "synthetic.json"
    path.write_text('{"value":NaN}', encoding="utf-8")
    with pytest.raises(InvalidObservation):
        load_observation(path)


def test_large_payload_rejected(tmp_path: Path):
    path = tmp_path / "synthetic.json"
    path.write_bytes(b" " * (1024 * 1024 + 1))
    with pytest.raises(InvalidObservation):
        load_observation(path)


def test_cli_public_report_and_exit_codes(tmp_path: Path, capsys):
    windows, wine = _pair()
    n = tmp_path / "windows.json"
    w = tmp_path / "wine.json"
    report = tmp_path / "report.json"
    n.write_text(json.dumps(windows), encoding="utf-8")
    w.write_text(json.dumps(wine), encoding="utf-8")
    assert main(["--windows", str(n), "--wine", str(w), "--public-report", str(report)]) == 0
    output = json.loads(report.read_text(encoding="utf-8"))
    assert set(output) == {"schema_version", "verdict", "reason_code", "assertion_counts"}
    assert "PASS: MATCHED" in capsys.readouterr().out


def test_cli_no_stale_or_sensitive_output_on_invalid_input(tmp_path: Path, capsys):
    windows, _ = _pair()
    n = tmp_path / "windows.json"
    w = tmp_path / "wine.json"
    report = tmp_path / "report.json"
    n.write_text(json.dumps(windows), encoding="utf-8")
    w.write_text('{"hostname":"SECRET-SYNTHETIC-KEY"}', encoding="utf-8")
    report.write_text("OLD", encoding="utf-8")
    assert main(["--windows", str(n), "--wine", str(w), "--public-report", str(report)]) == 3
    combined = capsys.readouterr()
    assert "SECRET" not in combined.err + combined.out
    assert not report.exists()


def test_required_capabilities_cannot_duplicate():
    windows, wine = _pair()
    wine["capabilities"].append("file-roundtrip")
    with pytest.raises(InvalidObservation):
        compare(windows, wine)


def test_mutating_original_inputs_does_not_change_public_projection():
    windows, wine = _pair()
    base = compare(windows, wine)
    wine["execution"]["run_id"] = "new-run"
    wine["execution"]["source_head_sha"] = "1" * 40
    assert compare(windows, wine) == base


def test_schema_contracts_match_positive_fixture():
    # JSON Schema is supplemental documentation. Runtime validation is strict and
    # does not depend on a schema-validation package being installed.
    from qualification.compare import validate_observation

    schema_path = Path(__file__).resolve().parents[1] / "qualification/schemas"
    observation_schema = json.loads((schema_path / "observation-v0.schema.json").read_text())
    report_schema = json.loads((schema_path / "public-report-v0.schema.json").read_text())
    assert observation_schema["properties"]["schema_version"]["const"] == "compat-observation/v0"
    assert report_schema["properties"]["schema_version"]["const"] == "compat-diff-public/v0"
    assert observation_schema["additionalProperties"] is False
    assert report_schema["additionalProperties"] is False
    assert validate_observation(_observation()) == _observation()


def test_result_values_are_fixed_whitelist():
    from qualification.compare import REASONS, VERDICTS

    windows, wine = _pair()
    result = compare(windows, wine)
    assert result["reason_code"] in REASONS
    assert result["verdict"] in VERDICTS
