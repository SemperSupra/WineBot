# Status

## Current State
- **Version:** v0.9.7a release containers published.
- **Status:** **Release containers rebuilt and verified on GitHub Actions.**
- **Handover Point:** `main` is synchronized with `origin/main` at commit `8b93e66` plus this documentation handoff. The Debian Trixie base image and v0.9.7a release images were published to GHCR and verified by the release workflow.
- **Base Runtime:** `ghcr.io/sempersupra/winebot-base:base-2026-05-04` is the active pinned fallback base image. `base-latest` and `base-stable` were updated by the Base Image workflow.

## Completed This Session
- **Input pipeline fix:** Added `POST /input/key` API endpoint with AHK Send backend that bypasses the X11 `explorer.exe /desktop` keyboard interception barrier.
- Added xdotool-to-AHK key syntax translation supporting modifier chords (`ctrl+c`), named keys (`Return`, `Escape`), function keys, arrow keys, and plain text.
- Added `WINEBOT_INPUT_KEY_BACKEND` config (ahk/xdotool/auto) and `WINEBOT_TIMEOUT_INPUT_KEY_SECONDS` with defaults.
- Exposed `WINEBOT_ALLOW_HEADLESS_HYBRID` and `WINEBOT_SUPERVISE_EXPLORER` in docker-compose headless profile.
- Documented keyboard barrier root cause, input pipeline, and solutions in `docs/troubleshooting.md`.
- Added 20 unit tests for key translation + e2e test for full keyboard pipeline.
- Closed superseded PRs #52 and #53.
- Verified: Ruff passes, Mypy passes (23 source files), 162 unit tests pass (0 new failures).

## Handover Point
- `main` at commit `a7184c8` (pending push).
- The new `/input/key` endpoint is ready for use by agents and users.
- E2E test (`tests/e2e/test_input_keyboard.py`) requires a running interactive WineBot instance to execute.
- Added base-image patching/upgrade steps so required patched packages are refreshed during base and application image builds.
- Updated release, smoke, soak, compose, README, and policy-check fallbacks to `ghcr.io/sempersupra/winebot-base:base-2026-05-04`.
- Corrected GitHub Actions Node.js 20 warnings by moving actions to Node 24-compatible pinned SHAs.
- Updated external dependency pins for the accepted dependency refresh:
  - Embedded Windows Python `3.13.13`.
  - Playwright `1.59.0`.
  - `pytest==9.0.3`.
  - `pytest-playwright==0.7.2`.
  - `uvloop==0.22.1`.
  - `zstandard==0.25.0`.
- Rebuilt and published the base image and v0.9.7a release containers through GitHub Actions.

## Published Images
- `ghcr.io/sempersupra/winebot-base:base-2026-05-04`
- `ghcr.io/sempersupra/winebot-base:base-latest`
- `ghcr.io/sempersupra/winebot-base:base-stable`
- `ghcr.io/sempersupra/winebot:v0.9.7a-rel`
  - index digest: `sha256:46bce5b85d6e0c0f2384f94a0d12b76970259bb073e939398479e5653c07d674`
- `ghcr.io/sempersupra/winebot:v0.9.7a-rel-runner`
  - index digest: `sha256:a41433596594966a3d99bf8884ff04fc0c945e31891adc44484049a9db2a642e`

## Validation Evidence
- Local lint gate passed:
  - `./scripts/wb lint`
  - Ruff passed.
  - Mypy passed for 93 source files.
  - Capability matrix, SBOM, and license policy checks passed.
  - Local Trivy filesystem scan was skipped because Trivy is not installed locally.
- Local containerized unit tests passed:
  - `docker compose -f compose/docker-compose.yml --profile lint run --rm lint-runner /work/scripts/ci/test.sh`
  - Result: `135 passed, 1 warning`.
- GitHub Base Image workflow passed:
  - Run `25330932840`
  - `https://github.com/SemperSupra/WineBot/actions/runs/25330932840`
- GitHub Release workflow for `v0.9.7a` passed:
  - Run `25331384570`
  - `https://github.com/SemperSupra/WineBot/actions/runs/25331384570`
  - Smoke gate, UI/UX policy, keyboard UX, Trivy scan, REL policy checks, publish, cosign signing, and artifact verification passed.

## GitHub Actions Status
- No queued runs at handoff.
- No in-progress runs at handoff.
- Latest Base Image and Release runs passed.
- A stale CI run failed before the new base image tag existed:
  - Run `25330798122`
  - Cause: CI attempted to pull `ghcr.io/sempersupra/winebot-base:base-2026-05-04` before the Base Image workflow had published it.
  - Current impact: superseded by the successful Base Image and Release workflows.

## Known Issues / Follow-Up
- GHCR authentication for CI when new pinned base tags are introduced (transient 403 from run 25330798122).
- Local Trivy is not installed; GitHub Trivy gates pass.
- E2E keyboard test requires running interactive WineBot instance to execute.

## Next Session Proposed Steps
1. Review GHCR package visibility/authentication and decide whether CI should log in before pulling private or organization-scoped base images.
2. Optionally create a GitHub Release or release notes entry for `v0.9.7a`.
3. Continue Stage 2 planning from the existing backlog after release follow-up is closed.
