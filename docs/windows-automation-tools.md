# Windows Automation Tools

WineBot includes support for popular Windows automation tools running inside the Wine environment.

## Available Tools

| Tool | Command | Description |
| :--- | :--- | :--- |
| **AutoIt v3** | `autoit` | Powerful scripting language for Windows GUI automation. |
| **AutoHotkey v1.1** | `ahk` | Automation scripting language for Windows. |
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

## Smoke Tests
You can verify the tools are working by running the included smoke tests:
```bash
./tests/run_smoke_tests.sh
```
