# WineBot Agent Map

This document is a navigation aid for autonomous agents working on the WineBot codebase.

## 1. System Architecture

WineBot is a containerized Windows application runtime (Wine 10.0) with an X11 display stack, controlled via a Python FastAPI.

### Core Layers
| Layer | Components | Description |
| :--- | :--- | :--- |
| **Control** | `api/` | FastAPI server, Input Broker, Policy enforcement. |
| **Orchestration** | `docker/entrypoint.sh` | Startup sequence, Xvfb/Openbox launch, Supervisor loop. |
| **Automation** | `automation/` | Python/AHK scripts for recording, tracing, and interacting with Wine. |
| **Tools** | `scripts/` | Shell helpers for local management (`winebotctl`) and diagnostics. |
| **Policies** | `policy/` | Formal mandates for development, security, and visual style. |

## 2. Key File Map

| Path | Purpose | Key Symbols |
| :--- | :--- | :--- |
| `api/server.py` | Main API entrypoint. Mounts routers. | `app`, `lifespan` |
| `api/core/broker.py` | Input Control Policy state machine. | `InputBroker`, `ControlMode` |
| `policy/visual-style-and-ux-policy.md` | Mandates "Cyber-Industrial Dark" UI and A11y. | |
| `api/routers/*.py` | API endpoints by category. | `/health`, `/input`, `/recording` |
| `docker/entrypoint.sh` | Container boot logic. Handles Xvfb, Openbox, Wine init. | `Xvfb`, `wineserver`, `tint2` |
| `docker/openbox/rc.xml` | Window Manager config. Controls input focus/decorations. | `<applications>`, `<mouse>` |
| `scripts/bin/` | Primary user-facing tools (`winebotctl`, `run-app.sh`). | |
| `scripts/diagnostics/` | System validation suite (`diagnose-master.sh`, `health-check.sh`). | `diagnose-master.sh` |
| `scripts/setup/` | Installation and fix logic (`install-theme.sh`, `fix-wine-input.sh`). | |
| `automation/bin/` | Standalone automation tools (`x11.sh`, `screenshot.sh`). | |
| `automation/examples/` | Demo and verification scripts (`notepad_create_and_verify.py`). | |
| `tests/` | Pytest suite. | `test_policy.py`, `test_api.py` |
| `archive/status/` | Archived project status reports. | |

## 3. Environment Variables

| Variable | Default | Purpose |
| :--- | :--- | :--- |
| `WINEBOT_RECORD` | profile-dependent (`0` headless, `1` interactive) | Enable session recording (ffmpeg). |
| `WINEBOT_INPUT_TRACE` | profile-dependent (`1` in compose defaults) | Enable X11 input event logging. |
| `WINEBOT_INPUT_TRACE_WINDOWS` | profile-dependent (`1` in compose defaults) | Enable Windows-side (AHK) input logging. |
| `WINEBOT_INPUT_TRACE_NETWORK` | `0` | Enable VNC proxy logging. |
| `API_TOKEN` | (None) | Secure API access key. |
| `VNC_PASSWORD` | (None) | Password for x11vnc. |
| `SCREEN` | `1280x720x24` | Xvfb display resolution. |
| `WINEBOT_SHUTDOWN_GUARD_TTL_SECONDS` | `120` | Duplicate shutdown guard window. |
| `WINEBOT_LOG_FOLLOW_ACQUIRE_TIMEOUT_SECONDS` | `0.05` | Timeout acquiring log-follow stream slot. |

## 4. Common Tasks

### Docker runtime on this host

Docker Desktop has been removed. Docker Engine v29.6.1 runs inside WSL2
`Ubuntu`; use explicit WSL commands from Windows:

```powershell
wsl -d Ubuntu docker <args>
wsl -d Ubuntu docker compose <args>
```

Do not run bare `docker` from Windows PowerShell unless you know the user's
PowerShell profile loaded the local proxy functions. Use `docker compose`, not
`docker-compose`. See [docs/DOCKER_ENGINE_ON_WSL2.md](docs/DOCKER_ENGINE_ON_WSL2.md).

### How to run tests?
```bash
# Rapid local feedback (Watch mode)
./scripts/bin/dev-watch.sh

# UI/UX Policy Compliance
wsl -d Ubuntu docker compose -f compose/docker-compose.yml --profile interactive --profile test run --rm test-runner pytest tests/e2e/test_ux_quality.py

# Unit tests
wsl -d Ubuntu docker compose -f compose/docker-compose.yml --profile interactive --profile test run --rm test-runner scripts/ci/test.sh
```

### How to apply config changes?
```bash
# 1. Edit config
scripts/winebotctl config set KEY VALUE

# 2. Apply (Restarts container)
scripts/winebotctl config apply
```

### How to trace input?
```bash
scripts/winebotctl input trace start --layer windows
scripts/winebotctl input trace events --source client --limit 50
```

### How to debug input issues?
1. Enable traces: `WINEBOT_INPUT_TRACE=1` etc.
2. Check `logs/input_events_*.jsonl` in session dir.
3. Run `scripts/diagnose-input-suite.sh` inside container.

## 5. Programmatic Interaction

Agents should use the following API patterns for reliable control.

### Automated Input
#### `POST /input/mouse/click`
Performs a mouse click at specific coordinates.

