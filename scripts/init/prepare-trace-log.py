#!/usr/bin/env python3
"""Prepare an existing-or-new private trace log, without following symlinks.

A Wine 11 path conversion can fail for an absent final path component.
Never disclose the source path or filesystem error on a public runner.
"""
from __future__ import annotations

import os
import stat
import sys


def prepare(path: str) -> bool:
    flags = os.O_WRONLY | os.O_CREAT | os.O_APPEND | os.O_NONBLOCK | os.O_CLOEXEC
    flags |= os.O_NOFOLLOW
    try:
        fd = os.open(path, flags, 0o600)
    except OSError:
        return False
    try:
        if not stat.S_ISREG(os.fstat(fd).st_mode):
            return False
        # Preserve existing bytes, require private access.
        os.fchmod(fd, 0o600)
        return True
    except OSError:
        return False
    finally:
        os.close(fd)


def main() -> int:
    if len(sys.argv) != 2 or not sys.argv[1]:
        print("WIN_TRACE_DIAGNOSTIC stage=invalid_input", file=sys.stderr)
        return 2
    if not prepare(sys.argv[1]):
        print("WIN_TRACE_DIAGNOSTIC stage=unsafe_log_target", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
