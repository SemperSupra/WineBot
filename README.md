# WineBot

WineBot is a containerized harness for running Windows GUI applications under Wine in headless or interactive modes. It provides a stable virtual desktop for automation and optional VNC/noVNC access for debugging.

## Quickstart

Headless:

`docker compose -f compose/docker-compose.yml --profile headless up --build`

Interactive (VNC + noVNC):

`docker compose -f compose/docker-compose.yml --profile interactive up --build`

If you only have `docker-compose` v1 installed, replace `docker compose` with `docker-compose`.

## Run a Windows app

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

The image is saved to `/tmp/screenshot.png` inside the container.

## Run the sample CV automation

`docker compose -f compose/docker-compose.yml --profile headless exec --user winebot winebot python3 automation/find_and_click.py --template automation/assets/example_button.png`

## Run the Notepad automation

`docker compose -f compose/docker-compose.yml --profile interactive exec --user winebot winebot-interactive python3 automation/notepad_create_and_verify.py --text "Hello from WineBot" --output /tmp/notepad_test.txt --launch`

## Smoke test

`scripts/smoke-test.sh`

Variants:

- `scripts/smoke-test.sh --full`
- `scripts/smoke-test.sh --include-interactive`
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
- `docs/installing-apps.md`
- `docs/testing.md`
- `docs/troubleshooting.md`
