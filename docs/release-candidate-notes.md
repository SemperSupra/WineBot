# Release Candidate Notes

## Candidate
- Date: 2026-03-01
- Branch: `feat/recording-contract-hardening`
- Head commit: `c5eabd6`
- PR: `#37` (`https://github.com/SemperSupra/WineBot/pull/37`)

## Scope
- Hardened recording contract, response models, and CLI contract validation.
- Expanded conformance/testing coverage (API, HTTP semantics, runtime policy, CLI, mDNS).
- Added input pipeline conformance policy and occlusion E2E tests.
- Stabilized smoke/E2E readiness around API startup and token/health races.
- Hardened diagnostics and trace collection for X11/client/windows layers.
- Improved runtime robustness for screenshot and Notepad-based smoke actions.

## Validation Evidence
- Full local gate:
  - `./scripts/bin/smoke-test.sh --full --include-interactive --cleanup --no-build`
  - Unit tests: `120 passed`
  - E2E tests: `14 passed`
  - Diagnostics phases passed: `health`, `smoke`, `cv`, `trace`, `recovery`
- Focused sanity:
  - Openbox menu validation: `Openbox menu validation OK (14 commands)`
  - Targeted E2E input checks:
    - `/work/tests/e2e/test_comprehensive_input.py::test_comprehensive_input`
    - `/work/tests/e2e/test_input_occlusion_conformance.py`
    - Result: `3 passed`
- PR checks:
  - `Pre-flight (Lint & Unit)`: pass
  - `Integration (Smoke Test)`: pass

## Known Notes
- `scripts/health-check.sh` deprecation notice appears during diagnostics runs; execution remains successful.
- noVNC secure-context warning appears in browser console during containerized test execution; functional checks pass.
