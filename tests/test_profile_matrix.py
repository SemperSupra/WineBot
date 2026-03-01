import pytest

from api.core.config_guard import (
    USE_CASE_PROFILE_CANONICAL,
    validate_runtime_configuration,
)


@pytest.mark.parametrize(
    "profile,params,expected_ok",
    [
        (
            "human-interactive",
            dict(
                runtime_mode="interactive",
                instance_lifecycle_mode="persistent",
                session_lifecycle_mode="persistent",
                instance_control_mode="human-only",
                session_control_mode="human-only",
                build_intent="rel",
                allow_headless_hybrid=False,
                use_case_profile="human-interactive",
                performance_profile="low-latency",
            ),
            True,
        ),
        (
            "human-exploratory",
            dict(
                runtime_mode="interactive",
                instance_lifecycle_mode="persistent",
                session_lifecycle_mode="persistent",
                instance_control_mode="human-only",
                session_control_mode="human-only",
                build_intent="rel",
                allow_headless_hybrid=False,
                use_case_profile="human-exploratory",
                performance_profile="balanced",
            ),
            True,
        ),
        (
            "human-debug-input",
            dict(
                runtime_mode="interactive",
                instance_lifecycle_mode="persistent",
                session_lifecycle_mode="persistent",
                instance_control_mode="human-only",
                session_control_mode="human-only",
                build_intent="rel",
                allow_headless_hybrid=False,
                use_case_profile="human-debug-input",
                performance_profile="diagnostic",
            ),
            True,
        ),
        (
            "agent-batch",
            dict(
                runtime_mode="headless",
                instance_lifecycle_mode="persistent",
                session_lifecycle_mode="persistent",
                instance_control_mode="agent-only",
                session_control_mode="agent-only",
                build_intent="rel",
                allow_headless_hybrid=False,
                use_case_profile="agent-batch",
                performance_profile="balanced",
            ),
            True,
        ),
        (
            "agent-timing-critical",
            dict(
                runtime_mode="headless",
                instance_lifecycle_mode="persistent",
                session_lifecycle_mode="persistent",
                instance_control_mode="agent-only",
                session_control_mode="agent-only",
                build_intent="rel",
                allow_headless_hybrid=False,
                use_case_profile="agent-timing-critical",
                performance_profile="low-latency",
            ),
            True,
        ),
        (
            "agent-forensic",
            dict(
                runtime_mode="headless",
                instance_lifecycle_mode="persistent",
                session_lifecycle_mode="persistent",
                instance_control_mode="agent-only",
                session_control_mode="agent-only",
                build_intent="rel",
                allow_headless_hybrid=False,
                use_case_profile="agent-forensic",
                performance_profile="diagnostic",
            ),
            True,
        ),
        (
            "supervised-agent",
            dict(
                runtime_mode="interactive",
                instance_lifecycle_mode="persistent",
                session_lifecycle_mode="persistent",
                instance_control_mode="hybrid",
                session_control_mode="hybrid",
                build_intent="rel",
                allow_headless_hybrid=False,
                use_case_profile="supervised-agent",
                performance_profile="balanced",
            ),
            True,
        ),
        (
            "incident-supervision",
            dict(
                runtime_mode="interactive",
                instance_lifecycle_mode="persistent",
                session_lifecycle_mode="persistent",
                instance_control_mode="hybrid",
                session_control_mode="hybrid",
                build_intent="rel",
                allow_headless_hybrid=False,
                use_case_profile="incident-supervision",
                performance_profile="diagnostic",
            ),
            True,
        ),
        (
            "demo-training",
            dict(
                runtime_mode="interactive",
                instance_lifecycle_mode="persistent",
                session_lifecycle_mode="persistent",
                instance_control_mode="hybrid",
                session_control_mode="hybrid",
                build_intent="rel",
                allow_headless_hybrid=False,
                use_case_profile="demo-training",
                performance_profile="max-quality",
            ),
            True,
        ),
        (
            "ci-gate",
            dict(
                runtime_mode="headless",
                instance_lifecycle_mode="oneshot",
                session_lifecycle_mode="oneshot",
                instance_control_mode="agent-only",
                session_control_mode="agent-only",
                build_intent="rel",
                allow_headless_hybrid=False,
                use_case_profile="ci-gate",
                performance_profile="balanced",
            ),
            True,
        ),
        (
            "legacy-alias-human-desktop",
            dict(
                runtime_mode="interactive",
                instance_lifecycle_mode="persistent",
                session_lifecycle_mode="persistent",
                instance_control_mode="human-only",
                session_control_mode="human-only",
                build_intent="rel",
                allow_headless_hybrid=False,
                use_case_profile="human-desktop",
                performance_profile="low-latency",
            ),
            True,
        ),
        (
            "blocked-invalid-performance-for-use-case",
            dict(
                runtime_mode="headless",
                instance_lifecycle_mode="oneshot",
                session_lifecycle_mode="oneshot",
                instance_control_mode="agent-only",
                session_control_mode="agent-only",
                build_intent="rel",
                allow_headless_hybrid=False,
                use_case_profile="ci-gate",
                performance_profile="diagnostic",
            ),
            False,
        ),
        (
            "blocked-use-case-runtime-mismatch",
            dict(
                runtime_mode="headless",
                instance_lifecycle_mode="persistent",
                session_lifecycle_mode="persistent",
                instance_control_mode="hybrid",
                session_control_mode="hybrid",
                build_intent="rel",
                allow_headless_hybrid=False,
                use_case_profile="supervised-agent",
                performance_profile="balanced",
            ),
            False,
        ),
        (
            "blocked-headless-human-only",
            dict(
                runtime_mode="headless",
                instance_lifecycle_mode="persistent",
                session_lifecycle_mode="persistent",
                instance_control_mode="human-only",
                session_control_mode="human-only",
                build_intent="rel",
                allow_headless_hybrid=False,
                use_case_profile="",
                performance_profile="",
            ),
            False,
        ),
        (
            "blocked-rel-runner-interactive",
            dict(
                runtime_mode="interactive",
                instance_lifecycle_mode="persistent",
                session_lifecycle_mode="persistent",
                instance_control_mode="agent-only",
                session_control_mode="agent-only",
                build_intent="rel-runner",
                allow_headless_hybrid=False,
                use_case_profile="",
                performance_profile="",
            ),
            False,
        ),
    ],
)
def test_profile_matrix(profile, params, expected_ok):
    errors = validate_runtime_configuration(**params)
    assert (len(errors) == 0) is expected_ok, f"{profile}: {errors}"


