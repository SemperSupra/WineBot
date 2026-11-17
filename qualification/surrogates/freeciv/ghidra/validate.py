#!/usr/bin/env python3
"""Fail-closed validation of the public Freeciv Ghidra static witness."""

import argparse
import hashlib
import json
import re
from pathlib import Path

SCHEMA = "freeciv-ghidra-static/v0.1"
EXPECTED_FIELDS = {"schema", "execution_class", "artifact_sha256", "function_count",
                   "interval_count", "pc_correlated"}
MAX_REPORT_BYTES = 4096


def no_duplicate_keys(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise ValueError("DUPLICATE_WITNESS_KEY")
        result[key] = value
    return result


def validate(raw, binary):
    if not (0 < len(raw) <= MAX_REPORT_BYTES):
        raise ValueError("WITNESS_SIZE_INVALID")
    try:
        report = json.loads(raw, object_pairs_hook=no_duplicate_keys)
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise ValueError("WITNESS_JSON_INVALID") from exc
    if not isinstance(report, dict) or set(report) != EXPECTED_FIELDS:
        raise ValueError("WITNESS_FIELDS_INVALID")
    if (report["schema"] != SCHEMA or report["execution_class"] !=
            "REAL_GHIDRA_SOURCE_KNOWN_STATIC_ONLY"):
        raise ValueError("WITNESS_CLASS_INVALID")
    digest = report["artifact_sha256"]
    if not isinstance(digest, str) or not re.fullmatch("[0-9a-f]{64}", digest):
        raise ValueError("WITNESS_DIGEST_INVALID")
    if hashlib.sha256(binary).hexdigest() != digest:
        raise ValueError("WITNESS_BINARY_IDENTITY_MISMATCH")
    functions, intervals = report["function_count"], report["interval_count"]
    if type(functions) is not int or type(intervals) is not int or not (100 <= functions <= intervals <= 10000000):
        raise ValueError("WITNESS_FUNCTION_INTERVALS_INVALID")
    if report["pc_correlated"] is not False:
        raise ValueError("WITNESS_PC_CLAIM_NOT_ACCEPTED")
    return {"schema": SCHEMA, "status": "PASS", "artifact_sha256": digest,
            "functions": functions, "intervals": intervals,
            "evidence_class": "REAL_GHIDRA_STATIC_INDEX_ONLY", "pc_correlated": False}


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--input", required=True)
    ap.add_argument("--binary", required=True)
    ap.add_argument("--output", required=True)
    args = ap.parse_args()
    original = Path(args.binary)
    if original.is_symlink() or not original.is_file():
        raise SystemExit("GHIDRA_BINARY_BOUNDARY_INVALID")
    result = validate(Path(args.input).read_bytes(), original.read_bytes())
    Path(args.output).write_text(json.dumps(result, sort_keys=True) + "\n", encoding="utf-8")
    print("PUBLIC_GHIDRA_STATIC_WITNESS_ACCEPTED")


if __name__ == "__main__":
    main()
