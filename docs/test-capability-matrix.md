# Test Capability Matrix

This matrix defines minimum automated coverage for each major WineBot capability set.

Rules:
- Every capability set must map to at least one automated test or diagnostic.
- New feature/capability additions must update this file in the same PR.
- CI validates that referenced test paths/scripts exist.

| Capability Set | Required Coverage | Test/Diagnostic References |
| :--- | :--- | :--- |
| Runtime foundation health | API and desktop stack ready/healthy | `scripts/bin/smoke-test.sh`, `scripts/diagnostics/diagnose-master.sh` |
| Session lifecycle correctness | suspend/resume/shutdown idempotent and policy-safe | `tests/test_lifecycle_hardened.py`, `tests/test_api_contracts.py` |
| Control policy and grants | human/agent/hybrid mode correctness | `tests/test_config_guard.py`, `tests/test_profile_matrix.py` |
| Input APIs and validation | input boundaries and safety invariants | `tests/test_input_validation.py`, `tests/test_input_lifecycle_regression.py` |
| Input tracing layers | x11/windows/client/network trace operability | `scripts/diagnostics/diagnose-input-trace.sh`, `tests/e2e/test_input_quality.py` |
| Automation execution | app launch/script execution behavior | `tests/e2e/test_comprehensive_input.py`, `tests/test_api.py` |
| Recording lifecycle + artifacts | start/pause/resume/stop and artifact integrity | `tests/test_recorder_unit.py`, `scripts/internal/recording-smoke-test.sh` |
| Telemetry correctness | schema, sampling, rate limits, attribution | `tests/test_telemetry.py`, `tests/test_command_substrate_telemetry.py`, `tests/test_telemetry_contract.py` |
| UI/UX behavior | dashboard state sync, responsive UX, error surfaces | `tests/e2e/test_ux_quality.py`, `tests/e2e/test_zz_dashboard_ux_compliance.py`, `tests/test_ui_dashboard.py` |
| UI accessibility baseline | structural accessibility and keyboard affordances | `tests/test_ui_accessibility.py`, `tests/e2e/test_ux_keyboard_accessibility.py` |
| Fault recovery | process fault injection and recovery expectations | `scripts/diagnostics/diagnose-master.sh`, `scripts/diagnostics/diagnose-fault-injection.sh` |
| Resource bounds and soak | long-run memory/log/session growth constraints | `scripts/diagnostics/diagnose-trace-soak.sh`, `scripts/diagnostics/soak-resource-bounds.sh` |
| Release trust evidence | machine-readable test and diagnostics summary | `scripts/ci/generate-trust-pack.sh` |
