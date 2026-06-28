# Architecture

WineBot runs Windows GUI applications inside a Linux container using Wine, Xvfb, and a lightweight window manager. It exposes an HTTP API for programmatic control.

## Base Image Selection

Choosing the correct base image is critical for supporting modern versions of Wine while maintaining container best practices. The following options were evaluated:

*   **Ubuntu LTS + WineHQ Repository:** While this provides access to the latest Wine versions, Ubuntu images are larger, and relying on third-party repositories introduces build-time failure risks (e.g., repository downtime or GPG key changes).
*   **Alpine Linux:** Offers the smallest possible footprint. However, Alpine uses `musl` libc instead of `glibc`. Wine heavily relies on `glibc`, making Alpine highly incompatible and requiring complex, fragile workarounds.
*   **Arch Linux:** Provides native, bleeding-edge packages without external repositories. However, rolling releases lack the stability required for predictable CI/CD pipelines and production container runtimes.
*   **Debian Stable + WineHQ / Backports:** Provides a rock-solid base, but backports often lag behind the latest Wine releases, and using WineHQ reintroduces third-party dependency risks.

**Final Decision:** WineBot uses a **minimal Debian Trixie (Testing) base** (`debian:trixie-slim`) layered with specific requirements. This approach was chosen because it:
1.  **Provides Modern Wine:** Access to recent Wine versions directly from native Debian repositories without third-party repos.
2.  **Maintains Minimal Size:** The slim variant keeps the base layer small.
3.  **Ensures High Compatibility:** Full `glibc` support ensures standard behavior for Wine and Windows applications.
4.  **Is Future-Proof:** Using the upcoming stable release prepares the project for the future without major migrations.

## System Layers

1.  **Application Layer (Windows)**
    *   Target Application (`.exe`)
    *   Automation Tools (`AutoHotkey`, `AutoIt`, `Python/winpy`)
    *   Running inside `WINEPREFIX` (`/wineprefix`)

2.  **Display Layer (X11)**
    *   `Xvfb`: Virtual framebuffer (Display `:99`). **2D rendering only** — no GPU, no
        hardware-accelerated OpenGL, no Vulkan support. All rendering is done in software
        via the CPU. Applications requiring 3D/GL/Direct3D will fail or fall back to
        unusably slow software rendering. This is an architectural constraint of Xvfb,
        not a configuration gap. See `docs/known-limitations.md#22-no-hardware-acceleration-in-headless-mode`.
    *   `openbox`: Window manager for geometry management.
    *   `x11vnc` / [`noVNC`](https://novnc.com) / [`websockify`](https://github.com/novnc/websockify): Optional interactive viewing.

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

2.  **Infrastructure:** Starts `Xvfb`, [`openbox`](http://openbox.org), and [`tint2`](https://gitlab.com/o9000/tint2).

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

---

## Sidecar Architecture

WineBot's computer vision, OCR, and ML capabilities are provided by **sidecar containers** —
separate Docker images that communicate with the core WineBot container over HTTP.
This separation keeps the core image small, GPU-agnostic, and focused on Wine automation.

### Sidecar Landscape

| Sidecar | Repo | Port | GPU | Status |
|:---|:---|:---|:---|:---|
| **CV/OCR** | [`github.com/sempersupra/desktop-ui-cv`](https://github.com/sempersupra/desktop-ui-cv) (private) | 8001 | Optional (GPU image available) | ✅ Active — phases 1-3 complete |
| **Captioning** | `github.com/sempersupra/ui-captioning` (planned) | 8002 | Required | 📅 Planned |
| **KV-Ground-8B** | `github.com/sempersupra/kv-ground-server` (planned) | 8003/8004 | Required | 🚧 TrueNAS deployment active, repo extraction planned |

### CV/OCR Sidecar (`winebot-cv`)

**Python package:** `desktop-ui-cv` — provides `winebot_cv` module with detectors, OCR, CLIP embedding, model registry, and GT dataset generator.

**Server:** `desktop-ui-cv[server]` extra — FastAPI application with endpoints:
- `GET /health` — liveness check
- `POST /analyze` — UI element detection + OCR on a single image
- `POST /batch` — batch analysis of video frames
- `POST /describe` — natural language scene description
- `POST /ground` — natural language element grounding

**Image variants:**
- `Dockerfile.cv-analyzer` — CPU-only, Tesseract + OpenCV baseline
- `Dockerfile.cv-analyzer-gpu` — GPU-accelerated, PyTorch + YOLO + CLIP + Florence-2

**Integration:** Core WineBot calls sidecar via HTTP at `http://winebot-cv:8001`. The sidecar URL is configured via `INFRA_WINEBOT_SIDECAR_URL`.

### Repo Separation Plan

The sidecar code is being extracted from the WineBot monorepo into independent repositories:

```
Phase 1-2: ✅ Package skeleton + engines moved to packages/desktop-ui-cv/
Phase 3:   ✅ Sidecar server imports from the package
Phase 4:   🔄 CI/CD pipeline for the package
Phase 5:   📅 Extract to github.com/sempersupra/desktop-ui-cv (tag v0.1.0)
Phase 6:   📅 Extract kv-ground-server to its own repo
Phase 7:   📅 Extract captioning sidecar to its own repo
```

### Naming Convention

| Artifact | Name |
|:---|:---|
| GitHub org | `sempersupra` (private repos initially) |
| CV/OCR repo | `desktop-ui-cv` |
| Python package | `desktop-ui-cv` (import as `winebot_cv`) |
| Server extra | `desktop-ui-cv[server]` |
| Docker image | `ghcr.io/sempersupra/desktop-ui-cv-sidecar` |
| KV-Ground repo | `kv-ground-server` |
| Captioning repo | `ui-captioning` |

### Design Principles

1. **API-first:** Sidecars communicate via stable HTTP APIs. Consumers (WineBot, WinBot, research scripts) never import the package directly — they call the API.
2. **Independent release cycles:** Each sidecar has its own CI/CD, version tag, and image registry.
3. **GPU optional:** The CV sidecar has CPU and GPU image variants. GPU is never required for core WineBot functionality.
4. **Private then public:** Repos start private for controlled maturation, then release publicly when stable.