**Payload:**
```json
{
  "x": 100,
  "y": 100,
  "button": 1,
  "window_title": "Notepad",
  "relative": true
}
```

**Features:**
- **Validation:** Clicks are validated against the current `SCREEN` resolution to prevent out-of-bounds errors.
- **Window Targeting:** Providing `window_title` or `window_id` logs the target for better traceability.
- **Relative Clicking:** If `relative: true`, coordinates are calculated relative to the specified window's top-left corner.
- **Non-blocking:** The call is asynchronous and will not stall the system during execution.

### Health & Discovery
- **`GET /health`**: Use this to verify system readiness. Check `security_warning` for potential exposure.
- **`GET /health/invariants`**: Use this to verify runtime lifecycle/control/config invariants.
- **mDNS Discovery**: WineBot broadcasts `_winebot-session._tcp.local.`. Agents on the same network can discover instances automatically.

## 6. Responsible Automation (Agent Ethics)

To ensure system stability and reliability, agents must adhere to the following constraints:

1.  **Avoid UI Feedback Loops:** Do not programmatically click on transient UI elements like Toast notifications or status badges. This can lead to non-deterministic state transitions.
2.  **Action Throttling:** Enforce a minimum "Politeness" delay of at least **100ms** between discrete API actions (e.g., clicks or keypresses) to allow the Wine/X11 stack to settle.
3.  **Graceful Termination:** Always attempt to call `POST /lifecycle/shutdown` before exiting to ensure video artifacts are finalized and resources are reaped.
4.  **Least Privilege:** Do not attempt to modify files outside of `/wineprefix` or `/artifacts`. The `apps` and `automation` directories are mounted as Read-Only for safety.

## 7. Diagnosing Input Issues

### Is the input pipeline healthy?

```bash
# Check keyboard injection works
scripts/winebotctl input key "test" --window-title "Notepad"

# Check trace layers
scripts/winebotctl input trace status --layer x11
scripts/winebotctl input trace status --layer windows

# Run full diagnostic suite (requires interactive mode)
scripts/diagnostics/diagnose-input-suite.sh

# Run 5-layer trace bisect
scripts/diagnostics/diagnose-input-trace.sh --layers x11,windows

# Analyze keyboard latency
python3 scripts/diagnostics/analyze-trace-latency.py --mode keyboard
```

### Keyboard events not reaching the app?

The Wine desktop shell (`explorer.exe /desktop`) intercepts X11 keyboard events.
The `/input/key` endpoint uses AHK Send by default, bypassing this barrier.
Verify the backend in the response: `{"backend": "ahk", "status": "sent"}`.

If key events arrive at X11 but not Windows:
```bash
# Enable Windows trace
POST /input/trace/windows/start
# Send a test key
POST /input/key {"keys": "Test", "window_title": "Notepad"}
# Query Windows trace for the key
GET /input/events?source=windows&origin=agent&limit=50
# Look for key_down/key_up events with matching trace_id
```

### Input latency investigation

```bash
# Start all trace layers
scripts/diagnostics/diagnose-input-trace.sh --layers x11,windows
# Send several keystrokes
scripts/winebotctl input key "test1"
scripts/winebotctl input key "test2"
# Analyze latency
python3 scripts/diagnostics/analyze-trace-latency.py --mode keyboard
```

See [docs/tracing.md](docs/tracing.md) for the full trace event schema and cross-layer
correlation guide.

## 8. Window Identification Systems

WineBot has two distinct window ID systems that do **not** map to each other:

| System | Source | Example | Used By |
|:---|:---|:---|:---|
| **X11 Window IDs** | `xdotool search --name "Title"` | `23068673` (decimal) | `/input/mouse/click`, `xdotool key`, `GET /health/windows` |
| **Wine HWNDs** | AHK `WinExist("Title")` | `0x160034` (hex) | `/input/key` (AHK backend) via native title matching |

**Rule:** When calling `/input/key` with a `window_title`, the AHK backend uses
AHK's native `WinActivate/WinWaitActive` with the title string — NOT the X11 ID.
This is correct because X11 window IDs are not AHK HWNDs and cannot be used
with `ahk_id`.

When calling `/input/mouse/click`, the xdotool backend uses X11 window IDs,
which ARE correct for X11-level operations.

To discover window titles:
```bash
GET /health/windows   # Returns X11 IDs and titles for all windows
```

To target a specific window in a script, use its **title** (visible in the window list),
not its numeric ID. The API resolves the title to the correct system internally.

### Cross-system coordination

In scripts and agents that use both mouse and keyboard:
1. **Get window list** via `GET /health/windows` — titles are the source of truth
2. **Mouse clicks**: Use `window_title` from the window list (xdotool resolves to X11 ID)
3. **Keyboard input**: Use the same `window_title` (AHK resolves by Wine title matching)
4. **Dialogs**: After launching a dialog (Save As, Open), switch window_title to the
   dialog's title. Example: `"Save As"` not `"Notepad"` after Ctrl+S opens the save dialog.

**See [docs/known-limitations.md](docs/known-limitations.md) for the full catalog of platform constraints**
including comdlg32 dialog keyboard limitations, AHK Send character escaping rules,
`/run/python` Linux vs Windows behavior, and tool selection guidance.

