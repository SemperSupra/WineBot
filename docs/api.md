# WineBot Internal API

WineBot includes an internal HTTP API to facilitate programmatic control from within the container or (if ports are mapped) from the host.

**Base URL:** `http://localhost:8000`

## Security

### Authentication
To secure the API, set the `API_TOKEN` environment variable. All requests must then include the token in the header:
- **Header:** `X-API-Key: <your-token>`

If `API_TOKEN` is not set, the API is open (not recommended for shared environments).

### Path Safety
Endpoints accepting file paths (`/apps/run`) are restricted to specific directories to prevent traversal attacks. Absolute paths must start with an allowed prefix. "Naked" filenames (no separators) are allowed and assumed to be in the Wine search path.

Allowed prefixes:
- `/apps`
- `/wineprefix`
- `/tmp`
- `/artifacts`
- `/opt/winebot`
- `/usr/bin`

## Unified CLI

Use `scripts/winebotctl` for a single CLI entrypoint to the API.

Examples:
- `scripts/winebotctl health`
- `scripts/winebotctl sessions list`
- `scripts/winebotctl recording start --session-root /artifacts/sessions`
- `scripts/winebotctl api POST /sessions/suspend --json '{"shutdown_wine":true}'`

Idempotent mode is supported (see `--idempotent` / `--no-idempotent`) so repeat invocations can safely reuse the same response when desired.

## Versioning and Compatibility

WineBot publishes explicit API and artifact/event schema versions.

- HTTP responses include:
  - `X-WineBot-API-Version`
  - `X-WineBot-Build-Version`
  - `X-WineBot-Artifact-Schema-Version`
  - `X-WineBot-Event-Schema-Version`
- `GET /version` returns the same values as JSON fields.
- `session.json`, `segment_*.json`, and JSONL event streams include `schema_version`.
- Readers default missing `schema_version` to `1.0` for backward compatibility with older artifacts.

## Endpoints

### Quick Reference
| Method | Path | Purpose |
| --- | --- | --- |
| GET | `/health` | High‑level health summary |
| GET | `/health/system` | System stats |
| GET | `/health/x11` | X11 status |
| GET | `/health/windows` | X11 window list |
| GET | `/health/wine` | Wine prefix details |
| GET | `/health/tools` | Tool availability |
| GET | `/health/storage` | Storage stats |
| GET | `/health/recording` | Recorder status |
| GET | `/lifecycle/status` | Lifecycle status for core components |
| GET | `/lifecycle/events` | Recent lifecycle events |
| POST | `/lifecycle/shutdown` | Gracefully stop the container |
| POST | `/openbox/reconfigure` | Reload Openbox config |
| POST | `/openbox/restart` | Restart Openbox |
| GET | `/sessions` | List session directories |
| POST | `/sessions/suspend` | Suspend a session (keep container alive) |
| POST | `/sessions/resume` | Resume a session directory |
| GET | `/ui` | noVNC + API dashboard UI |
| GET | `/windows` | List visible windows |
| POST | `/windows/focus` | Focus a window |
| POST | `/input/mouse/click` | Click at coordinates |
| POST | `/apps/run` | Run a Windows app |
| GET | `/screenshot` | Capture screenshot (metadata sidecar + header) |
| POST | `/recording/start` | Start recording session |
| POST | `/recording/pause` | Pause recording session |
| POST | `/recording/resume` | Resume recording session |
| POST | `/recording/stop` | Stop recording session |
| GET | `/recording/perf/summary` | Summarize recording performance metrics |
| POST | `/run/ahk` | Run AutoHotkey script |
| POST | `/run/autoit` | Run AutoIt script |
| POST | `/run/python` | Run Windows Python |
| POST | `/inspect/window` | WinSpy‑style inspection |

### Health & State

#### `GET /health`
High-level health summary (X11, Wine prefix, tools, storage).
- **Response:** `{"status": "ok", "x11": "connected", "wineprefix": "ready", "tools_ok": true, "security_warning": "...", ...}`
- **Security Warning:** Reports if VNC is exposed on a public IP or running without a password.

