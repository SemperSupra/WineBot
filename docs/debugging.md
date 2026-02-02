# Debugging

This guide covers winedbg support in WineBot and other useful tooling for troubleshooting.

## winedbg (internal)

Launch an app under winedbg in gdb proxy mode (default):

`ENABLE_WINEDBG=1 WINEDBG_MODE=gdb WINEDBG_PORT=2345 WINEDBG_NO_START=1 APP_EXE=/apps/MyApp.exe docker compose -f compose/docker-compose.yml --profile interactive up --build`

Connect from the host:

`gdb -ex "target remote localhost:2345"`

Run a scripted winedbg command (default mode):

`ENABLE_WINEDBG=1 WINEDBG_MODE=default WINEDBG_COMMAND="info proc" APP_EXE=/apps/MyApp.exe docker compose -f compose/docker-compose.yml --profile headless up --build`

Notes:

- `WINEDBG_PORT=0` skips `--port` (winedbg chooses a random port).
- The interactive compose profile publishes `WINEDBG_PORT`; for headless runs, add a port mapping in an override file if you need remote gdb access.
- `WINEDBG_NO_START=0` auto-starts gdb inside the container.
- `WINEDBG_COMMAND` and `WINEDBG_SCRIPT` only apply to `WINEDBG_MODE=default`.
- `scripts/smoke-test.sh --include-debug` runs a minimal winedbg check.
- `scripts/smoke-test.sh --include-debug-proxy` runs a gdb proxy attach check and verifies the target exe is running.
- `gdb` may exit with code `137` in some container environments; treat it as valid if threads are printed.

## Other Windows-side tools (run under Wine)

These can be installed into the prefix or placed under `apps/`:

- Sysinternals tools: ProcDump, Process Explorer, Process Monitor, DebugView
- Dependency Walker/Dependencies to inspect missing DLLs
- App-specific crash reporters or logging tools

## Host/container perspective

Useful Linux-side tools for observing the Wine environment:

- `WINEDEBUG` channels for verbose logging (example: `WINEDEBUG=+seh,+tid,+timestamp`)
- `xwininfo`, `xprop`, `wmctrl`, `xdotool` for window inspection and focus issues
- `ps`, `top`, and `/proc` (via `procps`) for process state
- Optional: `strace`, `ltrace`, `lsof`, `tcpdump` if you add them to the image

## Headless GUI Debugging

WineBot includes helpers to make headless debugging easier (especially with Xvfb).

### Auto-detected X11 Environment
Scripts in `scripts/` and `automation/` automatically source `scripts/lib/x11_env.sh`. This helper:
- Detects the active X server (even if `DISPLAY` is unset).
- Finds the correct `XAUTHORITY` (handling `xvfb-run` locations).
- Exports these variables so tools like `xdotool` and `import` work seamlessly.

### X11 Inspection Wrapper
Use `/automation/x11.sh` (inside container) to inspect windows without manual env setup:

```bash
# List all windows (ID + Title)
/automation/x11.sh list-windows

# Get active window ID
/automation/x11.sh active-window

# Get title of a specific window
/automation/x11.sh window-title <id>

# Focus a window
/automation/x11.sh focus <id>

# Search windows by name
/automation/x11.sh search --name "Notepad"
```

### taking Screenshots
`automation/screenshot.sh` is now robust against missing env variables:
```bash
/automation/screenshot.sh /tmp/myshot.png
```

### Running AutoHotkey with Focus + Logs
Use `scripts/run-ahk.sh` to ensure Wine is ready, focus a target window, and capture logs:
```bash
/scripts/run-ahk.sh my_script.ahk --focus-title "My App" --log /tmp/ahk.log
```

### Windows Inspectors (Au3Info / WinSpy)
You can inspect window controls (ClassNN, ID) using Windows tools running under Wine.

**Enable Inspectors:**
Run the installer inside the container (only needs to be done once per container if not persisted):
```bash
/scripts/install-inspectors.sh
```

**Run Inspectors:**
```bash
# AutoIt Window Info (pre-installed)
/scripts/au3info.sh

# WinSpy (if installed)
/scripts/winspy.sh
```
*Note: These run graphically. Use VNC/noVNC to interact with them.*
