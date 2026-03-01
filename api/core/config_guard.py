import os
from typing import List
from api.core.constants import (
    MODE_HEADLESS,
    MODE_INTERACTIVE,
    VALID_RUNTIME_MODES,
    VALID_LIFECYCLE_MODES,
    VALID_CONTROL_POLICY_MODES,
    CONTROL_MODE_HUMAN_ONLY,
    CONTROL_MODE_AGENT_ONLY,
    CONTROL_MODE_HYBRID,
    LIFECYCLE_MODE_PERSISTENT,
)

PERFORMANCE_PROFILE_LOW_LATENCY = "low-latency"
PERFORMANCE_PROFILE_BALANCED = "balanced"
PERFORMANCE_PROFILE_MAX_QUALITY = "max-quality"
PERFORMANCE_PROFILE_DIAGNOSTIC = "diagnostic"
VALID_PERFORMANCE_PROFILES = {
    PERFORMANCE_PROFILE_LOW_LATENCY,
    PERFORMANCE_PROFILE_BALANCED,
    PERFORMANCE_PROFILE_MAX_QUALITY,
    PERFORMANCE_PROFILE_DIAGNOSTIC,
}

USE_CASE_PROFILE_CANONICAL = {
    "human-interactive": {
        "runtime_mode": MODE_INTERACTIVE,
        "instance_lifecycle_mode": "persistent",
        "session_lifecycle_mode": "persistent",
        "instance_control_mode": CONTROL_MODE_HUMAN_ONLY,
        "session_control_mode": CONTROL_MODE_HUMAN_ONLY,
        "default_performance_profile": PERFORMANCE_PROFILE_LOW_LATENCY,
        "allowed_performance_profiles": list(VALID_PERFORMANCE_PROFILES),
    },
    "human-exploratory": {
        "runtime_mode": MODE_INTERACTIVE,
        "instance_lifecycle_mode": "persistent",
        "session_lifecycle_mode": "persistent",
        "instance_control_mode": CONTROL_MODE_HUMAN_ONLY,
        "session_control_mode": CONTROL_MODE_HUMAN_ONLY,
        "default_performance_profile": PERFORMANCE_PROFILE_BALANCED,
        "allowed_performance_profiles": list(VALID_PERFORMANCE_PROFILES),
    },
    "human-debug-input": {
        "runtime_mode": MODE_INTERACTIVE,
        "instance_lifecycle_mode": "persistent",
        "session_lifecycle_mode": "persistent",
        "instance_control_mode": CONTROL_MODE_HUMAN_ONLY,
        "session_control_mode": CONTROL_MODE_HUMAN_ONLY,
        "default_performance_profile": PERFORMANCE_PROFILE_DIAGNOSTIC,
        "allowed_performance_profiles": [
            PERFORMANCE_PROFILE_DIAGNOSTIC,
            PERFORMANCE_PROFILE_BALANCED,
        ],
    },
    "agent-batch": {
        "runtime_mode": MODE_HEADLESS,
        "instance_lifecycle_mode": "persistent",
        "session_lifecycle_mode": "persistent",
        "instance_control_mode": CONTROL_MODE_AGENT_ONLY,
        "session_control_mode": CONTROL_MODE_AGENT_ONLY,
        "default_performance_profile": PERFORMANCE_PROFILE_BALANCED,
        "allowed_performance_profiles": [
            PERFORMANCE_PROFILE_BALANCED,
            PERFORMANCE_PROFILE_LOW_LATENCY,
            PERFORMANCE_PROFILE_DIAGNOSTIC,
        ],
    },
    "agent-timing-critical": {
        "runtime_mode": MODE_HEADLESS,
        "instance_lifecycle_mode": "persistent",
        "session_lifecycle_mode": "persistent",
        "instance_control_mode": CONTROL_MODE_AGENT_ONLY,
        "session_control_mode": CONTROL_MODE_AGENT_ONLY,
        "default_performance_profile": PERFORMANCE_PROFILE_LOW_LATENCY,
        "allowed_performance_profiles": [
            PERFORMANCE_PROFILE_LOW_LATENCY,
            PERFORMANCE_PROFILE_BALANCED,
        ],
    },
    "agent-forensic": {
        "runtime_mode": MODE_HEADLESS,
        "instance_lifecycle_mode": "persistent",
        "session_lifecycle_mode": "persistent",
        "instance_control_mode": CONTROL_MODE_AGENT_ONLY,
        "session_control_mode": CONTROL_MODE_AGENT_ONLY,
        "default_performance_profile": PERFORMANCE_PROFILE_DIAGNOSTIC,
        "allowed_performance_profiles": [
            PERFORMANCE_PROFILE_DIAGNOSTIC,
            PERFORMANCE_PROFILE_BALANCED,
        ],
    },
    "supervised-agent": {
        "runtime_mode": MODE_INTERACTIVE,
        "instance_lifecycle_mode": "persistent",
        "session_lifecycle_mode": "persistent",
        "instance_control_mode": CONTROL_MODE_HYBRID,
        "session_control_mode": CONTROL_MODE_HYBRID,
        "default_performance_profile": PERFORMANCE_PROFILE_BALANCED,
        "allowed_performance_profiles": list(VALID_PERFORMANCE_PROFILES),
    },
    "incident-supervision": {
        "runtime_mode": MODE_INTERACTIVE,
        "instance_lifecycle_mode": "persistent",
        "session_lifecycle_mode": "persistent",
        "instance_control_mode": CONTROL_MODE_HYBRID,
        "session_control_mode": CONTROL_MODE_HYBRID,
        "default_performance_profile": PERFORMANCE_PROFILE_DIAGNOSTIC,
        "allowed_performance_profiles": [
            PERFORMANCE_PROFILE_DIAGNOSTIC,
            PERFORMANCE_PROFILE_BALANCED,
        ],
    },
    "demo-training": {
        "runtime_mode": MODE_INTERACTIVE,
        "instance_lifecycle_mode": "persistent",
        "session_lifecycle_mode": "persistent",
        "instance_control_mode": CONTROL_MODE_HYBRID,
        "session_control_mode": CONTROL_MODE_HYBRID,
        "default_performance_profile": PERFORMANCE_PROFILE_MAX_QUALITY,
        "allowed_performance_profiles": [
            PERFORMANCE_PROFILE_MAX_QUALITY,
            PERFORMANCE_PROFILE_BALANCED,
        ],
    },
    "ci-gate": {
        "runtime_mode": MODE_HEADLESS,
        "instance_lifecycle_mode": "oneshot",
        "session_lifecycle_mode": "oneshot",
        "instance_control_mode": CONTROL_MODE_AGENT_ONLY,
        "session_control_mode": CONTROL_MODE_AGENT_ONLY,
        "default_performance_profile": PERFORMANCE_PROFILE_BALANCED,
        "allowed_performance_profiles": [PERFORMANCE_PROFILE_BALANCED],
    },
}

