# Architecture

WineBot runs Windows GUI applications inside a Linux container using Wine, Xvfb, and a lightweight window manager. It exposes an HTTP API for programmatic control.

## System Layers

1.  **Application Layer (Windows)**
    *   Target Application (`.exe`)
    *   Automation Tools (`AutoHotkey`, `AutoIt`, `Python/winpy`)
    *   Running inside `WINEPREFIX` (`/wineprefix`)

2.  **Display Layer (X11)**
    *   `Xvfb`: Virtual framebuffer (Display `:99`).
    *   `openbox`: Window manager for geometry management.
    *   `x11vnc` / `noVNC`: Optional interactive viewing.

3.  **Control Layer (Linux/Container)**
    *   **API Server (`api/server.py`):** FastAPI service on port 8000. Orchestrates automation.
    *   **Helper Scripts (`scripts/`, `automation/`):** Shell wrappers for X11 and Wine interactions.
    *   **Entrypoint (`entrypoint.sh`):** Bootstraps user permissions, X11, Wine, and API.

## API & Automation Flow

External Agents -> HTTP API (8000) -> `api/server.py` -> Shell Helpers -> `wine`/`xdotool`/`import` -> Application

## Startup Flow

1.  **Entrypoint:** Sets up `winebot` user (UID mapping).
2.  **X11:** Starts `Xvfb` and `openbox`.
3.  **Services:** Starts optional VNC/noVNC.
4.  **API:** Starts `uvicorn` (if `ENABLE_API=1`).
5.  **Wine:** Initializes prefix (`wineboot`) if needed.
6.  **App:** Launches target executable (if configured).

## Persistence

-   **`/wineprefix`:** Persistent Wine environment (C: drive).
-   **`/apps`:** Read-only mount for installers/executables.
-   **`/automation`:** Scripts and assets.