#### `GET /health/system`
System stats (uptime, load average, CPU count, memory).

#### `GET /health/x11`
X11/display status and active window.

#### `GET /health/windows`
Window list and active window details.

#### `GET /health/wine`
Wine prefix status and `wine --version`.

#### `GET /health/tools`
Presence/paths of key tools (`winedbg`, `gdb`, `ffmpeg`, etc).

#### `GET /health/storage`
Disk space and writeability for `/wineprefix`, `/artifacts`, and `/tmp`.

#### `GET /health/recording`
Recorder status and current session info (if any).

#### `GET /lifecycle/status`
Status for core WineBot components (Xvfb, Openbox, VNC/noVNC, recorder, etc).
- **Response:** includes `session_id`, `session_dir`, `user_dir`, `processes`, and `lifecycle_log`.

#### `GET /lifecycle/events`
Return recent lifecycle events.
- **Parameters:**
  - `limit` (optional): Max events to return (default: 100).
- **Response:** `{"events":[ ... ]}`

#### `POST /lifecycle/shutdown`
Gracefully stop the recorder and UI components, shut down Wine, and terminate the container process.
- **Parameters:**
  - `delay` (optional): Seconds to wait before terminating (default: 0.5).
  - `wine_shutdown` (optional): Whether to run `wineboot --shutdown` and `wineserver -k` before exiting (default: true).
  - `power_off` (optional): Immediately terminate the container (unsafe; skips graceful shutdown).
- **Response:** `{"status":"shutting_down","delay_seconds":0.5,"wine_shutdown":{...},"component_shutdown":{...}}`

#### `POST /openbox/reconfigure`
Reload the Openbox configuration.
- **Response:** `{"status":"ok","action":"reconfigure","result":{...}}`

#### `POST /openbox/restart`
Restart the Openbox window manager.
- **Response:** `{"status":"ok","action":"restart","result":{...}}`

#### `GET /sessions`
List session directories in the session root.
- **Parameters:**
  - `root` (optional): Override session root (default: `/artifacts/sessions`).
  - `limit` (optional): Max sessions to return (default: 100).
- **Response:** `{"root":"...","sessions":[...]}`

#### `POST /sessions/suspend`
Suspend a session without terminating the container.
- **Body (JSON):**
  - `session_id` or `session_dir` (optional): Target session (default: current).
  - `session_root` (optional): Session root when using `session_id`.
  - `shutdown_wine` (optional): Stop Wine services (default: true).
  - `stop_recording` (optional): Stop active recording (default: true).

#### `POST /sessions/resume`
Resume an existing session directory.
- **Body (JSON):**
  - `session_id` or `session_dir` (required).
  - `session_root` (optional): Session root when using `session_id`.
  - `restart_wine` (optional): Restart Wine services (default: true).
  - `stop_recording` (optional): Stop active recording before switching (default: true).

### Dashboard

#### `GET /ui`
Serve the built‑in dashboard (noVNC + API controls). If `API_TOKEN` is set, enter it in the UI to authenticate API requests.
- Includes lifecycle controls (graceful shutdown and power off), component status badges, and an activity log console.

#### `GET /windows`
List currently visible windows.
- **Response:**
  ```json
  {
    "windows": [
      {"id": "0x123456", "title": "Untitled - Notepad"},
      ...
    ]
  }
  ```

### Vision

#### `GET /screenshot`
Capture a screenshot via `/automation/screenshot.sh`.
- **Parameters:**
  - `output_dir` (optional): Override output directory. If omitted, the session screenshots directory is used.
- **Response:** PNG image file.
  - **Headers:** `X-Screenshot-Path` (saved path inside container)
  - **Default storage:** If no session exists, `/tmp` is used.

#### `POST /recording/start`
Start a recording session.
- **Body (optional):**
  ```json
  {
    "session_label": "smoke",
    "session_root": "/artifacts/sessions",
    "display": ":99",
    "resolution": "1920x1080",
    "fps": 30,
    "new_session": false
  }
  ```
