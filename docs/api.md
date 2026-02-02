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

### Health & State

#### `GET /health`
Checks if X11 and Wine environment are responsive.
- **Response:** `{"status": "ok", "x11": "connected"}`

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
- **Response:** PNG image file.

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

#### `POST /run/python`
Run a Python script using the embedded Windows Python environment (`winpy`).
- **Body:** `{"script": "import sys; print(sys.version)"}`
- **Response:** `{"status": "success", "stdout": "...", "stderr": "..."}`

## Usage

To enable the API server, set `ENABLE_API=1` when starting the container. For security, also set `API_TOKEN`.

```bash
ENABLE_API=1 API_TOKEN=mysecret docker compose up
```

You can then interact with it via `curl` or any HTTP client inside the container or mapped host port.

```bash
curl -H "X-API-Key: mysecret" http://localhost:8000/health
```
