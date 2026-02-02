# AGENTS.md — WineBot Agent Guide

This document is the definitive guide for autonomous agents (LLMs, scripts, CI runners) interacting with WineBot.

## 1. Primary Interface: HTTP API

The preferred method for agents to control WineBot is via the internal HTTP API (port 8000).

**Base URL:** `http://localhost:8000` (inside container) or mapped port.

### Capabilities
- **Vision:** `GET /screenshot` (returns PNG)
- **State:** `GET /windows` (list open windows), `GET /health`
- **Control:** `POST /input/mouse/click`, `POST /windows/focus`
- **Automation:** `POST /run/ahk`, `POST /run/autoit`, `POST /run/python`
- **Management:** `POST /apps/run`, `GET /apps`

### Authentication
If `API_TOKEN` is set in the container environment, you MUST provide it:
- **Header:** `X-API-Key: <your-token>`

### Example Workflow (Agent)
1. **Launch App:** `POST /apps/run` `{"path": "notepad.exe", "detach": true}`
2. **Verify:** `GET /windows/search?name=Notepad` -> returns ID.
3. **Focus:** `POST /windows/focus` `{"window_id": "..."}`
4. **Interact:** `POST /run/ahk` `{"script": "Send, Hello World"}`
5. **Verify:** `GET /screenshot` -> Analyze image.

See `docs/api.md` for the full OpenAPI specification.

---

## 2. Secondary Interface: CLI Tools

If direct shell access (`docker exec`) is preferred, use the optimized helper scripts.

### X11 & Vision
- **Inspection:** `/automation/x11.sh list-windows` (IDs + Titles)
- **Search:** `/automation/x11.sh search --name "Pattern"`
- **Focus:** `/automation/x11.sh focus <id>`
- **Click:** `/automation/x11.sh click-at <x> <y>`
- **Screenshot:** `/automation/screenshot.sh /tmp/out.png` (Supports `--window`, `--label`)

### Execution
- **AutoHotkey:** `/scripts/run-ahk.sh script.ahk` (Handles Wine bootstrapping automatically)
- **AutoIt:** `/scripts/run-autoit.sh script.au3`
- **App Launch:** `/scripts/run-app.sh "C:/Path/To/App.exe"`

---

## 3. Deployment Strategy for Agents

### Docker Compose (Recommended)
Use the provided `docker-compose.yml` to spin up the environment.
- **Headless:** Use `profile: headless` for background tasks.
- **Environment:** Set `API_TOKEN` for security.

### Troubleshooting
- **No Windows?** Check `GET /health`. Ensure `wine explorer` or the app is running.
- **Input fails?** Ensure the window is focused (`POST /windows/focus`).
- **Crashes?** Check container logs or use `/run/ahk` logging.

---

## 4. Development & Extension

If you (the Agent) need to extend WineBot:
1. **Python:** Add dependencies to `Dockerfile` (`pip install ...`).
2. **API:** Extend `api/server.py` (FastAPI).
3. **Scripts:** Add bash helpers to `scripts/` (ensure `chmod +x`).
4. **Validation:** ALWAYS run `scripts/smoke-test.sh` after changes.