- **Response:** `{"status":"started","session_id":"...","session_dir":"...","segment":1,"output_file":"...","events_file":"..."}`
If a session already exists and `new_session` is false, each start creates a new numbered segment in the same session directory.

#### `POST /recording/pause`
Pause the active recording session.
- **Response:** `{"status":"paused","session_dir":"..."}`

#### `POST /recording/resume`
Resume the active recording session.
- **Response:** `{"status":"resumed","session_dir":"..."}`

#### `POST /recording/stop`
Stop the active recording session.
- **Response:** `{"status":"stopped","session_dir":"..."}`

#### `GET /recording/perf/summary`
Summarize metrics from `logs/perf_metrics.jsonl` for a session.
- **Parameters (optional):**
  - `session_id`
  - `session_dir`
  - `session_root` (used with `session_id`)
- **Response:** includes `metrics` keyed by metric name with percentile stats (`count`, `min_ms`, `mean_ms`, `p50_ms`, `p90_ms`, `p95_ms`, `p99_ms`, `max_ms`).

### Control

#### `POST /windows/focus`
Focus a specific window.
- **Body:** `{"window_id": "0x123456"}`
- **Response:** `{"status": "focused", "id": "..."}`

#### `POST /input/mouse/click`
Click at specific coordinates.
- **Body:** 
  ```json
  {
    "x": 100, 
    "y": 200, 
    "button": 1, 
    "window_title": "Notepad", 
    "relative": true
  }
  ```
- **Response:** `{"status": "clicked", "trace_id": "...", ...}`
- **Notes:** Supports relative clicking if `window_title` is provided and `relative` is true. Clicks are validated against the current `SCREEN` resolution if not relative.

#### `GET /input/trace/status`
Get input trace status for the active session.
- **Response:** `{"running": true, "pid": 123, "state": "running", "log_path": "...", ...}`

#### `POST /input/trace/start`
Start input tracing (mouse motion, clicks, keypresses).
- **Body (optional):**
  ```json
  {
    "include_raw": false,
    "motion_sample_ms": 0
  }
  ```
- **Response:** `{"status": "started", "pid": 123, "log_path": "..."}`

#### `POST /input/trace/stop`
Stop input tracing.
- **Response:** `{"status": "stopped", "session_dir": "..."}`

#### `GET /input/trace/x11core/status`
Get X11 core input trace status (xinput test).
- **Response:** `{"running": true, "pid": 123, "state": "running", "log_path": "...", ...}`

#### `POST /input/trace/x11core/start`
Start X11 core input tracing.
- **Body (optional):**
  ```json
  {
    "motion_sample_ms": 10
  }
  ```
- **Response:** `{"status": "started", "pid": 123, "log_path": "..."}`

#### `POST /input/trace/x11core/stop`
Stop X11 core input tracing.
- **Response:** `{"status": "stopped", "session_dir": "..."}`

#### `GET /input/trace/client/status`
Get client (noVNC) input trace status.
- **Response:** `{"enabled": true, "log_path": "...", ...}`

#### `POST /input/trace/client/start`
Enable client (noVNC) input trace collection.
- **Response:** `{"status":"enabled","log_path":"..."}`

#### `POST /input/trace/client/stop`
Disable client (noVNC) input trace collection.
- **Response:** `{"status":"disabled","session_dir":"..."}`

#### `POST /input/client/event`
Ingest a client (noVNC UI) input event.
- **Body:** arbitrary JSON fields for the event.
- **Response:** `{"status":"ok"}` (or `{"status":"ignored"}` when disabled).

#### `GET /input/trace/windows/status`
Get Windows-side input trace status.
- **Response:** `{"running": true, "pid": 123, "state": "running", "backend": "hook", "log_path": "...", ...}`

#### `POST /input/trace/windows/start`
Start Windows-side input tracing.
- **Body (optional):**
  ```json
  {
    "motion_sample_ms": 10,
    "debug_keys": ["vk41", "LButton"],
    "debug_keys_csv": "vk41,LButton",
    "debug_sample_ms": 200,
    "backend": "auto"
  }
  ```
