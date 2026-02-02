# WineBot

> **For AI Agents & Automation:** See [AGENTS.md](AGENTS.md) for the API and programmatic control guide.

WineBot is a containerized harness for running Windows GUI applications under Wine in headless or interactive modes. It provides a stable virtual desktop for automation and optional VNC/noVNC access for debugging.

## Quickstart

Headless:

`docker compose -f compose/docker-compose.yml --profile headless up --build`

Interactive (VNC + noVNC):

`docker compose -f compose/docker-compose.yml --profile interactive up --build`

If you only have `docker-compose` v1 installed, replace `docker compose` with `docker-compose`.

## Simplified Usage (v0.4+)

The updated entrypoint allows running commands directly with automatic Xvfb management and host user mapping.

**Run a command (pass-through):**
```bash
# Runs 'make' inside the container as the current host user
docker run --rm -v $(pwd):/work -w /work -e HOST_UID=$(id -u) winebot make
```

**Run a Windows executable:**
```bash
docker run --rm -v $(pwd):/work -w /work -e HOST_UID=$(id -u) winebot wine myapp.exe
```

**Interactive Shell:**
```bash
docker run --rm -it -e HOST_UID=$(id -u) winebot bash
```

## Run a Windows app (Compose)

1. Put your executable in `./apps`.
2. Set `APP_EXE` to the path inside the container (defaults to `cmd.exe` if unset).

Example:

`APP_EXE=/apps/MyApp.exe docker compose -f compose/docker-compose.yml --profile interactive up --build`

You can also set:

- `APP_ARGS` for optional arguments
- `WORKDIR` for a specific working directory
- `APP_NAME` to label the noVNC URL

## Install then run (recommended)

Install into the persistent Wine prefix:

`scripts/install-app.sh apps/MyInstaller.exe`

Run the installed app (use the Unix path to avoid backslash escaping):

`scripts/run-app.sh "/wineprefix/drive_c/Program Files/MyApp/MyApp.exe"`

List installed executables in the prefix:

`scripts/list-installed-apps.sh --pattern "MyApp"`

Run in the background:

`scripts/run-app.sh "/wineprefix/drive_c/Program Files/MyApp/MyApp.exe" --detach`

See `docs/installing-apps.md` for more options.

## Connect to the desktop

- VNC client: `localhost:5900`
- Browser (noVNC): `http://localhost:6080`

Change the default VNC password in `compose/docker-compose.yml`.

## Take a screenshot (headless)

`docker compose -f compose/docker-compose.yml --profile headless exec --user winebot winebot ./automation/screenshot.sh`

The image is saved to `/tmp/screenshot_YYYY-MM-DD_HH-MM-SS.png` inside the container. You can also specify a custom path or directory as an argument.

## Debug with winedbg

Run an app under winedbg's gdb proxy (port 2345):

`ENABLE_WINEDBG=1 WINEDBG_MODE=gdb WINEDBG_PORT=2345 WINEDBG_NO_START=1 APP_EXE=/apps/MyApp.exe docker compose -f compose/docker-compose.yml --profile interactive up --build`

Then connect from the host:

`gdb -ex "target remote localhost:2345"`

See `docs/debugging.md` for scripted commands and additional tooling.

## Headless Tools & Helpers

WineBot provides helpers to simplify headless interaction:

- **X11 Inspection:** `/automation/x11.sh` (list windows, focus, search)
- **Robust Screenshots:** `/automation/screenshot.sh` (auto-detects X11 env)
- **AutoHotkey Runner:** `/scripts/run-ahk.sh` (handles focus, logs, and wineboot)
- **Windows Inspectors:** `/scripts/au3info.sh` and `/scripts/winspy.sh` (for inspecting controls)
- **Internal API:** HTTP API for programmatic control (see `docs/api.md`).

See [docs/debugging.md](docs/debugging.md) for details.

## Run the sample CV automation

`docker compose -f compose/docker-compose.yml --profile headless exec --user winebot winebot python3 automation/find_and_click.py --template automation/assets/example_button.png`

## Run the Notepad automation

`docker compose -f compose/docker-compose.yml --profile interactive exec --user winebot winebot-interactive python3 automation/notepad_create_and_verify.py --text "Hello from WineBot" --output /tmp/notepad_test.txt --launch`

## Windows Automation Tools

WineBot includes pre-installed Windows automation tools running under Wine:

- **AutoIt v3** (`autoit`)
- **AutoHotkey v1.1** (`ahk`)
- **Python 3.13** (`winpy`)

See [docs/windows-automation-tools.md](docs/windows-automation-tools.md) for usage.

Run the tool smoke tests:

`docker compose -f compose/docker-compose.yml --profile headless exec --user winebot winebot ./tests/run_smoke_tests.sh`

## Smoke test

`scripts/smoke-test.sh`

Variants:

- `scripts/smoke-test.sh --full`
- `scripts/smoke-test.sh --include-interactive`
- `scripts/smoke-test.sh --include-debug`
- `scripts/smoke-test.sh --include-debug-proxy`
- `scripts/smoke-test.sh --full --cleanup`

## Releases & GHCR

GitHub Actions runs smoke tests and publishes images to GHCR on release:

- `ghcr.io/<owner>/winebot:<release-tag>`
- `ghcr.io/<owner>/winebot:latest`
- `ghcr.io/<owner>/winebot:sha-<short>`

Manual runs are supported via Actions → Release → Run workflow. Provide `image_tag` or it defaults to `manual-<sha>`.

## Documentation

- `docs/architecture.md`
- `docs/automation.md`
- `docs/api.md`
- `docs/debugging.md`
- `docs/installing-apps.md`
- `docs/testing.md`
- `docs/troubleshooting.md`
