# Testing

WineBot includes a smoke test to validate the display stack, Wine prefix, core API endpoints, and optional VNC/noVNC services.

## Capability Coverage Policy

Coverage is defined in:

`docs/test-capability-matrix.md`

CI verifies the matrix with:

`python3 scripts/ci/verify-capability-matrix.py`

Every new feature/capability set must add or reference automated tests/diagnostics in that matrix.

## Quick smoke test (headless)

`scripts/smoke-test.sh`

Checks performed (headless):

- Xvfb and openbox are running
- A window is present on `DISPLAY=:99`
- Screenshot capture works (timestamped file under `/tmp/`)
- The Wine prefix persists across containers
- API unit tests for `api/server.py` and host-view helper tests
- API integration checks for `/health` and `/health/*`
- API integration checks for `/inspect/window` (list-only)
- Screenshot metadata validation (PNG tEXt + JSON sidecar)

## Full smoke test

`scripts/smoke-test.sh --full`

Adds a Notepad automation round-trip. The test writes a file under
`/tmp/` for reliable write permissions in headless mode.

## Interactive checks

`scripts/smoke-test.sh --include-interactive`

Verifies `x11vnc` and noVNC/websockify are running and accepting connections.

## Debug checks

`scripts/smoke-test.sh --include-debug`

Runs a minimal winedbg command (`info proc`) in a one-off container.

`scripts/smoke-test.sh --include-debug-proxy`

Starts a one-off container under winedbg gdb proxy, verifies the target exe is running, and attaches via gdb to list threads.

Note: gdb may exit with code `137` in some container environments; the smoke test treats it as a pass when threads are reported.

## Cleanup

By default the smoke test leaves services running. To stop them:

`scripts/smoke-test.sh --cleanup`

For CI, prefer `--full --cleanup` and set `API_TOKEN` if security is enforced.

## UI/UX Quality Tests

The dashboard's visual integrity and behavioral correctness are verified using Playwright:

`pytest -v tests/e2e/test_ux_quality.py`

This suite enforces:
- **Functional Sync:** UI reflects backend process failures (e.g., stopping Xvfb triggers "Issues Detected").
- **Responsive Design:** Control panel correctly transitions to a mobile drawer on small viewports.
- **Feedback Loops:** Actions like taking a screenshot trigger visible Toast notifications.
- **Visual Baselines:** Captures masked snapshots for regression review.

## Local Developer Guardrails

To maintain high standards and fast-fail basic errors before they reach CI:

### Pre-commit Hooks
Install `pre-commit` and run `pre-commit install` to enable automated linting (`ruff`, `mypy`) and shell validation (`shellcheck`) before every commit.

### Watch Mode (Fast Iteration)
Use the dev-watch tool to automatically run tests as you save files:

`./scripts/bin/dev-watch.sh`

## CI Pipeline (GitHub Actions)

The CI workflow is split into two distinct stages:

1.  **Pre-flight (Fast):** Runs linting and unit tests on a native Python runner. Fails in < 1 minute if logic or style errors are detected.
2.  **Integration (Thorough):** Builds the `slim` Docker image and executes `smoke-test.sh`.

Official releases in `release.yml` additionally execute the full UI/UX quality suite and visual regression checks.

## Soak Diagnostics

Use the soak checker to watch for unbounded trace/recording growth and memory drift over time:

`scripts/diagnose-trace-soak.sh`

Tiered soak presets:

`scripts/diagnostics/soak-resource-bounds.sh pr`

`scripts/diagnostics/soak-resource-bounds.sh nightly`

`scripts/diagnostics/soak-resource-bounds.sh weekly`

Useful environment knobs:

- `DURATION_SECONDS` (default `600`)
- `INTERVAL_SECONDS` (default `15`)
- `MAX_LOG_MB` (default `512`)
- `MAX_SESSION_MB` (default `4096`)
- `MAX_PID1_RSS_MB` (default `2048`)
- `API_URL` and `API_TOKEN`

## Recording Lifecycle Validation

Use `scripts/recording-smoke-test.sh` to validate full recording lifecycle behavior and artifact correctness:

