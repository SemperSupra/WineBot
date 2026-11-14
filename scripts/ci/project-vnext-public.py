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
    print("Safe provisional vNext numerical counts projected")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
