#!/usr/bin/env python3
"""Public-safe syscall boundary classification: local paths/data never leave workcell.

Do not interpret syscall counts as decoder/engine semantics. The underlying
source-neutral event relationship is (process,fd,path-class,operation,bytes).
Raw per-event traces remain ephemeral; output contains aggregate counts only.
"""
import argparse
import json
import re
from collections import Counter
from pathlib import Path

SCHEMA = "freeciv-io-boundaries/v0.1"
MAX_FILE_BYTES = 32 * 1024 * 1024
MAX_LINES = 300_000
FN = re.compile(r"^(?:[0-9]+(?:\.[0-9]+)?\s+)?(openat2?|read|pread64|readv|write|pwrite64|writev|mmap|mmap2|lseek|close)\(")
FD = re.compile(r"(?<![0-9])(-?[0-9]+)<([^>\n]{1,2048})>")
RET = re.compile(r"\)\s+=\s+(-?[0-9]+)(?:\s|$|<)")
MAP_RET = re.compile(r"\)\s+=\s+0x[0-9a-fA-F]+(?:\s|$)")
NATIVE_PATH = re.compile(r"(?:^|/)\.\.(?:/|$)")


def file_category(path):
    p = path.lower()
    if NATIVE_PATH.search(p):
        return "other"
    # No path names, hashes, data bytes or filesystem identities are exported.
    if any(x in p for x in (".sav", "/save/", "/saves/")):
        return "save_candidate"
    if any(p.endswith(x) for x in (".so", ".so.0", ".so.1", ".dll")) or ".so." in p:
        return "library_candidate"
    if p.endswith((".ini", ".cfg", ".conf", ".json", ".xml")):
        return "config_candidate"
    if p.endswith((".png", ".bmp", ".wav", ".ogg", ".zip", ".pak", ".dat")):
        return "asset_candidate"
    return "other"


def parse_trace(folder):
    """Require complete bounded traces; never emit raw trace lines/paths."""
    folder = Path(folder)
    files = sorted(folder.glob("syscalls.*"))
    if not files:
        raise ValueError("TRACE_FILES_ABSENT")
    counters = Counter()
    per_kind = Counter()
    total_size = 0
    line_count = 0
    for trace in files:
        if not trace.is_file() or trace.is_symlink():
            raise ValueError("TRACE_FILE_UNSAFE")
        size = trace.stat().st_size
        total_size += size
        if total_size > MAX_FILE_BYTES:
            raise ValueError("TRACE_BUDGET_EXCEEDED")
        with trace.open("r", encoding="utf-8", errors="replace") as handle:
            for line in handle:
                line_count += 1
                if line_count > MAX_LINES:
                    raise ValueError("TRACE_LINE_BUDGET_EXCEEDED")
                m = FN.match(line)
                if not m:
                    continue
                name = m.group(1)
                r = RET.search(line)
                if name in ("mmap", "mmap2") and MAP_RET.search(line):
                    counters["mapping_calls"] += 1
                    details = FD.search(line)
                    kind = file_category(details.group(2)) if details else "unknown_fd"
                    per_kind[(kind, "mapping_calls")] += 1
                    continue
                # Unlike strace output payloads, numeric returns are safe to use.
                if r is None:
                    counters["unparsed_returns"] += 1
                    continue
                value = int(r.group(1))
                if value < 0:
                    counters["failed_calls"] += 1
                    continue
                counters["successful_calls"] += 1
                details = FD.search(line)
                kind = file_category(details.group(2)) if details else "unknown_fd"
                if name in ("read", "pread64", "readv"):
                    counters["read_calls"] += 1
                    counters["bytes_read"] += value
                    per_kind[(kind, "read_calls")] += 1
                elif name in ("write", "pwrite64", "writev"):
                    counters["write_calls"] += 1
                    counters["bytes_written"] += value
                    per_kind[(kind, "write_calls")] += 1
                elif name in ("mmap", "mmap2"):
                    counters["mapping_calls_numeric"] += 1
                elif name in ("openat", "openat2"):
                    counters["open_calls"] += 1
                    per_kind[(kind, "open_calls")] += 1
                elif name == "lseek":
                    counters["seek_calls"] += 1
    # Avoid falsely concluding no mmap use: strace prints hex address returns.
    status = "PASS" if counters["read_calls"] and counters["write_calls"] else "UNQUALIFIED"
    return {
        "schema": SCHEMA,
        "status": status,
        "evidence_class": "REAL_SYSCALL_METADATA_NOT_GAME_OBJECT_SEMANTICS",
        "trace_files": len(files),
        "lines_examined": line_count,
        "counters": {k: int(v) for k, v in sorted(counters.items())},
        "file_category_counts": {f"{kind}.{operation}": int(v)
                                 for (kind, operation), v in sorted(per_kind.items())},
        "limitations": [
            "FD path decoration is a best-effort Linux strace observation",
            "read/write offsets are not proven without separate pread/lseek/open-file-description state",
            "mmap page dirtiness and decoder semantics are not observed",
            "No user paths, memory data, raw traces or game assets are exported",
        ],
    }


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--trace-dir", required=True)
    p.add_argument("--output", required=True)
    opts = p.parse_args()
    try:
        result = parse_trace(opts.trace_dir)
    except (OSError, ValueError):
        result = {"schema": SCHEMA, "status": "UNQUALIFIED",
                  "evidence_class": "NO_VALID_IO_TRACE"}
    Path(opts.output).write_text(json.dumps(result, sort_keys=True, indent=2) + "\n", encoding="utf-8")
    return 0 if result["status"] == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())
