#!/usr/bin/env python3
"""Project raw conformance results into a minimal public evidence artifact.

The underlying report may contain runtime responses, host identity, credentials,
or user-facing window titles. Never copy its free-form fields to a public artifact.
"""

from __future__ import annotations

import argparse
import json
import re
from pathlib import Path

MAX_RAW_BYTES = 1_048_576
COUNT_FIELDS = ("total", "passed", "failed", "skipped", "xfailed", "xpassed", "errors")
SAFE_TEST_ID = re.compile(
    r"(?:contracts/)?tests/conformance/test_[A-Za-z0-9_]+\.py"
    r"(?:::\w+)*::test_[A-Za-z0-9_]+"
)


def project_public_result(raw: object) -> dict:
    """Build output solely from validated, bounded, allowlisted fields."""
    if not isinstance(raw, dict) or not isinstance(raw.get("summary"), dict):
        raise ValueError("missing or invalid conformance summary")

    summary = raw["summary"]
    counts = {}
    for key in COUNT_FIELDS:
        value = summary.get(key)
        if type(value) is not int or value < 0:
            raise ValueError("invalid conformance count")
        counts[key] = value
    if sum(counts[k] for k in COUNT_FIELDS if k != "total") != counts["total"]:
        raise ValueError("inconsistent conformance counts")

    failures = raw.get("failures")
    if not isinstance(failures, list) or len(failures) != counts["failed"]:
        raise ValueError("inconsistent failure inventory")

    tests = []
    for item in failures:
        if not isinstance(item, dict):
            raise ValueError("invalid failure entry")
        name = item.get("test")
        safe_name = (
            name
            if isinstance(name, str) and len(name) <= 200 and SAFE_TEST_ID.fullmatch(name)
            else "redacted"
        )
        tests.append({"test_id": safe_name})

    return {
        "schema": "winebot.public-conformance.v1",
        "summary": counts,
        "failed_tests": tests,
        "note": "Raw failure payloads and environment details remain job-local.",
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--input", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()

    if not args.input.is_file() or args.input.stat().st_size > MAX_RAW_BYTES:
        raise SystemExit("Conformance source unavailable or exceeds the public projection limit")
    try:
        original = json.loads(args.input.read_text(encoding="utf-8"))
        public = project_public_result(original)
    except (ValueError, UnicodeError, OSError):
        raise SystemExit("Conformance report cannot be safely projected") from None

    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(public, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print("Public conformance report projected without raw failure/environment fields")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