USE_CASE_PROFILE_ALIASES = {
    "human-desktop": "human-interactive",
    "assisted-desktop": "supervised-agent",
    "unattended-runner": "agent-batch",
    "ci-oneshot": "ci-gate",
    "support-session": "incident-supervision",
}


def resolve_use_case_profile(name: str) -> str:
    candidate = _normalize(name, "")
    if not candidate:
        return ""
    if candidate in USE_CASE_PROFILE_CANONICAL:
        return candidate
    return USE_CASE_PROFILE_ALIASES.get(candidate, "")


def _normalize(value: str, default: str) -> str:
    return (value or default).strip().lower()


def compute_effective_control_mode(instance_mode: str, session_mode: str) -> str:
    instance_mode = _normalize(instance_mode, CONTROL_MODE_HYBRID)
    session_mode = _normalize(session_mode, CONTROL_MODE_HYBRID)
    if instance_mode == CONTROL_MODE_HUMAN_ONLY or session_mode == CONTROL_MODE_HUMAN_ONLY:
        return CONTROL_MODE_HUMAN_ONLY
    if instance_mode == CONTROL_MODE_AGENT_ONLY or session_mode == CONTROL_MODE_AGENT_ONLY:
        return CONTROL_MODE_AGENT_ONLY
    return CONTROL_MODE_HYBRID


