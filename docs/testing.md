# Testing

WineBot includes a simple smoke test to validate the display stack, Wine prefix, and optional VNC/noVNC services.

## Quick smoke test (headless)

`scripts/smoke-test.sh`

Checks performed:

- Xvfb and openbox are running
- A window is present on `DISPLAY=:99`
- Screenshot capture works (`/tmp/screenshot.png`)
- The Wine prefix persists across containers

## Full smoke test

`scripts/smoke-test.sh --full`

Adds a Notepad automation round-trip. The test writes a file under
`/wineprefix/drive_c/users/winebot/Temp/` for reliability in headless mode.

## Interactive checks

`scripts/smoke-test.sh --include-interactive`

Verifies `x11vnc` and noVNC/websockify are running and accepting connections.

## Cleanup

By default the smoke test leaves services running. To stop them:

`scripts/smoke-test.sh --cleanup`

For CI, prefer `--full --cleanup`.
