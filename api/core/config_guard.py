import os
from typing import List
from api.core.constants import (
    MODE_HEADLESS,
    VALID_RUNTIME_MODES,
    VALID_LIFECYCLE_MODES,
    VALID_CONTROL_POLICY_MODES,
    CONTROL_MODE_HUMAN_ONLY,
    CONTROL_MODE_AGENT_ONLY,
    CONTROL_MODE_HYBRID,
    LIFECYCLE_MODE_PERSISTENT,
)


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
) -> List[str]:
    errors: List[str] = []

    runtime_mode = _normalize(runtime_mode, "headless")
    instance_lifecycle_mode = _normalize(instance_lifecycle_mode, LIFECYCLE_MODE_PERSISTENT)
    session_lifecycle_mode = _normalize(session_lifecycle_mode, LIFECYCLE_MODE_PERSISTENT)
    instance_control_mode = _normalize(instance_control_mode, CONTROL_MODE_HYBRID)
    session_control_mode = _normalize(session_control_mode, CONTROL_MODE_HYBRID)
    build_intent = _normalize(build_intent, "rel")

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
    )
