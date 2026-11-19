#!/usr/bin/env python3
"""Project bounded, allowlisted init-failure categories without exposing raw logs.

Never include raw container stdout/stderr, paths, environment variables,
container IDs, host details or credential material in public CI output.
"""
import re
import sys

STAGES = {
    "app-seed": {
        "unavailable", "invalid_mount", "invalid_manifest", "version_mismatch",
        "unexpected_files", "unexpected_symlink", "integrity_mismatch",
        "incomplete_volume", "concurrent_init", "permissions_failed", "copy_failed", "stamp_failed",
        "existing_verified", "created_verified",
    },
    "state-init": {
        "invalid_identity", "mount_unavailable", "permissions_failed",
        "ownership_failed", "ready",
    },
}
PREFIX = {
    "app-seed": "APP_LAYER_DIAGNOSTIC",
    "state-init": "STATE_LAYER_DIAGNOSTIC",
}


def classify(service: str, lines) -> str:
    if service not in STAGES:
        raise ValueError("unrecognized service")
    match = re.compile(rf"^{PREFIX[service]} stage=([a-z_]+)$")
    found = ""
    any_log_lines = False
    for line in lines:
        any_log_lines = True
        if len(line) > 256:
            continue
        category = match.fullmatch(line.rstrip("\r\n"))
        if category and category.group(1) in STAGES[service]:
            found = category.group(1)
    if not found:
        found = "unclassified_nonempty" if any_log_lines else "unclassified_empty"
    return f"WINE11_LAYER_HIL service={service} cause={found}"


def main() -> int:
    if len(sys.argv) != 2 or sys.argv[1] not in STAGES:
        print("WINE11_LAYER_HIL cause=invalid_classifier_input", file=sys.stderr)
        return 2
    print(classify(sys.argv[1], sys.stdin))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
