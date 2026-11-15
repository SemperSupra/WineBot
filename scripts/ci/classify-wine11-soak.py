#!/usr/bin/env python3
"""Fail-closed, fixed-domain public classifier for isolated Wine 11 long soak."""
from __future__ import annotations

import re
import sys
from pathlib import Path

MAX_BYTES = 1024 * 1024
STAGE_NAMES = {
    "health_request",
    "system_health_request",
    "recording_health_request",
    "recording_metadata_invalid",
    "log_usage_unavailable",
    "session_usage_unavailable",
}
LIMIT_PREFIXES = {
    "[soak] FAIL: log size ": "log_limit",
    "[soak] FAIL: session size ": "session_limit",
    "[soak] FAIL: pid1 VmRSS ": "memory_limit",
}


def classify(text: str) -> str:
    for line in text.splitlines():
        m = re.fullmatch(r"\[soak\] FAIL stage=([a-z_]+)", line.strip())
        if m and m.group(1) in STAGE_NAMES:
            return m.group(1)
        for prefix, stage in LIMIT_PREFIXES.items():
            if line.startswith(prefix):
                return stage
        if line.startswith("[soak] INVALID_CONFIG "):
            return "invalid_config"
    return "unknown"


def main() -> int:
    try:
        path = Path(sys.argv[1])
        if len(sys.argv) != 2 or path.is_symlink() or not path.is_file():
            raise ValueError("invalid log")
        if path.stat().st_size > MAX_BYTES:
            raise ValueError("oversized log")
        stage = classify(path.read_text(encoding="utf-8"))
    except (IndexError, ValueError, UnicodeError, OSError):
        stage = "unknown"
    print(f"WINE11_SOAK_DIAGNOSTIC stage={stage}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
