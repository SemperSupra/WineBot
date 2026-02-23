#!/usr/bin/env bash
set -euo pipefail
echo "--- Running Unit Tests ---"
pytest \
  tests/test_api.py \
  tests/test_api_contracts.py \
  tests/test_input_validation.py \
  tests/test_input_lifecycle_regression.py \
  tests/test_lifecycle_hardened.py \
  tests/test_profile_matrix.py \
  tests/test_policy.py \
  tests/test_process_timeout.py \
  tests/test_recorder_unit.py \
  tests/test_telemetry.py \
  tests/test_telemetry_contract.py \
  tests/test_command_substrate_telemetry.py \
  tests/test_monitor_inactivity.py \
  tests/test_diag_bundle.py \
  tests/test_auto_view.py \
  tests/test_ui_dashboard.py \
  tests/test_ui_accessibility.py
