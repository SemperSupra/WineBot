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

### API Control
You can also launch apps under winedbg via the internal API:

```bash
curl -X POST http://localhost:8000/run/winedbg \
  -H "Content-Type: application/json" \
  -d '{"path":"/apps/MyApp.exe","mode":"gdb","port":2345,"no_start":true}'
```

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

## Input tracing

WineBot can record detailed input events (mouse motion, clicks, key presses) from both interactive use (VNC/noVNC) and agent-driven actions.

### Enable via env
Set `WINEBOT_INPUT_TRACE=1` when starting the container. Optional tuning:
- `WINEBOT_INPUT_TRACE_RAW=1`: include raw `xinput` lines in each event.
- `WINEBOT_INPUT_TRACE_MOTION_SAMPLE_MS=NN`: sample motion events (0 = no sampling).
- `WINEBOT_INPUT_TRACE_WINDOWS=1`: enable Windows-side input tracing (AutoHotkey).
- `WINEBOT_INPUT_TRACE_WINDOWS_SAMPLE_MS=NN`: mouse move sample interval for Windows tracing (default 10ms).
- `WINEBOT_INPUT_TRACE_NETWORK=1`: enable VNC network proxy tracing (requires container restart).
- `WINEBOT_INPUT_TRACE_NETWORK_SAMPLE_MS=NN`: sample motion events for network tracing (default 10ms).
- `WINEBOT_INPUT_TRACE_RECORD=1`: add input trace events into recording subtitles.

### Enable via API
```bash
curl -X POST http://localhost:8000/input/trace/start
curl -X GET  http://localhost:8000/input/trace/status
curl -X POST http://localhost:8000/input/trace/stop
```

Windows-side tracing (AutoHotkey):
```bash
curl -X POST http://localhost:8000/input/trace/windows/start
curl -X GET  http://localhost:8000/input/trace/windows/status
curl -X POST http://localhost:8000/input/trace/windows/stop
```

Client-side tracing (noVNC UI):
```bash
curl -X POST http://localhost:8000/input/trace/client/start
curl -X GET  http://localhost:8000/input/trace/client/status
curl -X POST http://localhost:8000/input/trace/client/stop
```

Network tracing (VNC proxy):
```bash
curl -X GET  http://localhost:8000/input/trace/network/status
curl -X POST http://localhost:8000/input/trace/network/start
curl -X POST http://localhost:8000/input/trace/network/stop
```

### Read recent events
```bash
curl "http://localhost:8000/input/events?limit=50"
curl "http://localhost:8000/input/events?limit=50&source=client"
curl "http://localhost:8000/input/events?limit=50&source=windows"
```

Events are written to `logs/input_events*.jsonl` inside the session directory.

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
Preferred (API-first) usage:
```bash
scripts/winebotctl run ahk --file my_script.ahk --focus-title "My App"
```

### Windows Inspectors (Au3Info / WinInspect)
Use API inspection for agent-driven automation. Native inspector binaries are still available for interactive debugging when needed.

**Enable Inspectors:**
Run the installer inside the container (only needs to be done once per container if not persisted):
```bash
/scripts/install-inspectors.sh
```

**Run Inspectors (interactive tools):**
```bash
# AutoIt Window Info (pre-installed)
/scripts/au3info.sh

# WinInspect GUI (if installed via /scripts/install-inspectors.sh)
wine /opt/winebot/windows-tools/WinSpy/wininspect-gui.exe

# WinInspect daemon/CLI smoke
bash /scripts/diagnostics/smoke-wininspect.sh
```
*Note: These run graphically. Use VNC/noVNC to interact with them.*

See [WinInspect v0.4.0 Integration](wininspect-v0.4.0-integration.md) for the
daemon, protocol, and capability-based integration plan.

### WinSpy-Style API Inspection
For agent-driven automation, you can query control metadata via the API:

```bash
curl -X POST http://localhost:8000/inspect/window \
  -H "Content-Type: application/json" \
  -d '{"title":"Untitled - Notepad","include_controls":true}'
```

### Auto-Open Viewer (Host)
When launching via `scripts/run-app.sh`, you can auto-open a viewer:

```bash
scripts/run-app.sh "/wineprefix/drive_c/Program Files/MyApp/MyApp.exe" --view novnc
```

Supported modes: `auto`, `novnc`, `vnc`. This forces interactive mode and launches a browser or VNC client. When noVNC is used, the VNC password is passed via URL for auto-connect (disable with `--no-password-url`).

Example with explicit password:

```bash
scripts/run-app.sh "/wineprefix/drive_c/Program Files/MyApp/MyApp.exe" \
  --view novnc \
  --novnc-password "winebot"
```

To avoid embedding the password in the URL:

```bash
scripts/run-app.sh "/wineprefix/drive_c/Program Files/MyApp/MyApp.exe" \
  --view novnc \
  --no-password-url
```

For VNC viewers, use a password file capable client (e.g., `vncviewer`) and pass a password:

```bash
scripts/run-app.sh "/wineprefix/drive_c/Program Files/MyApp/MyApp.exe" \
  --view vnc \
  --vnc-password "winebot"
```

---

## Git Bash Path Translation (Windows Host)

When running `docker` commands from **Git Bash** (MSYS2/MinGW) on Windows, Unix-style
paths like `/scripts` or `/tmp` are automatically translated to Windows paths:
`C:/Program Files/Git/scripts` or `C:/Users/Mark/AppData/Local/Temp/`.

This causes cryptic failures:
```
python3: can't open file '/work/C:/Program Files/Git/scripts/file.py': No such file or directory
```

### Prevention

Prefix all `docker` commands with `MSYS_NO_PATHCONV=1` to disable path translation:

```bash
# WRONG — path gets mangled
docker exec mycontainer python3 /scripts/annotation_server.py

# RIGHT — path preserved
MSYS_NO_PATHCONV=1 docker exec mycontainer python3 /scripts/annotation_server.py
```

### Affected Commands

| Command | Without MSYS_NO_PATHCONV | With MSYS_NO_PATHCONV |
|:---|:---|:---|
| `docker exec ... python3 /path/to/script.py` | ❌ `File not found` | ✅ Works |
| `docker cp /tmp/file container:/path/` | ❌ Wrong source path | ✅ Works |
| `docker run -v C:\path:/container` | ❌ Wrong mount path | ✅ Use `//c/path` |
| `docker exec -d ...` | ❌ Detached mode fails silently | ✅ Use MSYS_NO_PATHCONV |
| `sh -c 'cat /tmp/file'` | ❌ `/tmp` → Windows temp | ✅ Works |

### Docker Volume Mounts

For volume mounts, use double-slash prefix for Windows paths:

```bash
# WRONG — Git Bash translates C:\path to /c/path with wrong format
docker run -v C:\Users\me\data:/data ...

# RIGHT — double-slash prevents translation
docker run -v //c/Users/me/projects/models:/models ...
```

### Annotation Server (Specific Case)

The annotation server requires this fix when started from the host:

```bash
# From the repo root:
MSYS_NO_PATHCONV=1 docker exec -d winebot-cv python3 /scripts/annotation_server.py \
  --dir /artifacts/annotations/images --port 8080 --sidecar http://localhost:8001

# Or use the helper script:
MSYS_NO_PATHCONV=1 bash scripts/start-annotation.sh
```

### Diagnostic

If a command fails with path-related errors, check whether Git Bash is translating:

```bash
# Check if translation is happening
docker exec winebot-cv python3 -c "import sys; print(sys.argv)" /scripts/test.py
# If output shows C:/Program Files/Git/, MSYS_NO_PATHCONV=1 is needed.
```