- API lifecycle transitions: `start`, `pause`, `resume`, `stop`, and idempotent repeats.
- Segment rollover behavior and part concatenation after pause/resume.
- Artifact set per segment:
  - `video_###.mkv`
  - `events_###.jsonl`
  - `events_###.vtt`
  - `events_###.ass`
  - `segment_###.json`
- Media/container checks via `ffprobe`:
  - video stream present
  - subtitle streams present
  - duration sane
  - `WINEBOT_SESSION_ID` metadata tag present and matched
- Timing/content alignment:
  - event timeline monotonic
  - subtitle cues monotonic
  - annotation marker presence in events + VTT + ASS
  - marker timing alignment between event log and subtitles

## Fault Injection and Recovery

Run deterministic recovery checks:

`scripts/diagnostics/diagnose-fault-injection.sh`

This validates operator-visible recovery after injected Openbox faults.

## Telemetry Contract Validation

Telemetry contract and rate-limit tests:

`pytest -q tests/test_telemetry_contract.py tests/test_command_substrate_telemetry.py tests/test_telemetry.py`

## Conformance and Standards Validation

WineBot includes explicit standards conformance suites for API, HTTP semantics, runtime policy, CLI contracts, and mDNS format:

`pytest -q tests/test_conformance_openapi.py tests/test_conformance_http_semantics.py tests/test_conformance_runtime_policy.py tests/test_conformance_cli_contract.py tests/test_conformance_mdns.py`

Reference:

`docs/conformance.md`

## Profile System Strategy

Profile coverage is enforced at four layers:

1. Matrix and admission unit tests:
- `tests/test_profile_matrix.py`
- `tests/test_config_guard.py`

2. CLI contract tests for startup/config profile UX:
- `tests/test_conformance_cli_contract.py`

3. Config-file admission validation:
- `scripts/internal/validate-winebot-config.py`

4. Container runtime integration via smoke/e2e:
- `scripts/bin/smoke-test.sh --full --include-interactive --cleanup --no-build`

Required CI profile subset:
- `human-interactive + low-latency`
- `supervised-agent + balanced`
- `agent-batch + balanced`
- `ci-gate + balanced`

Nightly/extended:
- full use-case/performance matrix in isolated container runs.

## Input Pipeline Conformance

Policy reference:

`policy/input-pipeline-conformance-policy.md`

Run the baseline input conformance bundle:

`pytest -q tests/test_policy.py tests/test_input_lifecycle_regression.py tests/e2e/test_input_quality.py tests/e2e/test_comprehensive_input.py tests/e2e/test_ux_keyboard_accessibility.py tests/test_ui_accessibility.py`

Recommended stress and diagnostics:

- `scripts/diagnostics/diagnose-input-trace.sh`
- `tests/stress_input.sh`

### Input Conformance Strategy (Tiered)

- Tier 0 (Schema/Unit): input events are parsed and normalized correctly, including button/modifier fields.
- Tier 1 (Policy/Arbitration): human input revokes agent control; agent actions require explicit grant.
- Tier 2 (Pipeline Integration): client, X11, and optional Windows traces align for clicks, drags, wheel, and keyboard paths.
- Tier 3 (E2E UX): noVNC canvas interactions reach focused Wine apps under both 1:1 and scaled viewport.
- Tier 4 (Occlusion): dashboard overlays do not swallow input outside explicit control regions.
- Tier 5 (Soak/Stress): prolonged sessions do not degrade delivery, drift coordinates, or leave stuck input state.

## Invariant Validation

Lifecycle/control/config invariants are codified and tested:

`pytest -q tests/test_invariants.py tests/test_lifecycle_hardened.py tests/test_config_guard.py tests/test_config_strict_validation.py`

Runtime invariant status is available at:

`GET /health/invariants`

## UX and Accessibility

In addition to existing UI/UX suites, keyboard navigation baseline is validated with:

`pytest -q tests/e2e/test_ux_keyboard_accessibility.py`

## Release Trust Pack

Generate a machine-readable evidence bundle:

`scripts/ci/generate-trust-pack.sh artifacts/trust-pack`
