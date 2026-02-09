# Testing

WineBot includes a smoke test to validate the display stack, Wine prefix, core API endpoints, and optional VNC/noVNC services.

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
`/wineprefix/drive_c/users/winebot/Temp/` for reliability in headless mode.

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

## Soak Diagnostics

Use the soak checker to watch for unbounded trace/recording growth and memory drift over time:

`scripts/diagnose-trace-soak.sh`

Useful environment knobs:

- `DURATION_SECONDS` (default `600`)
- `INTERVAL_SECONDS` (default `15`)
- `MAX_LOG_MB` (default `512`)
- `MAX_SESSION_MB` (default `4096`)
- `MAX_PID1_RSS_MB` (default `2048`)
- `API_URL` and `API_TOKEN`
