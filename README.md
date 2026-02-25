# WineBot

> **For AI Agents & Automation:** See [AGENTS.md](AGENTS.md) for the API and programmatic control guide.

WineBot is a containerized harness for running Windows GUI applications under Wine in headless or interactive modes. It provides a stable virtual desktop for automation and optional VNC/noVNC access for debugging.

## Control Surfaces

WineBot provides two primary CLI tools for interaction, depending on your role:

| Tool | Purpose | Context |
| :--- | :--- | :--- |
| **`scripts/wb`** | **Developer/Lifecycle Tool**. Build, test, and manage the project infrastructure. | **Host Machine**. Uses Docker/Compose to manage the environment. |
| **`scripts/winebotctl`** | **Operator/Agent Tool**. Control a running WineBot instance via the API. | **Anywhere**. Inside the container, or remotely via the network. |

### 1. Developer Tool (`scripts/wb`)
Use this for project maintenance and verification:
- `./scripts/wb bootstrap`: Verify host dependencies.
- `./scripts/wb lint`: Run containerized linting (Ruff/Mypy).
- `./scripts/wb test`: Run unit and E2E tests.
- `./scripts/wb build [intent]`: Build local images (e.g., `slim`, `dev`, `rel`).
- `./scripts/wb vuln`: Run vulnerability scans.

### 2. Operator Tool (`scripts/winebotctl`)
Use this to automate applications:
- `scripts/winebotctl health`: Check API status.
- `scripts/winebotctl screenshot`: Capture the virtual desktop.
- `scripts/winebotctl apps run "/path/to/app.exe"`: Launch a Windows app.
- `scripts/winebotctl input click 100 200`: Perform a mouse click.

## Configuration

WineBot uses a unified, validated configuration system based on environment variables. 

| Variable | Default | Description |
| :--- | :--- | :--- |
| `API_TOKEN` | (Random) | Security token for API access. |
| `WINEBOT_LOG_LEVEL` | `INFO` | DEBUG, INFO, WARNING, ERROR, CRITICAL. |
| `WINEBOT_COMMAND_TIMEOUT` | `5` | Subprocess execution limit in seconds. |
| `WINEBOT_SESSION_ROOT` | `/artifacts/sessions` | Path to store session data. |
| `WINEBOT_INACTIVITY_PAUSE_SECONDS` | `180` | Auto-pause recording when idle (seconds). |
| `WINEBOT_INACTIVITY_PAUSE_SECONDS_HUMAN` | (Unset) | Optional human-specific inactivity threshold override. |
| `WINEBOT_INACTIVITY_PAUSE_SECONDS_AGENT` | (Unset) | Optional agent-specific inactivity threshold override. |
| `WINEBOT_INACTIVITY_RESUME_ACTIVITY_SECONDS` | `10` | Activity recency window for auto-resume. |
| `WINEBOT_INACTIVITY_MIN_PAUSE_SECONDS` | `15` | Minimum paused dwell time before auto-resume. |
| `WINEBOT_INACTIVITY_RESUME_COOLDOWN_SECONDS` | `10` | Cooldown after auto-pause before auto-resume is allowed. |
| `WINEBOT_PERF_METRICS` | `1` | Enable runtime performance metric logging. |
| `WINEBOT_PERF_METRICS_SAMPLE_SECONDS` | `30` | Monitor sample period for perf metric snapshots. |
| `WINEBOT_TELEMETRY` | `1` | Master telemetry toggle. |
| `WINEBOT_TELEMETRY_LEVEL` | `standard` | Telemetry detail mode (`minimal`, `standard`, `debug`). |
| `WINEBOT_TELEMETRY_FEATURES` | (Unset) | Optional allowlist of features (`recording,input,control,automation,lifecycle,health,runtime`). |
| `WINEBOT_TELEMETRY_CAPABILITIES` | (Unset) | Optional allowlist of capabilities (comma-separated). |
| `WINEBOT_TELEMETRY_FEATURE_SETS` | (Unset) | Optional allowlist of feature sets. |
| `WINEBOT_TELEMETRY_SAMPLE_RATE` | `1.0` | Probability of event emission (0.0-1.0). |
| `WINEBOT_TELEMETRY_MAX_EVENTS_PER_MIN` | `600` | Global telemetry emission cap per minute. |

## Quickstart

Headless:

Headless:

`docker compose -f compose/docker-compose.yml --profile headless up --build`

Interactive (VNC + noVNC):

`docker compose -f compose/docker-compose.yml --profile interactive up --build`

If you only have `docker-compose` v1 installed, replace `docker compose` with `docker-compose`.

Named defaults (recommended):

`./scripts/wb profile list`

`./scripts/wb profile up assisted-desktop --build`

`./scripts/wb profile up unattended-runner --build`

See [docs/default-profiles.md](docs/default-profiles.md) for profile definitions.

Feature/capability commit mapping:

See [docs/feature-capability-commit-map.md](docs/feature-capability-commit-map.md).
Auto-generate a draft from recent commit subjects:
`./scripts/wb feature-map 200`

Test capability coverage matrix:

See [docs/test-capability-matrix.md](docs/test-capability-matrix.md).

Standards and conformance coverage:

See [docs/conformance.md](docs/conformance.md).

Invariant registry and enforcement model:

See [docs/invariants.md](docs/invariants.md).

Generate release/CI trust evidence bundle:

`scripts/ci/generate-trust-pack.sh artifacts/trust-pack`

## Build Intents

`BUILD_INTENT` controls packaged capabilities and defaults independently from compose profiles:

- profiles select runtime UX (`headless`/`interactive`)
- build intent selects image intent (`dev`/`test`/`slim`/`rel`/`rel-runner`)

Examples:

`BUILD_INTENT=dev docker compose -f compose/docker-compose.yml --profile interactive up --build`

`BUILD_INTENT=slim docker compose -f compose/docker-compose.yml --profile headless up --build`

`slim` is a lightweight image that skips the 1.4GB pre-warmed prefix template, ideal for CI and rapid logic verification.

`BUILD_INTENT=rel docker compose -f compose/docker-compose.yml --profile headless up --build`

`BUILD_INTENT=rel-runner docker compose -f compose/docker-compose.yml --profile headless up --build`

`rel-runner` is automation-only: no VNC/noVNC interactive stack is available. Use CLI/API-driven execution and diagnostics.

Local images are named by version+intent:

`winebot:${WINEBOT_IMAGE_VERSION:-local}-${BUILD_INTENT}`

Base runtime can be pinned independently:

`BASE_IMAGE=ghcr.io/<owner>/winebot-base:<base-version>`

CI/release builds read repository variable `WINEBOT_BASE_IMAGE` (fallback is `ghcr.io/SemperSupra/winebot-base:base-2026-02-09`).

In `rel` and `rel-runner`, default logging is capped (`WARN`). Enable bounded support mode for triage:

`WINEBOT_SUPPORT_MODE=1 WINEBOT_SUPPORT_MODE_MINUTES=60 BUILD_INTENT=rel docker compose -f compose/docker-compose.yml --profile headless up --build`

Generate a local support bundle:

`scripts/winebotctl diag bundle --max-mb 200`

## Simplified Usage (v0.4+)

The updated entrypoint allows running commands directly with automatic Xvfb management and host user mapping.

**Run a command (pass-through):**
```bash
# Runs 'make' inside the container as the current host user
docker run --rm -v $(pwd):/work -w /work -e HOST_UID=$(id -u) winebot make
```

**Run a Windows executable:**
```bash
docker run --rm -v $(pwd):/work -w /work -e HOST_UID=$(id -u) winebot wine myapp.exe
```

**Interactive Shell:**
```bash
docker run --rm -it -e HOST_UID=$(id -u) winebot bash
```

## Run a Windows app (Compose)

1. Put your executable in `./apps`.
2. Set `APP_EXE` to the path inside the container (defaults to `cmd.exe` if unset).

Example:

`APP_EXE=/apps/MyApp.exe docker compose -f compose/docker-compose.yml --profile interactive up --build`

You can also set:

- `APP_ARGS` for optional arguments
- `WORKDIR` for a specific working directory
- `APP_NAME` to label the noVNC URL

## Install then run (recommended)

Install into the persistent Wine prefix:

`scripts/install-app.sh apps/MyInstaller.exe`

Run the installed app (use the Unix path to avoid backslash escaping):

`scripts/run-app.sh "/wineprefix/drive_c/Program Files/MyApp/MyApp.exe"`

List installed executables in the prefix:

`scripts/list-installed-apps.sh --pattern "MyApp"`

