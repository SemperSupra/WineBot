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

## Control Surfaces

WineBot provides two primary CLI tools for interaction, depending on your role:

### 1. Developer Tooling (`scripts/wb`)
Used for project maintenance and verification on the **host machine**:
- **Unified Lifecycle:** `./scripts/wb` wraps Docker Compose profiles (`lint`, `test`, `interactive`) to ensure a consistent environment across development stages.
- **Bootstrapping:** Automated host dependency checks (Docker, Compose).
- **Vulnerability Scanning:** Integrated Trivy scans for both the local filesystem and container images.
- **Build Intents:** Automated image building for different use cases (`dev`, `test`, `slim`, `rel`).

### 2. Operator Interface (`scripts/winebotctl`)
The primary interface for autonomous agents and remote operators to **control a running instance**:
- **API-First:** Communicates with a running WineBot instance via HTTP.
- **Portability:** Lightweight shell script that can be vendored into other environments without the full build system.
- **Idempotency:** Optional caching for idempotent API calls.

## Configuration & Defaults

WineBot eliminates "magic values" by centralizing all settings in `api/utils/config.py`.

- **Validation**: All environment variables are validated via Pydantic on API startup.
- **Fail-Fast**: The system refuses to boot if critical configuration (e.g., ports, timeouts) is malformed.
- **Agent Friendly**: Agents can discover the current configuration schema via the `GET /handshake` endpoint.

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
