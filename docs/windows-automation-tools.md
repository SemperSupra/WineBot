# Windows Automation Tools

WineBot includes support for popular Windows automation tools running inside the Wine environment.

## Available Tools

| Tool | Command | Description |
| :--- | :--- | :--- |
| **AutoIt v3** | `autoit` | Powerful scripting language for Windows GUI automation. ([autoitscript.com](https://www.autoitscript.com)) |
| **AutoHotkey v1.1** | `ahk` | Automation scripting language for Windows. ([autohotkey.com](https://www.autohotkey.com)) |
| **Python 3.13** | `winpy` | Windows embedded Python. |

## Usage

These tools are in the system PATH and can be called directly.

### AutoIt
Run an AutoIt script (`.au3`):
```bash
autoit my_script.au3
```

### AutoHotkey
Run an AutoHotkey script (`.ahk`):
```bash
ahk my_script.ahk
```

### Python (Windows)
Run a Python script (`.py`) using the Windows Python environment:
```bash
winpy my_script.py
```
Note: This is separate from the container's native Linux Python (`python3`). Use `winpy` when you need Windows-specific modules.

**Note on pip:** To minimize build time and image size, `pip` is not pre-installed in the `winpy` environment. `winpy` is intended for lightweight diagnostics and tracers using `ctypes` and the standard library. If you require `pip` at runtime, you can install it using:
```bash
curl -sL -o /tmp/get-pip.py https://bootstrap.pypa.io/get-pip.py
winpy /tmp/get-pip.py
```

## Wine UIA Status

Wine in this project currently runs as `wine-10.0 (Debian 10.0~repack-6)`.
In this runtime, UI Automation support is incomplete for pywinauto's `uia` backend and not reliable enough for default project use.
Typical failures are during `comtypes`/UIA typelib initialization even when `UIAutomationCore.dll` is present.

Practical guidance:
- Keep automation fallback paths available (AHK/AutoIt/X11/CV) for controls that are not accessible via `win32`.
- Re-check pywinauto viability as Wine UIA support matures in newer Wine releases.

## Smoke Tests
You can verify the tools are working by running the included smoke tests:
```bash
./tests/run_smoke_tests.sh
```

The smoke test now validates:
- AutoIt + AHK scripting
- Windows Python (`winpy`)
- screenshot artifacts, including required `/tmp/smoke_test.png`

## DEBUG Tool Version Output

If you start the container with `DEBUG=1`, entrypoint logs tool version/availability checks for:
- `autoit`
- `ahk`
- `winpy`