Run in the background:

`scripts/run-app.sh "/wineprefix/drive_c/Program Files/MyApp/MyApp.exe" --detach`

See `docs/installing-apps.md` for more options.

## Connect to the desktop

- VNC client: `localhost:5900`
- Browser (noVNC): `http://localhost:6080`

Change the default VNC password in `compose/docker-compose.yml`.

## Sessions and artifacts

Every WineBot start creates a new session under `/artifacts/sessions/session-<YYYY-MM-DD>-<unix>-<rand>/`. The session path is exported as `WINEBOT_SESSION_DIR`.

To resume an existing session on startup, set one of:
- `WINEBOT_SESSION_DIR=/artifacts/sessions/<session-id>`
- `WINEBOT_SESSION_ID=<session-id>` (uses `WINEBOT_SESSION_ROOT`)

Common locations inside the session directory:
- `screenshots/` for screenshots captured via API or scripts
- `logs/` for API/entrypoint/automation logs
- `scripts/` for API-generated scripts (AHK/AutoIt/Python)
- `user/` for app inputs/outputs (Wine user home; override with `WINEBOT_USER_DIR`)

Auto-open the dashboard (noVNC + API controls) or a VNC viewer (host helper):

`scripts/run-app.sh "/wineprefix/drive_c/Program Files/MyApp/MyApp.exe" --view novnc`

This forces interactive mode and opens the dashboard (`/ui`) with the embedded noVNC canvas. If a VNC password is set, it is passed via the URL to avoid prompts (consider the security tradeoff).

Explicit example with password:

`scripts/run-app.sh "/wineprefix/drive_c/Program Files/MyApp/MyApp.exe" --view novnc --novnc-password "winebot"`

To avoid embedding the password in the URL:

`scripts/run-app.sh "/wineprefix/drive_c/Program Files/MyApp/MyApp.exe" --view novnc --no-password-url`

If you prefer a VNC client:

`scripts/run-app.sh "/wineprefix/drive_c/Program Files/MyApp/MyApp.exe" --view vnc --vnc-password "winebot"`

Dashboard (noVNC + API controls):

`http://localhost:8000/ui` (enter `API_TOKEN` in the panel if configured)

## Unified CLI (API-first)

Use `scripts/winebotctl` to access the full API from the host or container. It supports idempotent mode and a generic API passthrough.

Examples:

`scripts/winebotctl health`

`scripts/winebotctl sessions list`

`scripts/winebotctl recording start --session-root /artifacts/sessions`

`scripts/winebotctl api POST /sessions/suspend --json '{"shutdown_wine":true}'`

Profile and config helpers:

`scripts/winebotctl config profile list`

`scripts/winebotctl config profile set human-desktop`

`scripts/winebotctl config validate`

`scripts/winebotctl config apply`

`scripts/winebotctl perf summary`

## Recording API Quick Reference

Recording action endpoints share a common response contract:
- `action`: `start|pause|resume|stop`
- `status`: legacy compatibility status string
- `result`: `converged|accepted`
- `converged`: boolean convergence signal

Common `status` values:
- `POST /recording/start`: `started`, `resumed`, `already_recording`
- `POST /recording/pause`: `paused`, `already_paused`, `idle`
- `POST /recording/resume`: `resumed`, `already_recording`, `resume_requested`
- `POST /recording/stop`: `stopped`, `already_stopped`, `stop_requested`

When `result=accepted` and `converged=false` (for example `stop_requested`), the action was accepted and is still converging; poll `GET /health/recording` until the target state is reached.

See:
- [docs/api.md](docs/api.md) (Recording Action Contract, transition guarantees, idempotency examples)
- [docs/recording.md](docs/recording.md) (recording behavior and runtime knobs)

## Take a screenshot (headless)

`docker compose -f compose/docker-compose.yml --profile headless exec --user winebot winebot ./automation/screenshot.sh`

If a session is active, the image is saved under `/artifacts/sessions/<session-id>/screenshots/` inside the container. A JSON sidecar with metadata is written next to it (`.png.json`). You can also specify a custom path or directory as an argument.

## Debug with winedbg

Run an app under winedbg's gdb proxy (port 2345):

`ENABLE_WINEDBG=1 WINEDBG_MODE=gdb WINEDBG_PORT=2345 WINEDBG_NO_START=1 APP_EXE=/apps/MyApp.exe docker compose -f compose/docker-compose.yml --profile interactive up --build`

