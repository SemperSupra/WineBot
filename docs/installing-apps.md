# Installing Apps

This workflow separates installation (into the persistent Wine prefix) from running the app for automation.

## 1) Place the installer

Copy the installer into `./apps` on the host, for example:

`apps/MyInstaller.exe`

## 2) Install into the Wine prefix

Use the installer script (interactive mode by default):

`scripts/install-app.sh apps/MyInstaller.exe`

Then open noVNC at `http://localhost:6080` and complete the installer UI. The container exits when the installer finishes.

For a silent installer, pass arguments and run headless:

`scripts/install-app.sh apps/MyInstaller.exe --args "/S" --headless`

## 3) Run the installed app

Prefer the Unix-style path inside the prefix (avoids backslash escaping):

`scripts/run-app.sh "/wineprefix/drive_c/Program Files/MyApp/MyApp.exe"`

If you need the Windows path, quote and escape backslashes:

`scripts/run-app.sh "C:\\Program Files\\MyApp\\MyApp.exe"`

Run in the background:

`scripts/run-app.sh "/wineprefix/drive_c/Program Files/MyApp/MyApp.exe" --detach`

List installed executables:

`scripts/list-installed-apps.sh`

Filter by name:

`scripts/list-installed-apps.sh --pattern "MyApp"`

## 4) Run with automation

Run headless and trigger an automation command after launch:

`scripts/run-app.sh "/wineprefix/drive_c/Program Files/MyApp/MyApp.exe" --automation "python3 automation/find_and_click.py --template automation/assets/example_button.png"`

## Notes

- The Wine prefix is stored in the `wineprefix` named volume and persists across runs.
- To reset the environment, remove the volume: `docker compose -f compose/docker-compose.yml down -v`
- If you only have `docker-compose` v1 installed, replace `docker compose` with `docker-compose`.

## Programmatic / API Usage

You can also install and run apps via the internal API:

- **List Apps:** `GET /apps`
- **Run App:** `POST /apps/run` `{"path": "...", "args": "/S"}`

See `docs/api.md` for details.