def validate_runtime_configuration(
    runtime_mode: str,
    instance_lifecycle_mode: str,
    session_lifecycle_mode: str,
    instance_control_mode: str,
    session_control_mode: str,
    build_intent: str = "",
    allow_headless_hybrid: bool = False,
    use_case_profile: str = "",
    performance_profile: str = "",
) -> List[str]:
    errors: List[str] = []

    runtime_mode = _normalize(runtime_mode, "headless")
    instance_lifecycle_mode = _normalize(instance_lifecycle_mode, LIFECYCLE_MODE_PERSISTENT)
    session_lifecycle_mode = _normalize(session_lifecycle_mode, LIFECYCLE_MODE_PERSISTENT)
    instance_control_mode = _normalize(instance_control_mode, CONTROL_MODE_HYBRID)
    session_control_mode = _normalize(session_control_mode, CONTROL_MODE_HYBRID)
    build_intent = _normalize(build_intent, "rel")
    requested_use_case = _normalize(use_case_profile, "")
    requested_performance = _normalize(performance_profile, "")

    if runtime_mode not in VALID_RUNTIME_MODES:
        errors.append(
            f"MODE must be one of {sorted(VALID_RUNTIME_MODES)} (got '{runtime_mode}')"
        )
    if instance_lifecycle_mode not in VALID_LIFECYCLE_MODES:
        errors.append(
            f"WINEBOT_INSTANCE_MODE must be one of {sorted(VALID_LIFECYCLE_MODES)} "
            f"(got '{instance_lifecycle_mode}')"
        )
    if session_lifecycle_mode not in VALID_LIFECYCLE_MODES:
        errors.append(
            f"WINEBOT_SESSION_MODE must be one of {sorted(VALID_LIFECYCLE_MODES)} "
            f"(got '{session_lifecycle_mode}')"
        )
    if instance_control_mode not in VALID_CONTROL_POLICY_MODES:
        errors.append(
            f"WINEBOT_INSTANCE_CONTROL_MODE must be one of {sorted(VALID_CONTROL_POLICY_MODES)} "
            f"(got '{instance_control_mode}')"
        )
    if session_control_mode not in VALID_CONTROL_POLICY_MODES:
        errors.append(
            f"WINEBOT_SESSION_CONTROL_MODE must be one of {sorted(VALID_CONTROL_POLICY_MODES)} "
            f"(got '{session_control_mode}')"
        )

    if requested_performance and requested_performance not in VALID_PERFORMANCE_PROFILES:
        errors.append(
            "WINEBOT_PERFORMANCE_PROFILE must be one of "
            f"{sorted(VALID_PERFORMANCE_PROFILES)} (got '{requested_performance}')"
        )

    if requested_use_case:
        canonical_use_case = resolve_use_case_profile(requested_use_case)
        if not canonical_use_case:
            known = sorted(set(USE_CASE_PROFILE_CANONICAL) | set(USE_CASE_PROFILE_ALIASES))
            errors.append(
                "WINEBOT_USE_CASE_PROFILE must be one of "
                f"{known} (got '{requested_use_case}')"
            )
        else:
            selected = USE_CASE_PROFILE_CANONICAL[canonical_use_case]
            expected_runtime = _normalize(selected["runtime_mode"], "")
            expected_instance_lifecycle = _normalize(
                selected["instance_lifecycle_mode"], ""
            )
            expected_session_lifecycle = _normalize(
                selected["session_lifecycle_mode"], ""
            )
            expected_instance_control = _normalize(
                selected["instance_control_mode"], ""
            )
            expected_session_control = _normalize(
                selected["session_control_mode"], ""
            )

            if runtime_mode != expected_runtime:
                errors.append(
                    f"WINEBOT_USE_CASE_PROFILE={canonical_use_case} requires MODE={expected_runtime} "
                    f"(got '{runtime_mode}')"
                )
            if instance_lifecycle_mode != expected_instance_lifecycle:
                errors.append(
                    "WINEBOT_USE_CASE_PROFILE="
                    f"{canonical_use_case} requires WINEBOT_INSTANCE_MODE={expected_instance_lifecycle} "
                    f"(got '{instance_lifecycle_mode}')"
                )
            if session_lifecycle_mode != expected_session_lifecycle:
                errors.append(
                    "WINEBOT_USE_CASE_PROFILE="
                    f"{canonical_use_case} requires WINEBOT_SESSION_MODE={expected_session_lifecycle} "
                    f"(got '{session_lifecycle_mode}')"
                )
            if instance_control_mode != expected_instance_control:
                errors.append(
                    "WINEBOT_USE_CASE_PROFILE="
                    f"{canonical_use_case} requires WINEBOT_INSTANCE_CONTROL_MODE={expected_instance_control} "
                    f"(got '{instance_control_mode}')"
                )
            if session_control_mode != expected_session_control:
                errors.append(
                    "WINEBOT_USE_CASE_PROFILE="
                    f"{canonical_use_case} requires WINEBOT_SESSION_CONTROL_MODE={expected_session_control} "
                    f"(got '{session_control_mode}')"
                )

            selected_perf = requested_performance or _normalize(
                selected["default_performance_profile"], ""
            )
            allowed_perf = {
                _normalize(item, "")
                for item in selected["allowed_performance_profiles"]
            }
            if selected_perf and selected_perf not in allowed_perf:
                errors.append(
                    "Invalid profile combination: "
                    f"use-case '{canonical_use_case}' does not allow performance '{selected_perf}'. "
                    f"Allowed: {sorted(allowed_perf)}"
                )

    effective_mode = compute_effective_control_mode(
        instance_control_mode, session_control_mode
    )

    if build_intent == "rel-runner" and runtime_mode == "interactive":
        errors.append(
            "BUILD_INTENT=rel-runner does not support MODE=interactive. "
            "Use MODE=headless."
        )

    if runtime_mode == MODE_HEADLESS and effective_mode == CONTROL_MODE_HUMAN_ONLY:
        errors.append(
            "Invalid combination: headless runtime cannot be human-only "
            "(no interactive human control surface)."
        )

    if runtime_mode == MODE_HEADLESS and effective_mode == CONTROL_MODE_HYBRID and not allow_headless_hybrid:
        errors.append(
            "Invalid combination: headless + hybrid is blocked by default. "
            "Set WINEBOT_ALLOW_HEADLESS_HYBRID=1 only if you intentionally accept "
            "reduced human takeover guarantees in headless mode."
        )

    return errors