Then connect from the host:

`gdb -ex "target remote localhost:2345"`

See [docs/debugging.md](docs/debugging.md) for scripted commands and additional tooling.

## Recording & Annotations

WineBot can record your session to video with automatically generated subtitles and positional overlays.

- **Enable recording:** Pass `--record` to `scripts/run-app.sh`.
- **Add annotations:** Use `scripts/annotate.sh` inside the container to add text or positional overlays during runtime.
- **Toggle visibility:** Subtitles and overlays are stored as separate tracks in the MKV file and can be toggled ON/OFF in players like VLC.

See [docs/recording.md](docs/recording.md) for details.

## Headless Tools & Helpers

WineBot provides helpers to simplify headless interaction:

- **X11 Inspection:** `/automation/x11.sh` (list windows, focus, search)
- **Robust Screenshots:** `/automation/screenshot.sh` (auto-detects X11 env)
- **Automation runners:** `scripts/winebotctl run ahk|autoit|python`
- **Window inspection:** `scripts/winebotctl inspect window` or `/inspect/window`
- **Internal API:** HTTP API for programmatic control (see `docs/api.md`).

See [docs/debugging.md](docs/debugging.md) for details.

## Performance & Reliability

Best practices and a low-resource compose override are documented in [docs/performance.md](docs/performance.md).
A detailed [Build Performance & Resource Utilization Report](docs/build-performance-and-resource-utilization.md) is also available.

## Run the sample CV automation

`docker compose -f compose/docker-compose.yml --profile headless exec --user winebot winebot python3 automation/find_and_click.py --template automation/assets/example_button.png`

## Run the Notepad automation

`docker compose -f compose/docker-compose.yml --profile interactive exec --user winebot winebot-interactive python3 automation/notepad_create_and_verify.py --text "Hello from WineBot" --output /tmp/notepad_test.txt --launch`

## Windows Automation Tools

WineBot includes pre-installed Windows automation tools running under Wine:

- **AutoIt v3** (`autoit`)
- **AutoHotkey v1.1** (`ahk`)
- **Python 3.13** (`winpy`)

See [docs/windows-automation-tools.md](docs/windows-automation-tools.md) for usage.
Note: pywinauto is not part of the active toolchain in this release; revisit as Wine UIA support matures.

Run the tool smoke tests:

`docker compose -f compose/docker-compose.yml --profile headless exec --user winebot winebot ./tests/run_smoke_tests.sh`

Expected smoke artifact: `/tmp/smoke_test.png`

## Smoke test

`scripts/smoke-test.sh`

Variants:

- `scripts/smoke-test.sh --full`
- `scripts/smoke-test.sh --include-interactive`
- `scripts/smoke-test.sh --include-debug`
- `scripts/smoke-test.sh --include-debug-proxy`
- `scripts/smoke-test.sh --full --cleanup`

## Releases & GHCR

GitHub Actions runs smoke tests and publishes images to GHCR on release:

- `ghcr.io/<owner>/winebot:<release-tag>-rel`
- `ghcr.io/<owner>/winebot:<release-tag>-rel-runner`
- `ghcr.io/<owner>/winebot:latest` (alias for rel)
- `ghcr.io/<owner>/winebot:latest-rel`
- `ghcr.io/<owner>/winebot:latest-rel-runner`
- `ghcr.io/<owner>/winebot:sha-<short>-rel`
- `ghcr.io/<owner>/winebot:sha-<short>-rel-runner`

Manual runs are supported via Actions → Release → Run workflow. Provide `image_tag` or it defaults to `manual-<sha>`.

Use the `Base Image` workflow to publish versioned base images:

- `ghcr.io/<owner>/winebot-base:<base-version>`
- `ghcr.io/<owner>/winebot-base:base-latest`
- optional `ghcr.io/<owner>/winebot-base:base-stable`

## Documentation

- `docs/architecture.md`
- `docs/automation.md`
- `docs/api.md`
- `policy/visual-style-and-ux-policy.md`
- `docs/debugging.md`
- `docs/build-intents.md`
- `docs/feature-capability-commit-map.md`
- `docs/feature-capability-commit-map.auto.md` (generated draft)
- `docs/installing-apps.md`
- `docs/testing.md`
- `docs/troubleshooting.md`
