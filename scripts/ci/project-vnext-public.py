#!/usr/bin/env python3
"""Project exactly five provisional vNext slices to public numeric counts only."""
from __future__ import annotations

import argparse
import json
import runpy
from pathlib import Path

LABELS = ("portable_core_candidate", "capability_extension_candidate",
          "implementation_specific", "obsolete_contract", "unresolved")
SAN = runpy.run_path(str(Path(__file__).with_name("sanitize-conformance-results.py")))
PROJECT = SAN["project_public_result"]
MAX_BYTES = SAN["MAX_RAW_BYTES"]


def project_slices(raw_dir: Path) -> dict:
    slices = []
    for label in LABELS:
        path = raw_dir / f"vnext-internal-{label}.json"
        entry = {"slice": label, "status": "missing"}
        try:
            if path.is_symlink():
                raise ValueError("symlink")
            if path.is_file():
                if path.stat().st_size > MAX_BYTES:
                    raise ValueError("oversize")
                projected = PROJECT(json.loads(path.read_text(encoding="utf-8")))
                entry = {"slice": label, "status": "validated",
                         "summary": projected["summary"]}
        except (ValueError, UnicodeError, OSError):
            entry = {"slice": label, "status": "invalid"}
        slices.append(entry)
    return {"schema": "winebot.public-vnext-slices.v1",
            "provisional": True, "native_acceptance": False, "slices": slices}


# Only these checked-in contract test modules may identify a public failure
# domain. The raw test node ID, assertion and response body never leave runner.
FAILURE_MODULES = {
    "test_automation.py": "automation",
    "test_errors.py": "error_response",
    "test_headers.py": "headers",
    "test_health.py": "health",
    "test_idempotency.py": "operations",
    "test_input.py": "input",
    "test_lifecycle.py": "lifecycle",
    "test_recording.py": "recording",
    "test_tracing.py": "tracing",
    "test_version.py": "version",
}
MAX_PUBLIC_COUNT = 1_000_000

FAILURE_CASES = {
    "test_lifecycle.py::TestLifecycleShutdown::test_shutdown_returns_200": "lifecycle_shutdown_http",
    "test_lifecycle.py::TestLifecycleShutdown::test_shutdown_has_required_fields": "lifecycle_shutdown_fields",
    "test_lifecycle.py::TestLifecycleShutdown::test_shutdown_with_custom_delay": "lifecycle_shutdown_delay",
    "test_lifecycle.py::TestLifecycleShutdown::test_shutdown_invalid_delay_rejected": "lifecycle_invalid_delay",
    "test_lifecycle.py::TestLifecycleShutdown::test_shutdown_too_large_delay_rejected": "lifecycle_oversized_delay",
    "test_lifecycle.py::TestLifecycleCancel::test_cancel_without_pending": "lifecycle_cancel_idle",
    "test_lifecycle.py::TestLifecycleCancel::test_cancel_aborts_pending_shutdown": "lifecycle_cancel_pending",
    "test_automation.py::TestScreenshot::test_screenshot_returns_200_or_acceptable": "automation_screenshot",
    "test_automation.py::TestWindows::test_windows_returns_200": "automation_windows_http",
    "test_automation.py::TestWindows::test_windows_has_count": "automation_windows_count",
    "test_automation.py::TestWindows::test_windows_has_list": "automation_windows_list",
    "test_automation.py::TestWindowFocus::test_focus_nonexistent_window": "automation_focus_missing",
    "test_automation.py::TestWindowFocus::test_focus_empty_title": "automation_focus_empty",
    "test_automation.py::TestInspectWindow::test_inspect_returns_200": "automation_inspect",
    "test_automation.py::TestAppRun::test_app_run_missing_path": "automation_app_missing",
    "test_automation.py::TestAppRun::test_app_run_with_valid_path": "automation_app_valid",
}