def validate_current_environment(
    session_control_mode: str = "",
) -> List[str]:
    runtime_mode = os.getenv("MODE", MODE_HEADLESS)
    runtime_default_control = (
        CONTROL_MODE_AGENT_ONLY if runtime_mode.strip().lower() == MODE_HEADLESS else CONTROL_MODE_HYBRID
    )
    allow_headless_hybrid = (os.getenv("WINEBOT_ALLOW_HEADLESS_HYBRID") or "0").strip() in {
        "1",
        "true",
        "yes",
        "on",
    }
    return validate_runtime_configuration(
        runtime_mode=runtime_mode,
        instance_lifecycle_mode=os.getenv("WINEBOT_INSTANCE_MODE", LIFECYCLE_MODE_PERSISTENT),
        session_lifecycle_mode=os.getenv("WINEBOT_SESSION_MODE", LIFECYCLE_MODE_PERSISTENT),
        instance_control_mode=os.getenv(
            "WINEBOT_INSTANCE_CONTROL_MODE", runtime_default_control
        ),
        session_control_mode=(
            session_control_mode
            or os.getenv("WINEBOT_SESSION_CONTROL_MODE", runtime_default_control)
        ),
        build_intent=os.getenv("BUILD_INTENT", "rel"),
        allow_headless_hybrid=allow_headless_hybrid,
        use_case_profile=os.getenv("WINEBOT_USE_CASE_PROFILE", ""),
        performance_profile=os.getenv("WINEBOT_PERFORMANCE_PROFILE", ""),
    )
