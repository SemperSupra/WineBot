# Known Limitations

This document catalogs fundamental limitations of the tools and subsystems
used by WineBot. These are not bugs — they are constraints of the underlying
platforms (Wine, X11, AHK, xdotool) that agents and users should understand.

## 1. Window Identification Systems

WineBot has **two independent window ID systems** that do not map to each other:

| System | Source | Format | Used By |
|:---|:---|:---|:---|
| **X11 Window IDs** | `xdotool search`, `/health/windows` | Decimal (`23068673`) | Mouse clicks, xdotool, window listing |
| **Wine HWNDs** | AHK `WinExist()`, `WinGet` | Hex (`0x160034`) | AHK window targeting with `ahk_id` |

**Do not pass X11 window IDs to AHK's `ahk_id` parameter.** They are different
numbering systems. The `/input/key` API endpoint uses **native AHK title matching**
via `WinActivate`/`WinWaitActive` with the title string, which works correctly
across both systems. Always use **window titles** as the stable identifier.

```bash
# CORRECT: Use title for both mouse and keyboard
POST /input/mouse/click {"x": 400, "y": 300, "window_title": "Notepad"}
POST /input/key {"keys": "Hello", "window_title": "Notepad"}

# WRONG: Using X11 numeric IDs with keyboard (AHK won't match)
POST /input/key {"keys": "Hello", "window_id": "23068673"}  # AHK can't use this
```

## 2. comdlg32 File Dialogs

Wine's common dialog implementation (`comdlg32`) creates modal windows that
have **fundamental input limitations**:

- **AHK `Send` cannot type into file dialog edit controls.** The Save As, Open,
  and similar dialogs are drawn as a single monolithic X11 window with zero
  children. All controls (filename field, buttons, tree view) exist only
  inside Wine's internal windowing — they are not exposed as separate X11
  or AHK-accessible subwindows.

- **`xdotool type` cannot type into dialog controls either.** `xdotool` can
  only send keystrokes to the parent X11 window, not to Wine's internal
  control hierarchy.

- **WinSpy** can inspect dialog controls but cannot inject text.

- **Workaround for file dialogs:**
  - Use `cmd.exe` or `reg.exe` for file and registry operations via the API
  - Write files programmatically via `/run/python` (Linux Python writes to
    the Wine prefix's filesystem directly)
  - Use `docker cp` to inject files at the Linux filesystem level
  - For GUI apps that require Save/Open: use apps that accept command-line
    arguments for file paths, bypassing the dialog entirely

## 3. Explorer.exe /desktop Keyboard Barrier

Wine's `explorer.exe /desktop` creates a virtual desktop window that
**intercepts all X11 keyboard events** from VNC and xdotool.

```
VNC Client -> x11vnc(:5900) -> Xvfb(:99) -> explorer.exe /desktop -> app.exe
                                                   ^
                                          KEYBOARD EVENTS STOP HERE
```

**Solution:** The `/input/key` endpoint uses AHK `Send` by default,
which operates inside the Wine process space and bypasses this barrier.
Mouse clicks (`/input/mouse/click`) work through xdotool regardless.

If you need xdotool-based keyboard:
```bash
# Option A: Disable the desktop supervisor
WINEBOT_SUPERVISE_EXPLORER=0

# Option B: Set keyboard backend to xdotool
WINEBOT_INPUT_KEY_BACKEND=xdotool
```

## 4. AHK Send Character Escaping

AHK's `Send` command interprets certain characters as control sequences:

| Character | AHK Meaning | API Behavior |
|:---|:---|:---|
| `%` | Variable dereference | Escaped to `` `% `` |
| `+` | Shift modifier | Escaped to `{+}` in plain text |
| `^` | Ctrl modifier | Escaped to `{^}` in plain text |
| `!` | Alt modifier | Escaped to `{!}` in plain text |
| `#` | Win modifier | Escaped to `{#}` in plain text |

The translation layer handles these automatically. When using `/run/ahk`
directly (not through `/input/key`), you must handle escaping yourself.

## 5. /run/python Runs Linux Python

The `/run/python` endpoint executes **Linux Python**, not Windows Python
(`winpy`). This means:
- `ctypes.windll` is not available
- Paths should use Linux conventions (`/wineprefix/drive_c/...`)
- No access to Wine's Windows API from Python

For Windows API access, use `/run/ahk` with a script that invokes `winpy`.

## 6. AutoIt/AHK Startup Delay

AHK and AutoIt scripts have a startup overhead of **~2-3 seconds** per call
due to Wine process initialization. The `SetKeyDelay` of 20ms adds ~20ms
per keystroke. For bulk text entry, send the full string in one call rather
than individual keystrokes.

## 7. No VNC Keyboard Passthrough in Headless Mode

In headless mode, VNC keyboard events are intercepted by the desktop barrier
(see #3). VNC mouse events work. For programmatic keyboard control, always
use the `/input/key` API endpoint.

## 8. Window Focus and Title Matching

AHK `WinWaitActive` has a 2-second default timeout. If the target window
doesn't exist or has a slightly different title, the keystroke is sent
to whatever window currently has focus.

Window titles in Wine may differ from their Windows equivalents:
- "Untitled - Notepad" vs "Untitled - Notepad"
- "Save As" (Wine) vs "Save As" (same in Wine, but may differ by locale)

Always verify window titles with `GET /health/windows` before targeting.

## 9. XInput2 Disabled

WineBot disables XInput2 (`UseXInput2=N`) for input stability with xdotool
and VNC. This means Wine applications cannot use touch/pen input or
high-precision scroll events. For the vast majority of GUI automation,
this is the correct setting.

## 10. mDNS Port Conflicts

WineBot runs mDNS on port 5353/UDP for service discovery. On Windows hosts
with Docker Desktop, this port may conflict with the host's Bonjour/mDNS
service. Workaround: remap the port in docker-compose.

## Summary: When to Use Which Tool

| Task | Recommended Tool | Fallback |
|:---|:---|:---|
| Click a UI element | `/input/mouse/click` | `/run/ahk` with `Click` |
| Type text into app | `/input/key` (AHK backend) | `/run/ahk` with `Send` |
| Launch an app | `/apps/run` | `cmd.exe` + `/input/key` |
| File system operations | `cmd.exe` via `/apps/run` with args | `/run/python` (Linux path) |
| Registry operations | `cmd.exe` via `/apps/run` with `reg` | `/run/ahk` with `RegWrite` |
| Save/Open file dialog | **Avoid** — use cmd.exe args instead | `docker cp` file injection |
| Read a window title | `GET /health/windows` | `xdotool getwindowname` |
| Run a batch script | `/apps/run` `cmd.exe /c script.bat` | `/run/python` write then execute |