- **Notes:** `backend` may be `auto`, `ahk`, or `hook`. `hook` uses the low-level Windows hook observer; `ahk` uses AutoHotkey.
- **Response:** `{"status":"started","pid":123,"log_path":"...","backend":"hook"}`

#### `POST /input/trace/windows/stop`
Stop Windows-side input tracing.
- **Response:** `{"status":"stopped","session_dir":"..."}`

#### `GET /input/trace/network/status`
Get network input trace status (VNC proxy).
- **Response:** `{"running": true, "pid": 123, "state": "enabled", "log_path": "...", ...}`

#### `POST /input/trace/network/start`
Enable network input trace logging (proxy must be running).
- **Response:** `{"status":"enabled","session_dir":"..."}`

#### `POST /input/trace/network/stop`
Disable network input trace logging (proxy must be running).
- **Response:** `{"status":"disabled","session_dir":"..."}`

#### `GET /input/events`
Return recent input trace events.
- **Query params:** `limit` (default 200), `since_epoch_ms` (optional), `source` (`client`, `x11_core`, `windows`, `network`, or default X11 trace file)
- **Response:** `{"events":[...], "log_path":"..."}`
Each event includes `origin` (`user`/`agent`/`unknown`) and `tool` when known.

#### `POST /apps/run`
Run a Windows application.
- **Body:**
  ```json
  {
    "path": "C:/Program Files/App/App.exe",
    "args": "-debug",
    "detach": true
  }
  ```
- **Response (Finished):**
  ```json
  {
    "status": "finished",
    "stdout": "...",
    "stderr": "..."
  }
  ```
- **Response (Failed):**
  ```json
  {
    "status": "failed",
    "exit_code": 1,
    "stdout": "...",
    "stderr": "..."
  }
  ```
- **Response (Detached):** `{"status":"detached","pid":...}`

### Automation

#### `POST /run/ahk`
Run an AutoHotkey script.
- **Body:**
  ```json
  {
    "script": "MsgBox, Hello from API"
  }
  ```
- **Response:** `{"status": "ok", "stdout": "..."}`

#### `POST /run/autoit`
Run an AutoIt v3 script.
- **Body:**
  ```json
  {
    "script": "MsgBox(0, 'Title', 'Hello from API')"
  }
  ```
- **Response:** `{"status": "ok", "stdout": "..."}`

#### `POST /run/python`
Run a Python script using the embedded Windows Python environment (`winpy`).
- **Body:** `{"script": "import sys; print(sys.version)"}`
- **Response:** `{"status": "ok", "stdout": "..."}`

#### `POST /inspect/window`
Inspect a Windows window and its controls (WinSpy-style) via AutoIt.
- **Body (inspect by title or handle):**
  ```json
  {
    "title": "Untitled - Notepad",
    "text": "",
    "handle": "",
    "include_controls": true,
    "max_controls": 200
  }
  ```
- **Body (list windows):**
  ```json
  {
    "list_only": true,
    "include_empty": false
  }
  ```
- **Response:** `{"status": "ok", "details": {}}` (current implementation returns a placeholder payload).

## Usage

To enable the API server, set `ENABLE_API=1` when starting the container. For security, also set `API_TOKEN`.

```bash
ENABLE_API=1 API_TOKEN=mysecret docker compose up
```

You can then interact with it via `curl` or any HTTP client inside the container or mapped host port.

```bash
curl -H "X-API-Key: mysecret" http://localhost:8000/health
```

### Auth-Protected Host Testing
If you expose port 8000 (see `compose/docker-compose.yml`) and set `API_TOKEN`, you can test from the host:

```bash
API_TOKEN=mysecret docker compose -f compose/docker-compose.yml --profile headless up -d
API_TOKEN=mysecret ./scripts/winebotctl health
API_TOKEN=mysecret ./scripts/winebotctl health system
```
