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
            if code in {"failed_trace_log_path", "failed_trace_script_path"}:
                for cause in ("missing_binary", "timeout", "nonzero", "invalid_output"):
                    if "WINEPATH_DIAGNOSTIC stage=" + cause in raw:
                        print("STARTUP_DIAGNOSTIC winepath=" + cause)
                        break
                # Only fixed classifications from the failed trace-path probe;
                # never reflect diagnostic text from untrusted service logs.
                for status in ("present", "unverified"):
                    if "WIN_TRACE_PROBE root_mapping=" + status in raw:
                        print("STARTUP_DIAGNOSTIC root_mapping=" + status)
                        break
                for status in ("pass", "fail"):
                    if "WIN_TRACE_PROBE control_file=" + status in raw:
                        print("STARTUP_DIAGNOSTIC control_file=" + status)
                        break
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
