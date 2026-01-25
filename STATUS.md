# Status

## Current state
- **Project Version:** v0.4 (Latest stable release).
- **GitHub Workflow:** Healthy. Latest build `21336011965` passed all smoke tests and published to GHCR.
- **Entrypoint:** Robust pass-through execution, host UID/GID mapping, and full `winedbg` support (gdb proxy and command modes) implemented.
- **Windows Automation:** AutoIt v3, AutoHotkey v1.1 (fixed download source), and Python 3.11 (embedded) integrated and available in PATH.
- **Security:** Critical vulnerabilities managed; `wheel` upgraded in Windows Python; `.trivyignore` used for persistent vendored issues.
- **Screenshots:** `automation/screenshot.sh` generates timestamped filenames; `scripts/smoke-test.sh` correctly validates them.
- **Persistence:** Wine prefix persistence via Docker volumes verified.

## Validation so far
- `scripts/smoke-test.sh --full` successfully validates:
    - Headless Xvfb/Openbox lifecycle.
    - Notepad automation (launch, type, save, and content verification).
    - winedbg `info proc` command execution.
    - winedbg gdb proxy availability and connectivity.
    - Screenshot generation and storage.
    - Persistent storage across container restarts.
- `scripts/smoke-test.sh --include-interactive` successfully validates:
    - VNC (5900) and noVNC (6080) service startup and port accessibility.
- GHCR image `ghcr.io/mark-e-deyoung/winebot:latest` is published and verified.

## Known quirks
- `docker-compose` v1 may error with `ContainerConfig` on recreate; remove the old container with `docker-compose ... rm -f -s` and re-run `up`.
- gdb may exit with code `137` in some container environments; treat it as valid if thread output is present.
- `automation/find_and_click.py` will return exit code `2` until a real template matches visible UI.

## Next steps (pick up here)
1. Install and run real-world Windows applications using `scripts/install-app.sh` and `scripts/run-app.sh`.
2. Develop application-specific automation logic using the integrated AutoIt or AutoHotkey tools.
3. Explore GHCR release automation for multi-arch builds (ARM64 support).
