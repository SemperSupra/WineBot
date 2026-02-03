# WineBot Internal API

WineBot includes an internal HTTP API to facilitate programmatic control from within the container or (if ports are mapped) from the host.

**Base URL:** `http://localhost:8000`

## Security

### Authentication
To secure the API, set the `API_TOKEN` environment variable. All requests must then include the token in the header:
- **Header:** `X-API-Key: <your-token>`

If `API_TOKEN` is not set, the API is open (not recommended for shared environments).

### Path Safety
Endpoints accepting file paths (`/apps/run`) are restricted to specific directories to prevent traversal attacks. Allowed prefixes:
- `/apps`
- `/wineprefix`
- `/tmp`

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
| GET | `/sessions` | List session directories |
| POST | `/sessions/suspend` | Suspend a session (keep container alive) |
| POST | `/sessions/resume` | Resume a session directory |
| GET | `/ui` | noVNC + API dashboard UI |
| GET | `/windows` | List visible windows |
| GET | `/windows/active` | Active window ID |
| GET | `/windows/search` | Search windows by name |
| POST | `/windows/focus` | Focus a window |
| POST | `/input/mouse/click` | Click at coordinates |
| GET | `/apps` | List installed apps |
| POST | `/apps/run` | Run a Windows app |
| GET | `/screenshot` | Capture screenshot (metadata sidecar + header) |
| POST | `/recording/start` | Start recording session |
| POST | `/recording/pause` | Pause recording session |
| POST | `/recording/resume` | Resume recording session |
| POST | `/recording/stop` | Stop recording session |
| POST | `/run/ahk` | Run AutoHotkey script |
| POST | `/run/autoit` | Run AutoIt script |
| POST | `/run/python` | Run Windows Python |
| POST | `/inspect/window` | WinSpy‑style inspection |
| POST | `/run/winedbg` | Launch app under winedbg |

### Health & State

#### `GET /health`
High-level health summary (X11, Wine prefix, tools, storage).
- **Response:** `{"status": "ok", "x11": "connected", "wineprefix": "ready", "tools_ok": true, ...}`

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
- Includes lifecycle controls (graceful shutdown and power off), component status badges, and recent lifecycle events.

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

#### `GET /windows/active`
Get the ID of the currently active/focused window.
- **Response:** `{"id": "0x123456"}`

#### `GET /windows/search`
Search for windows by name pattern (regex-like).
- **Parameters:** `name` (required)
- **Response:** `{"matches": ["0x123", "0x456"]}`

#### `GET /apps`
List installed applications in the Wine prefix.
- **Parameters:** `pattern` (optional) - Filter by name.
- **Response:** `{"apps": ["App.exe", ...]}`

### Vision

#### `GET /screenshot`
Capture a screenshot of the desktop or a specific window.
- **Parameters:**
  - `window_id` (optional): Window ID (default: "root").
  - `delay` (optional): Seconds to wait before capture (default: 0).
  - `label` (optional): Text to annotate at the bottom of the image.
  - `tag` (optional): User tag stored in screenshot metadata.
  - `session_root` (optional): Session root to use when creating a session for screenshots (default: `/artifacts/sessions`).
  - `output_dir` (optional): Override output directory (advanced; if provided, screenshots are written there instead of the session’s `screenshots/` directory). Allowed: `/apps`, `/wineprefix`, `/tmp`, `/artifacts`.
- **Response:** PNG image file.
  - **Headers:** `X-Request-Id` (unique request ID)
  - **Headers:** `X-Screenshot-Path` (saved path inside container)
  - **Headers:** `X-Screenshot-Metadata-Path` (saved metadata JSON path)
  - **Sidecar:** A JSON file is written alongside the PNG (`<file>.png.json`) containing metadata.
  - **Default storage:** If `output_dir` is not provided, screenshots are stored under `<session_dir>/screenshots`. If no session exists, one is created under `session_root`.

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

### Control

#### `POST /windows/focus`
Focus a specific window.
- **Body:** `{"window_id": "0x123456"}`
- **Response:** `{"status": "focused", "id": "..."}`

#### `POST /input/mouse/click`
Click at specific coordinates.
- **Body:** `{"x": 100, "y": 200}`
- **Response:** `{"status": "clicked", ...}`

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
- **Response:** `{"status": "launched", ...}`

### Automation

#### `POST /run/ahk`
Run an AutoHotkey script.
- **Body:**
  ```json
  {
    "script": "MsgBox, Hello from API",
    "focus_title": "Notepad" // Optional: Focus this window before running
  }
  ```
- **Response:** `{"status": "success", "log": "..."}`
- **Artifacts:** Script and logs are stored under the current session (`<session_dir>/scripts` and `<session_dir>/logs`).

#### `POST /run/autoit`
Run an AutoIt v3 script.
- **Body:**
  ```json
  {
    "script": "MsgBox(0, 'Title', 'Hello from API')",
    "focus_title": "Notepad"
  }
  ```
- **Response:** `{"status": "success", "log": "..."}`
- **Artifacts:** Script and logs are stored under the current session (`<session_dir>/scripts` and `<session_dir>/logs`).

#### `POST /run/python`
Run a Python script using the embedded Windows Python environment (`winpy`).
- **Body:** `{"script": "import sys; print(sys.version)"}`
- **Response:** `{"status": "success", "stdout": "...", "stderr": "...", "log_path": "..."}`
- **Artifacts:** Script and logs are stored under the current session (`<session_dir>/scripts` and `<session_dir>/logs`).

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
- **Response:** `{"status": "success", "result": { ... }}`
- **Artifacts:** Logs are stored under the current session (`<session_dir>/logs`).

#### `POST /run/winedbg`
Run a Windows app under `winedbg` (gdb proxy or command mode).
- **Body:**
  ```json
  {
    "path": "/apps/MyApp.exe",
    "args": "-debug",
    "detach": true,
    "mode": "gdb",
    "port": 2345,
    "no_start": true
  }
  ```
- **Command mode example:**
  ```json
  {
    "path": "/apps/MyApp.exe",
    "mode": "default",
    "command": "info proc"
  }
  ```
- **Response:** `{"status": "launched", "path": "...", "mode": "gdb"}`

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
API_TOKEN=mysecret docker-compose -f compose/docker-compose.yml --profile headless up -d
API_TOKEN=mysecret ./scripts/health-check.sh --all
```
