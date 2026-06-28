# Release Candidate Notes

## v0.9.8 Sidecar Extraction
- Date: 2026-06-28
- Branch: `main`
- Scope:
  - Extracted CV/OCR pipeline to `github.com/SemperSupra/desktop-ui-cv` (v0.1.0)
  - Extracted KV-Ground-8B server to `github.com/SemperSupra/kv-ground-server` (v0.1.0)
  - Extracted captioning server to `github.com/SemperSupra/ui-captioning` (v0.1.0)
  - CV sidecar now imports from `winebot_cv` package instead of loose files
  - CI/CD pipelines for all extracted repos
  - Dockerfiles support local wheel fallback for private repo builds
  - Full rebuild and E2E test: 14/14 endpoints verified passing
  - Fixed FastAPI binary upload crash (exception handler, #71)
  - Demo pipeline verified: AHK handler, notepad automation, state assertions
  - Xvfb 2D-only limitation documented
  - GPU proxy research documented
  - Credential scrub script (scripts/ci/check-credentials.sh) added
  - Structured JSON logging added to TrueNAS deployment scripts

## v0.9.7a Container Rebuild
- Date: 2026-05-04
- Branch: `main`
- Head commit: `8b93e66`
- Scope:
  - Rebuilt the release containers on top of the new Debian Trixie slim base image.
  - Published `ghcr.io/sempersupra/winebot-base:base-2026-05-04`.
  - Published `ghcr.io/sempersupra/winebot:v0.9.7a-rel`.
  - Published `ghcr.io/sempersupra/winebot:v0.9.7a-rel-runner`.
  - Updated GitHub Actions to Node 24-compatible pinned SHAs to clear Node.js 20 action warnings.
- Validation evidence:
  - Base Image workflow run `25330932840`: pass.
  - Release workflow run `25331384570`: pass.
  - Release smoke gate, Trivy scan, REL policy checks, cosign signing, and artifact verification: pass.
  - Local lint: pass.
  - Local containerized unit tests: `135 passed`.
- Published digests:
  - `v0.9.7a-rel`: `sha256:46bce5b85d6e0c0f2384f94a0d12b76970259bb073e939398479e5653c07d674`
  - `v0.9.7a-rel-runner`: `sha256:a41433596594966a3d99bf8884ff04fc0c945e31891adc44484049a9db2a642e`
- Known note:
  - No GitHub Release object was created in this session; the containers were published via manual `workflow_dispatch`.

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