def project_fixed_failure_domains(path: Path, expected_failures: int) -> dict[str, int]:
    """Count source-backed failure modules; any unknown ID becomes 'other'."""
    counts = {domain: 0 for domain in FAILURE_MODULES.values()}
    counts["other"] = 0
    if path.is_symlink() or not path.is_file() or path.stat().st_size > MAX_BYTES:
        raise ValueError("invalid raw source")
    raw = json.loads(path.read_text(encoding="utf-8"))
    # Reuse existing strict count/inventory validation. No free-form data copies.
    projected = PROJECT(raw)
    if projected["summary"]["failed"] != expected_failures:
        raise ValueError("failure count mismatch")
    for failure in raw["failures"]:
        test = failure.get("test")
        domain = "other"
        if isinstance(test, str) and len(test) <= 500:
            for module, fixed_domain in FAILURE_MODULES.items():
                if (test.startswith(f"contracts/tests/conformance/{module}::")
                    or test.startswith(f"tests/conformance/{module}::")
                    or test.startswith(f"{module}::")):
                    domain = fixed_domain
                    break
        counts[domain] += 1
    return counts



def project_fixed_failure_cases(path: Path, expected_failures: int) -> dict[str, int]:
    """Project only exact pinned test IDs to predeclared, non-sensitive enums."""
    if path.is_symlink() or not path.is_file() or path.stat().st_size > MAX_BYTES:
        raise ValueError("invalid raw source")
    raw = json.loads(path.read_text(encoding="utf-8"))
    projected = PROJECT(raw)
    if projected["summary"]["failed"] != expected_failures:
        raise ValueError("failure count mismatch")
    counts: dict[str, int] = {}
    for failure in raw["failures"]:
        test = failure.get("test")
        if not isinstance(test, str) or len(test) > 500:
            continue
        # Accept only the three known pytest checkout prefixes; never echo a
        # raw test ID or a heuristic suffix match from the untrusted payload.
        for prefix in ("contracts/tests/conformance/", "tests/conformance/", ""):
            if prefix and not test.startswith(prefix):
                continue
            fixed = FAILURE_CASES.get(test[len(prefix):])
            if fixed is not None:
                counts[fixed] = counts.get(fixed, 0) + 1
                break
    return counts


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--raw-dir", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    public = project_slices(args.raw_dir)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(public, indent=2, sort_keys=True) + "\n",
                           encoding="utf-8")
    # CI may emit only exact fixed labels and numerically validated counts.
    # A deliberately conservative cap prevents enormous untrusted integers
    # from expanding Actions stdout; raw test IDs and response data stay local.
    for entry in public["slices"]:
        label = entry["slice"]
        status = entry["status"]
        if status != "validated":
            print(f"VNEXT_PUBLIC_COUNT slice={label} status={status}")
            continue
        summary = entry["summary"]
        if any(value > 1000000 for value in summary.values()):
            print(f"VNEXT_PUBLIC_COUNT slice={label} status=withheld")
            continue
        counts = " ".join(
            f"{key}={summary[key]}" for key in SAN["COUNT_FIELDS"]
        )
        print(f"VNEXT_PUBLIC_COUNT slice={label} status=validated {counts}")
        # Additional safe, fixed-domain counters identify WHICH capability
        # area needs attention, not the raw testcase/host/window identifier.
        raw_path = args.raw_dir / f"vnext-internal-{label}.json"
        try:
            domain_counts = project_fixed_failure_domains(raw_path, summary["failed"])
        except (ValueError, UnicodeError, OSError, TypeError):
            print(f"VNEXT_PUBLIC_FAILURE_DOMAIN slice={label} status=withheld")
            continue
        for domain, failed in domain_counts.items():
            if 0 < failed <= MAX_PUBLIC_COUNT:
                print(
                    f"VNEXT_PUBLIC_FAILURE_DOMAIN slice={label} "
                    f"domain={domain} failed={failed}"
                )
        try:
            case_counts = project_fixed_failure_cases(raw_path, summary["failed"])
        except (ValueError, UnicodeError, OSError, TypeError):
            print(f"VNEXT_PUBLIC_FAILURE_CASE slice={label} status=withheld")
            continue
        for case, failed in sorted(case_counts.items()):
            if 0 < failed <= MAX_PUBLIC_COUNT:
                print(
                    f"VNEXT_PUBLIC_FAILURE_CASE slice={label} "
                    f"case={case} failed={failed}"
                )
    print("Safe provisional vNext numerical counts projected")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
