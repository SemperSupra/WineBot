#!/usr/bin/env python3
"""Select exact synthetic allocation/free events from a private Wine 11 +heap log.

Never print raw addresses, paths, trace lines or application payloads.
This source-only filter is not evidence of semantic object identity.
"""
import argparse
import json
import pathlib
import re
import sys

MAX_RAW_BYTES = 128 << 20
MAX_WITNESS_BYTES = 12288
MAX_EVENT_BYTES = 16384
ALLOC = re.compile(
    r"trace:heap:RtlAllocateHeap handle [0-9a-fA-Fx]+, flags [0-9a-fA-Fx]+, "
    r"size [0-9a-fA-Fx]+, return (?P<ptr>[0-9a-fA-Fx]+), status [0-9a-fA-Fx]+\."
)
FREE = re.compile(
    r"trace:heap:RtlFreeHeap handle [0-9a-fA-Fx]+, flags [0-9a-fA-Fx]+, "
    r"ptr (?P<ptr>[0-9a-fA-Fx]+), return [01], status [0-9a-fA-Fx]+\."
)


def filter_trace(witness: pathlib.Path, raw: pathlib.Path, output: pathlib.Path) -> None:
    if witness.stat().st_size <= 0 or witness.stat().st_size > MAX_WITNESS_BYTES:
        raise ValueError("invalid witness size")
    if raw.stat().st_size <= 0 or raw.stat().st_size > MAX_RAW_BYTES:
        raise ValueError("invalid trace size")
    records = [json.loads(line) for line in witness.read_text("utf-8").splitlines()]
    if len(records) != 3 or [r.get("kind") for r in records] != [
        "module", "heap_allocation", "memory_region"
    ]:
        raise ValueError("wrong witness cardinality")
    allocation = records[1]
    if allocation.get("schema") != "wine-introspection-rdte/v0" or (
        allocation.get("source") != "WIN32_API_ENUMERATED"
    ):
        raise ValueError("unproved Wine allocation")
    address = allocation.get("address")
    size = allocation.get("size_bytes")
    if not isinstance(address, str) or not re.fullmatch(r"0x[0-9a-fA-F]{1,16}", address):
        raise ValueError("invalid pointer")
    if not isinstance(size, int) or isinstance(size, bool) or size < 1:
        raise ValueError("invalid allocation size")
    target = int(address, 16)
    matches = []
    with raw.open("r", encoding="utf-8", errors="replace") as source:
        for line in source:
            if len(line.encode("utf-8")) > MAX_EVENT_BYTES:
                raise ValueError("overlong trace line")
            if "trace:heap:RtlAllocateHeap" not in line and (
                "trace:heap:RtlFreeHeap" not in line
            ):
                continue
            event = ALLOC.search(line) or FREE.search(line)
            if event and int(event.group("ptr"), 16) == target:
                matches.append(line)
                if len(matches) > 16:
                    raise ValueError("ambiguous trace target")
    # The Go oracle—not this filter—decides whether alloc/free semantics hold.
    output.write_text("".join(matches), encoding="utf-8")


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--witness", type=pathlib.Path, required=True)
    parser.add_argument("--trace", type=pathlib.Path, required=True)
    parser.add_argument("--output", type=pathlib.Path, required=True)
    args = parser.parse_args()
    try:
        filter_trace(args.witness, args.trace, args.output)
    except (OSError, ValueError, TypeError, json.JSONDecodeError):
        print("FAIL: wine11_heap_trace_selection", file=sys.stderr)
        sys.exit(1)
