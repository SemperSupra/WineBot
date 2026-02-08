# WineBot Dependency & Version Pinning Policy

To ensure reproducibility, stability, and security, WineBot enforces strict version pinning across all layers of the stack.

## 1. Base Operating System (Docker)
The `Dockerfile` must use a specific image digest (`sha256`) rather than a floating tag like `latest` or `slim`.
- **Target:** `debian:trixie-slim`
- **Mechanism:** `FROM debian@sha256:...`

## 2. Linux System Packages (APT)
Major system dependencies (Wine, FFmpeg, Xvfb) are managed via the Debian Trixie repositories. While pinning individual APT versions is often impractical due to transitive dependency shifts, the base image digest effectively pins the available package pool at a specific point in time.

## 3. Python Dependencies (PIP)
All Python packages for the API, Tracing, and Testing must be pinned to exact versions in `requirements.txt`.
- **Mechanism:** `pip install -r requirements.txt`
- **Constraint:** Use `==` for all top-level packages.

## 4. Windows Automation Tools
External Windows binaries (AutoIt, AHK, Python Embedded) must be downloaded from versioned URLs.
- **Mechanism:** `windows-tools/download_tools.sh`
- **Constraint:** No "latest" or redirect-based URLs without explicit version tags in the filename or path.

## 5. Continuous Integration (GitHub Actions)
All external actions used in `.github/workflows/` must be pinned to specific commit SHAs rather than mutable tags.
- **Mechanism:** `uses: actions/checkout@<full-sha>`

## 6. Updating Dependencies
Dependencies should be reviewed and updated periodically (e.g., once a month). When updating:
1. Update the `requirements.txt` or `Dockerfile`.
2. Run the `scripts/diagnose-master.sh` suite to verify compatibility.
3. Commit the changes with a clear "Dependency Update" message.
