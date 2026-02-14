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

2.  **Infrastructure:** Starts `Xvfb`, `openbox`, and `tint2`.

3.  **Wine Initialization:**

    *   If the prefix is empty, it is populated from a **pre-initialized build-time template** (`/opt/winebot/prefix-template`).

    *   This reduces startup time by ~60s and ensures theme/registry consistency.

4.  **Services:** Starts the API server, recording services, and the Desktop Supervisor.

5.  **Application Launch:** If `APP_EXE` is set, the entrypoint executes the application, capturing CLI output or supporting GUI automation.



## Persistence & Data Model



-   **`/wineprefix`:** Persistent Wine registry and system-wide settings.

-   **`/artifacts`:** Persistent storage for all session data (logs, videos, screenshots).

-   **User Profiles:** At session start/resume, the Windows user profile (`C:\users\winebot`) is dynamically symlinked to a sub-folder within the persistent `/artifacts` directory. This ensures that application data (AppData, Desktop, Documents) persists across sessions even if the container is recreated.

-   **`/apps`:** Volume for external Windows executables and installers.
