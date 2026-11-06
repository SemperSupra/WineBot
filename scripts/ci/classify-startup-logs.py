#!/usr/bin/env python3
"""Emit only fixed startup diagnostic codes; never echo untrusted service log text."""

from __future__ import annotations

import sys

SPECIFIC_STAGES = (
    ("services/trace-log-path", "failed_trace_log_path"),
    ("services/trace-script-path", "failed_trace_script_path"),
    ("services/trace-launch", "failed_trace_launch"),
    ("services/api-token", "failed_api_token"),
    ("services/native-input-trace", "failed_native_trace"),
    ("services/recording", "failed_recorder"),
    ("services/api", "failed_api"),
    ("services/supervisor", "failed_supervisor"),
    ("services/input-trace", "failed_input_trace"),
    ("services/complete", "failed_services_complete"),
    ("services", "failed_services"),
    ("configuration", "failed_configuration"),
    ("infrastructure", "failed_infrastructure"),
    ("wine", "failed_wine"),
)


def main() -> int:
    # Compose logs may contain credentials or user-facing window titles.
    # Read job-locally; print ONLY enumerated codes, never raw text.
    raw = sys.stdin.read(262144)
    for marker, code in SPECIFIC_STAGES:
        if "WINEBOT_STARTUP_ERROR stage=" + marker + " " in raw:
            print("STARTUP_DIAGNOSTIC stage=" + code)
            return 0
    for marker, code in (
        ("Pass 4: Services", "reached_services"),
        ("Pass 3: Wine Environment", "reached_wine"),
        ("Pass 2: Infrastructure", "reached_infrastructure"),
        ("Xvfb failed to start", "xvfb_failure"),
        ("Configuration admission rejected", "configuration_rejected"),
    ):
        if marker in raw:
            print("STARTUP_DIAGNOSTIC stage=" + code)
            return 0
    print("STARTUP_DIAGNOSTIC stage=unknown")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
