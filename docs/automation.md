# Automation

WineBot supports two layers of automation:
1.  **Windows-native tools** (AutoIt, AutoHotkey) running *inside* Wine.
2.  **External CV/Input tools** (OpenCV, xdotool) running in the Linux container environment.

## Windows Automation Tools (Preferred)

For direct control of Windows GUI elements, use the pre-installed tools. See [windows-automation-tools.md](windows-automation-tools.md) for details on `autoit`, `ahk`, and `winpy`.

## Linux/CV Automation SDK

WineBot includes a minimal automation SDK in `automation/` to help with debugging and simple UI flows when direct control isn't possible.
When using `docker compose exec` (or `docker-compose exec`), run automation as `winebot` to avoid Wine prefix ownership errors.

## Scripts

- `automation/screenshot.sh` captures the virtual desktop. Supports specific windows (`-w`), delays (`-d`), annotations (`-l`), and metadata (`--request-id`, `--tag`). A JSON sidecar (`.png.json`) is written alongside the image. When a session is active, screenshots default to `<session_dir>/screenshots`.
- `automation/x11.sh click-at <x> <y>` clicks absolute coordinates via `xdotool`.
- `automation/find_and_click.py` performs OpenCV template matching and clicks the best match
- `automation/notepad_create_and_verify.py` writes and verifies a file via Notepad

## Example

`python3 automation/find_and_click.py --template automation/assets/example_button.png --threshold 0.8 --retries 5`

Write and validate a file in Notepad:

`python3 automation/notepad_create_and_verify.py --text "Hello from WineBot" --output /tmp/notepad_test.txt --launch`

Exit codes:

- `0` match found and clicked
- `2` no match found after retries

For debugger-driven automation (winedbg, gdb proxy, scripted commands), see `docs/debugging.md`.
