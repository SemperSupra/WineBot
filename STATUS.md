# Status

## Current state
- **Dashboard UI:** Integrated noVNC + control panel with activity log console, collapsible sections, lifecycle controls, and screenshot/recording actions.
- **Openbox:** Single-desktop config, enriched menu with Wine tools, and helper scripts that show X11 output in Notepad and log menu actions.
- **Health/Lifecycle:** `/health/*` and `/lifecycle/*` endpoints are exercised by smoke tests; shutdown/poweroff controls are wired into the dashboard.
- **Automation/Tools:** winedbg API, AutoIt, AutoHotkey, Python, and recorder APIs remain integrated; Openbox helpers added for diagnostics.
- **Testing:** `scripts/smoke-test.sh --include-interactive` passes.
- **Diagnostics:** `scripts/diagnose-input-suite.sh` confirms `xdotool` mouse/keyboard injection works across Notepad, Regedit, and Winefile (with coordinate tuning).

## Validation so far
- `scripts/smoke-test.sh --include-interactive --cleanup` passes.
- **Unit Tests:** `pytest /tests` passes (39 tests covering API and Recorder).
- **Diagnostics:** `scripts/diagnose-input-suite.sh` passes comprehensively:
    - Verifies Mouse/Keyboard injection across Notepad, Regedit, Winefile.
    - Validates Clipboard (Copy/Paste), File I/O (Save As), and Window Management.
- **Recording:** Validated video capture and event annotation (via `scripts/run-diagnostics-with-recording.sh`).
- **Mouse Input Fixes:**
    - Updated `x11vnc` with `-noxrecord -noxfixes -noxdamage` to improve VNC input injection.
    - Added VNC Settings (Scale/View-Only) and "Inject Last Click" to dashboard for easier diagnosis.

## Known quirks
- `docker-compose` v1 may error with `ContainerConfig` on recreate; remove stale containers and re-run `up`.
- VNC mouse clicks should now be more reliable; if not, use the "Inject Last Click" tool in the dashboard to verify coordinates.

## Next steps (pick up here)
1. Verify the noVNC mouse click fix manually in the dashboard.
2. If reliable, remove the "Inject Last Click" debug tool.
3. Polish the dashboard UI for final release.
