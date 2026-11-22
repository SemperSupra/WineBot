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
    # Fixed, path-free progress checkpoints, never raw stdout or secrets.
    # Check latest possible phase first; no log contents are ever forwarded.
    for marker, code in (
        ("WINEBOT_WRITER_ADMISSION=SESSION_ROOT_UNAVAILABLE", "unadmitted_root_rejected"),
        ("WINEBOT_INFRA_CHECKPOINT=entropy_failed", "infra_entropy_failed"),
        ("Pass 4: Services", "reached_services"),
        ("Pass 3: Wine Environment", "reached_wine"),
        ("WINEBOT_INFRA_CHECKPOINT=completed", "infra_completed"),
        ("WINEBOT_INFRA_CHECKPOINT=xvfb_ready", "infra_xvfb_ready"),
        ("WINEBOT_INFRA_CHECKPOINT=session_dirs_ready", "infra_session_ready"),
        ("WINEBOT_INFRA_CHECKPOINT=ephemeral_pointer_written", "infra_pointer_written"),
        ("WINEBOT_INFRA_CHECKPOINT=session_identity_ready", "infra_identity_ready"),
        ("WINEBOT_INFRA_CHECKPOINT=begin", "infra_begin"),
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