def _base_params_for_use_case(use_case: str, performance: str) -> dict:
    profile = USE_CASE_PROFILE_CANONICAL[use_case]
    return dict(
        runtime_mode=profile["runtime_mode"],
        instance_lifecycle_mode=profile["instance_lifecycle_mode"],
        session_lifecycle_mode=profile["session_lifecycle_mode"],
        instance_control_mode=profile["instance_control_mode"],
        session_control_mode=profile["session_control_mode"],
        build_intent="rel",
        allow_headless_hybrid=False,
        use_case_profile=use_case,
        performance_profile=performance,
    )


def test_all_use_case_default_performance_combinations_are_allowed():
    for use_case, profile in USE_CASE_PROFILE_CANONICAL.items():
        params = _base_params_for_use_case(
            use_case, profile["default_performance_profile"]
        )
        errors = validate_runtime_configuration(**params)
        assert not errors, f"{use_case} default failed: {errors}"


def test_all_declared_allowed_performance_combinations_are_allowed():
    for use_case, profile in USE_CASE_PROFILE_CANONICAL.items():
        for performance in profile["allowed_performance_profiles"]:
            params = _base_params_for_use_case(use_case, performance)
            errors = validate_runtime_configuration(**params)
            assert not errors, f"{use_case}+{performance} failed: {errors}"
