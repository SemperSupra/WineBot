#!/usr/bin/env bash
set -euo pipefail
echo "--- Running Unit Tests ---"
pytest \
  tests/test_api.py \
  tests/test_api_contracts.py \
  tests/test_conformance_openapi.py \
  tests/test_conformance_http_semantics.py \
  tests/test_conformance_runtime_policy.py \
  tests/test_conformance_cli_contract.py \
  tests/test_conformance_mdns.py \
  tests/test_config_strict_validation.py \
  tests/test_invariants.py \
  tests/test_input_validation.py \
  tests/test_input_keyboard_conformance.py \
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

echo ""
echo "--- CV Analysis Gate ---"
# Run CV batch analysis on demo output if available
CV_BATCH="/work/scripts/diagnostics/cv-batch-analyze.py"
DEMO_OUTPUT="/work/demo/output"
if [ -f "$CV_BATCH" ] && [ -d "$DEMO_OUTPUT" ]; then
  echo "  Running CV batch analysis on demo/output/ ..."
  if python3 "$CV_BATCH" --input "$DEMO_OUTPUT" --exit-on-warnings 2>&1; then
    echo "  CV Analysis Gate: PASSED (no warnings)"
  else
    echo "  CV Analysis Gate: WARNINGS FOUND — check demo output"
    # Non-fatal for now; upgrade to hard failure when demos stabilize
  fi
else
  echo "  CV analysis skipped ($CV_BATCH not found or $DEMO_OUTPUT not found)"
fi
