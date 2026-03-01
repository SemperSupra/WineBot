from api.core.config_guard import (
    compute_effective_control_mode,
    validate_runtime_configuration,
)


def test_effective_control_mode_precedence():
    assert compute_effective_control_mode("human-only", "agent-only") == "human-only"
    assert compute_effective_control_mode("hybrid", "agent-only") == "agent-only"
    assert compute_effective_control_mode("hybrid", "hybrid") == "hybrid"


def test_headless_human_only_blocked():
    errors = validate_runtime_configuration(
        runtime_mode="headless",
        instance_lifecycle_mode="persistent",
        session_lifecycle_mode="persistent",
        instance_control_mode="human-only",
        session_control_mode="human-only",
        build_intent="rel",
        allow_headless_hybrid=False,
    )
    assert any("headless runtime cannot be human-only" in e for e in errors)


def test_headless_hybrid_requires_explicit_override():
    blocked = validate_runtime_configuration(
        runtime_mode="headless",
        instance_lifecycle_mode="persistent",
        session_lifecycle_mode="persistent",
        instance_control_mode="hybrid",
        session_control_mode="hybrid",
        build_intent="rel",
        allow_headless_hybrid=False,
    )
    assert any("headless + hybrid is blocked" in e for e in blocked)

    allowed = validate_runtime_configuration(
        runtime_mode="headless",
        instance_lifecycle_mode="persistent",
        session_lifecycle_mode="persistent",
        instance_control_mode="hybrid",
        session_control_mode="hybrid",
        build_intent="rel",
        allow_headless_hybrid=True,
    )
    assert not allowed


def test_rel_runner_cannot_be_interactive():
    errors = validate_runtime_configuration(
        runtime_mode="interactive",
        instance_lifecycle_mode="persistent",
        session_lifecycle_mode="persistent",
        instance_control_mode="hybrid",
        session_control_mode="hybrid",
        build_intent="rel-runner",
        allow_headless_hybrid=False,
    )
    assert any("BUILD_INTENT=rel-runner does not support MODE=interactive" in e for e in errors)


def test_use_case_alias_is_accepted():
    errors = validate_runtime_configuration(
        runtime_mode="interactive",
        instance_lifecycle_mode="persistent",
        session_lifecycle_mode="persistent",
        instance_control_mode="human-only",
        session_control_mode="human-only",
        build_intent="rel",
        allow_headless_hybrid=False,
        use_case_profile="human-desktop",
        performance_profile="low-latency",
    )
    assert not errors


def test_use_case_performance_combo_is_validated():
    errors = validate_runtime_configuration(
        runtime_mode="headless",
        instance_lifecycle_mode="oneshot",
        session_lifecycle_mode="oneshot",
        instance_control_mode="agent-only",
        session_control_mode="agent-only",
        build_intent="rel",
        allow_headless_hybrid=False,
        use_case_profile="ci-gate",
        performance_profile="diagnostic",
    )
    assert any("does not allow performance" in e for e in errors)
