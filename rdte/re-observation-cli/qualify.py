#!/usr/bin/env python3
"""Run the actual compiled receipt CLI on original synthetic fixtures."""
import json
import os
import pathlib
import subprocess
import sys
import tempfile

source = "a" * 40
rows = [
    ("module", "0x140000000", 8192),
    ("heap_allocation", "0x200040", 256),
    ("memory_region", "0x200000", 4096),
]
alloc = "0034:trace:heap:RtlAllocateHeap handle 0xabc, flags 0, size 0x100, return 0x200040, status 0.\n"
release = "0034:trace:heap:RtlFreeHeap handle 0xabc, flags 0, ptr 0x200040, return 1, status 0.\n"

def main():
    binary = sys.argv[1]
    with tempfile.TemporaryDirectory() as work:
        witness = pathlib.Path(work, "witness.jsonl")
        trace = pathlib.Path(work, "filtered.heap")
        witness.write_text("".join(json.dumps({
            "schema": "wine-introspection-rdte/v0",
            "source": "WIN32_API_ENUMERATED",
            "kind": kind, "process_id": 42,
            "address_space": "windows_process_va",
            "address": address, "size_bytes": size,
            "object_id": None, "generation": None,
            "semantic_type": None, "snapshot": "best_effort",
            "coverage": "partial",
        }) + "\n" for kind, address, size in rows), encoding="utf-8")
        trace.write_text(alloc + release, encoding="utf-8")
        args = [binary, "-witness", str(witness), "-trace", str(trace), "-source-commit", source]
        def invoke(argv):
            return subprocess.run(argv, capture_output=True, text=True, timeout=5, check=False)
        result = invoke(args)
        assert result.returncode == 0 and not result.stderr
        receipt = json.loads(result.stdout)
        assert receipt["schema"] == "winebot.research.synthetic-lifetime-join/v1"
        assert receipt["source_commit"] == source and receipt["witness_records"] == 3
        for key, value in {
            "evidence_class": "SYNTHETIC_CONSISTENCY_ONLY", "trust": "UNVERIFIED",
            "source_attestation": "UNVERIFIED", "process_attribution": "UNKNOWN",
            "trace_completeness": "UNKNOWN", "clock_correlation": "UNAVAILABLE",
            "semantic_identity": "UNKNOWN",
        }.items():
            assert receipt[key] == value
        for secret in ("0x200040", "0xabc", "process_id", str(witness), str(trace)):
            assert secret not in result.stdout
        def refuse(argv):
            result = invoke(argv)
            assert result.returncode != 0 and result.stdout == ""
            assert result.stderr.strip() == "WINEBOT_OBSERVATION=REFUSED"
        trace.write_text(alloc, encoding="utf-8")
        refuse(args)
        trace.write_text(alloc + release.replace("0xabc", "0xdef"), encoding="utf-8")
        refuse(args)
        trace.write_text(alloc + release, encoding="utf-8")
        refuse(args[:-1] + ["not-a-source"])
        refuse([binary, "-witness", str(witness)])
        trace.unlink()
        os.symlink(witness, trace)
        refuse(args)
    print("OBSERVATION_CLI=PASS")

if __name__ == "__main__":
    try:
        main()
    except Exception:
        raise SystemExit("OBSERVATION_CLI=FAIL")
