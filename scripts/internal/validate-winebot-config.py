#!/usr/bin/env python3
import argparse
import json
import os
import re
import sys
from typing import Dict, List

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
REPO_ROOT = os.path.abspath(os.path.join(SCRIPT_DIR, "..", ".."))
if REPO_ROOT not in sys.path:
    sys.path.insert(0, REPO_ROOT)

EXPORT_RE = re.compile(r"^\s*(?:export\s+)?([A-Za-z_][A-Za-z0-9_]*)=(.*)\s*$")


def _strip_shell_quotes(raw: str) -> str:
    value = raw.strip()
    if len(value) >= 2 and value[0] == value[-1] and value[0] in {"'", '"'}:
        return value[1:-1]
    return value


def parse_env_file(path: str) -> Dict[str, str]:
    out: Dict[str, str] = {}
    if not path or not os.path.exists(path):
        return out
    with open(path, "r", encoding="utf-8") as handle:
        for line in handle:
            line = line.strip()
            if not line or line.startswith("#"):
                continue
            m = EXPORT_RE.match(line)
            if not m:
                continue
            key, raw = m.group(1), m.group(2)
            out[key] = _strip_shell_quotes(raw)
    return out


def truthy(value: str) -> bool:
    return (value or "").strip().lower() in {"1", "true", "yes", "on"}


def main() -> int:
    from api.core.config_guard import (
        compute_effective_control_mode,
        validate_runtime_configuration,
    )

    parser = argparse.ArgumentParser(description="Validate WineBot runtime configuration")
    parser.add_argument(
        "--env-file",
        action="append",
        default=[],
        help="Optional env file(s) with export KEY=VALUE entries",
    )
    parser.add_argument(
        "--json",
        action="store_true",
        help="Print JSON result",
    )
    args = parser.parse_args()

    merged = dict(os.environ)
    for env_file in args.env_file:
        merged.update(parse_env_file(env_file))

    runtime_mode = merged.get("MODE", "headless")
    runtime_default_control = (
        "agent-only" if (runtime_mode or "").strip().lower() == "headless" else "hybrid"
    )
    instance_lifecycle_mode = merged.get("WINEBOT_INSTANCE_MODE", "persistent")
    session_lifecycle_mode = merged.get("WINEBOT_SESSION_MODE", "persistent")
    instance_control_mode = merged.get(
        "WINEBOT_INSTANCE_CONTROL_MODE", runtime_default_control
    )
    session_control_mode = merged.get(
        "WINEBOT_SESSION_CONTROL_MODE", runtime_default_control
    )
    allow_headless_hybrid = truthy(merged.get("WINEBOT_ALLOW_HEADLESS_HYBRID", "0"))
    build_intent = merged.get("BUILD_INTENT", "rel")
    use_case_profile = merged.get("WINEBOT_USE_CASE_PROFILE", "")
    performance_profile = merged.get("WINEBOT_PERFORMANCE_PROFILE", "")

    errors: List[str] = validate_runtime_configuration(
        runtime_mode=runtime_mode,
        instance_lifecycle_mode=instance_lifecycle_mode,
        session_lifecycle_mode=session_lifecycle_mode,
        instance_control_mode=instance_control_mode,
        session_control_mode=session_control_mode,
        build_intent=build_intent,
        allow_headless_hybrid=allow_headless_hybrid,
        use_case_profile=use_case_profile,
        performance_profile=performance_profile,
    )
    effective_mode = compute_effective_control_mode(
        instance_control_mode, session_control_mode
    )

    result = {
        "ok": len(errors) == 0,
        "runtime_mode": runtime_mode,
        "instance_mode": instance_lifecycle_mode,
        "session_mode": session_lifecycle_mode,
        "instance_control_mode": instance_control_mode,
        "session_control_mode": session_control_mode,
        "effective_control_mode": effective_mode,
        "build_intent": build_intent,
        "allow_headless_hybrid": allow_headless_hybrid,
        "use_case_profile": use_case_profile,
        "performance_profile": performance_profile,
        "errors": errors,
    }

    if args.json:
        print(json.dumps(result))
    else:
        if result["ok"]:
            print("WineBot config validation: OK")
            print(
                "resolved "
                f"runtime={runtime_mode} "
                f"instance={instance_lifecycle_mode} "
                f"session={session_lifecycle_mode} "
                f"instance_control={instance_control_mode} "
                f"session_control={session_control_mode} "
                f"effective_control={effective_mode} "
                f"use_case_profile={use_case_profile or '<unset>'} "
                f"performance_profile={performance_profile or '<unset>'}"
            )
        else:
            print("WineBot config validation: FAILED")
            for err in errors:
                print(f"- {err}")
    return 0 if result["ok"] else 2


if __name__ == "__main__":
    raise SystemExit(main())
