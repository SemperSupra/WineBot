# Build Intents

WineBot supports four build intents controlled by `BUILD_INTENT`:

- `dev`: developer-focused image with extra diagnostics tooling.
- `test`: CI/local validation image with test harnesses.
- `rel`: release image for end users with runtime essentials and support diagnostics.
- `rel-runner`: release automation runner for agents/automation only (non-interactive).

## Current WineBot State (Recon)

- Builds are currently produced from a single `docker/Dockerfile` and run via `compose/docker-compose.yml`.
- Compose profiles (`headless`, `interactive`) select runtime mode and services (VNC/noVNC), not build type.
- Session artifacts and logs are stored under `/artifacts/sessions/...` and exposed via the `../artifacts` host bind mount.
- Test-only surface is treated as:
  - `/tests` harnesses
  - CI-only scripts and diagnostics orchestration (`scripts/smoke-test.sh`, `scripts/diagnose-master.sh`)
- Runtime surface is treated as:
  - API, `winebotctl`, automation scripts, session/log artifact generation, and support bundle generation.

## Capability Classes

### Deep Diagnostics (DEV only)

- Additional troubleshooting packages (`strace`, `lsof`, `nano`) are included only in `dev`.
- Verbose defaults are permitted (`WINEBOT_LOG_LEVEL=DEBUG` by default).
- Intended for local debugging and agent-assisted investigation.

### Test Hooks (TEST only; optionally DEV)

- `/tests` harnesses are included for `test` (and `dev`) images.
- CI executes smoke/diagnostic phases on `BUILD_INTENT=test`.
- Release images do not include `/tests`.

### Support Diagnostics (DEV/TEST/REL/REL-RUNNER)

- Runtime logs, traces, and session artifacts remain available in all intents.
- `scripts/winebotctl diag bundle` generates a bounded redacted support archive:
  - local-only generation
  - size cap (`--max-mb`, default `200`)
  - redacted env/config/log snapshots
  - manifest with included files and hashes

### Core Health Signals

- Standard API health endpoints remain part of product surface across intents.
- No hidden test-only route behavior is introduced for `rel`.

## Explicit Feature Classification

- `winedbg`: supported product surface via API/CLI, not a hidden test backdoor.
- Input recorder/tracing: runtime feature, bounded via existing controls.
- VNC/noVNC: supported runtime UX; available via profile/environment configuration.
- Session artifact collection: runtime feature used by diagnostics/support.

## Image Differences by Intent

- `dev`:
  - includes `/tests`
  - includes developer troubleshooting packages
  - default `WINEBOT_LOG_LEVEL=DEBUG`
- `test`:
  - includes `/tests`
  - no extra dev package set
  - default `WINEBOT_LOG_LEVEL=INFO`
- `rel`:
  - excludes `/tests`
  - installs runtime Python deps from `requirements-rel.txt` (no `pytest`)
  - default `WINEBOT_LOG_LEVEL=WARN`
  - supports user-initiated support mode and bundle generation
- `rel-runner`:
  - excludes `/tests`
  - installs runtime Python deps from `requirements-rel.txt` (no `pytest`)
  - removes VNC/noVNC packages (`x11vnc`, `novnc`, `websockify`)
  - rejects interactive runtime requests (`MODE=interactive` or `ENABLE_VNC=1`)
  - keeps API/CLI and support diagnostics for automation

## Compose and Intents

Profiles and intents are orthogonal:

- `--profile headless` or `--profile interactive` controls runtime UX.
- `BUILD_INTENT` controls packaged capabilities/defaults.
- Compose builds target stage `intent-${BUILD_INTENT}` and tags local images as
  `winebot:${WINEBOT_IMAGE_VERSION:-local}-${BUILD_INTENT}`.
- Base runtime is independently pinnable via `BASE_IMAGE` (for example
  `ghcr.io/<owner>/winebot-base:<base-version>`), allowing separate base lifecycle management.

Examples:

```bash
BUILD_INTENT=dev docker compose -f compose/docker-compose.yml --profile interactive up --build
BUILD_INTENT=test docker compose -f compose/docker-compose.yml --profile headless up --build
BUILD_INTENT=rel docker compose -f compose/docker-compose.yml --profile headless up --build
BUILD_INTENT=rel-runner docker compose -f compose/docker-compose.yml --profile headless up --build
```

## REL Support Mode

In `rel` and `rel-runner`, support mode can be enabled without enabling prohibited test hooks:

- `WINEBOT_SUPPORT_MODE=1`
- `WINEBOT_SUPPORT_MODE_MINUTES=<n>` (default `60`)

Effect:

- raises default log level from `WARN` to `INFO` for bounded triage
- sets `WINEBOT_SUPPORT_MODE_UNTIL_EPOCH` for explicit expiry tracking

## Support Bundle Usage

Generate bundle from the active session (or latest session):

```bash
scripts/winebotctl diag bundle --max-mb 200
```

Specify an explicit session directory/output:

```bash
scripts/winebotctl diag bundle \
  --session-dir /artifacts/sessions/<session-id> \
  --out /artifacts/support-bundle.tar.gz \
  --max-mb 200
```

Bundle layout:

```text
support-bundle/
  manifest.json
  app/
    version.json
    config.redacted.json
    logs/
  session/
  system/
    os.json
    env.redacted.json
  notes.txt
```
