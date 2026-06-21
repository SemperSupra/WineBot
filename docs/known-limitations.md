# Known Limitations

This document catalogs fundamental limitations of the tools and subsystems
used by WineBot. These are not bugs — they are constraints of the underlying
platforms (Wine, X11, AHK, xdotool) that agents and users should understand.

Each section describes the limitation, its impact, and the workaround or
adaptation already in place.

---

## Input & Window Management

### 1. Window Identification: Two Incompatible ID Systems

WineBot has two independent window ID systems that do not map to each other:

| System | Source | Format | Used By |
|:---|:---|:---|:---|
| **X11 Window IDs** | `xdotool search`, `/health/windows` | Decimal (`23068673`) | Mouse clicks, xdotool, window listing |
| **Wine HWNDs** | AHK `WinExist()`, `WinGet` | Hex (`0x160034`) | AHK window targeting with `ahk_id` |

**Do not pass X11 window IDs to AHK's `ahk_id`.** The `/input/key` API endpoint
uses AHK native title matching (`WinActivate`/`WinWaitActive` with the title
string). Always use **window titles** as the stable identifier.

### 2. Explorer.exe /desktop Keyboard Barrier

Wine's `explorer.exe /desktop` creates a virtual desktop window that intercepts
all X11 keyboard events from VNC and xdotool:

```
VNC Client -> x11vnc(:5900) -> Xvfb(:99) -> explorer.exe /desktop -> app.exe
                                                   ^
                                          KEYBOARD EVENTS STOP HERE
```

**Adaptation:** `/input/key` uses AHK `Send` which operates inside the Wine process
space, bypassing this barrier. Mouse clicks work through xdotool regardless.
Configurable via `WINEBOT_SUPERVISE_EXPLORER` and `WINEBOT_INPUT_KEY_BACKEND`.

### 3. comdlg32 File Dialogs — Definitively Impossible to Inject Text

Wine's common dialog implementation (`comdlg32`) creates modal windows whose
controls are **fully visible via DllCall/EnumChildWindows** but whose text
is **impossible to set through any external mechanism**.

**Wine Windowing Architecture:**
```
X11 Root Window
└── X11 Window "Save As" (WM_CLASS: notepad.exe)  ← The ONLY X11-mapped window
    └── Wine Internal Controls (NOT X11 windows, NOT AHK-accessible normally):
        ├── Static: "File &name:"
        ├── ComboBoxEx32 (hwnd accessible via DllCall only)
        │   └── ComboBox
        │       └── Edit (hwnd accessible, BUT text is stored internally)
        ├── Static: "Save &in:"
        ├── ComboBox (dropdown, hwnd accessible)
        ├── Button: "&Save" (hwnd accessible, CLICKABLE via BM_CLICK)
        ├── Button: "Cancel" (hwnd accessible)
        ├── ToolbarWindow32 (breadcrumb bar)
        └── SysListView32 (file list)
```

**Internal state problem:** The ComboBoxEx32 stores the filename string in
a Wine-internal data member (`lpEditInfo->wszText`), NOT in the Edit HWND's
window text buffer. Any `SetWindowTextW` or `WM_SETTEXT` call on the Edit
or ComboBoxEx32 HWND succeeds at the API level (returns TRUE) but has zero
effect on `GetWindowTextW` — the edit control recomputes its display from
the internal data member on every `WM_PAINT`, overwriting any external change.

**All 12 methods tested — 0 work for text injection:**

| Method | Controls Enumerable | Sets Text | Button Click |
|:---|:---:|:---:|:---:|
| DllCall `EnumChildWindows` + manual traversal | ✅ | N/A | N/A |
| DllCall `FindWindowExW` chain (CBEx→CB→Edit) | ✅ | N/A | N/A |
| DllCall `SetWindowTextW` (Edit HWND) | ✅ | ❌ Sets HWND text, GetWindowText empty | N/A |
| DllCall `WM_SETTEXT` (ComboBoxEx32) | ✅ | ❌ Returns 1, no effect | N/A |
| DllCall `WM_SETTEXT` (Edit) | ✅ | ❌ Returns 1, no effect | N/A |
| AHK `ControlSend` to Edit HWND | ✅ | ❌ No effect | N/A |
| AHK `Send` / `SendInput` | ❌ | ❌ Keystrokes go to window, not control | N/A |
| AHK `ControlSetText` to named control | ❌ | ❌ ErrorLevel set | N/A |
| AHK clipboard set + `^v` | ❌ | ❌ Paste goes to window | N/A |
| `xdotool type` (with/without `explorer.exe`) | ❌ | ❌ No keyboard routing to internal controls | N/A |
| Mouse click field + `xdotool type` | ❌ | ❌ Focus doesn't reach internal controls | N/A |
| `winpy` `ctypes.windll` + `SetWindowTextW` | ❌ | ❌ Wine Python process times out | N/A |
| `SendMessage BM_CLICK` on Save button | ✅ | N/A | ✅ **CLICKABLE** |

**What DOES work:**
- Enumerating all dialog controls via DllCall `EnumChildWindows` — all HWNDs, classes, and labels are visible
- Clicking dialog buttons via `SendMessage(hBtn, BM_CLICK, 0, 0)` — Save, Cancel, Open, Help buttons all work
- The architecture for building an **AHK Gui replacement dialog** is proven: controls are discoverable, buttons are clickable, a resident AHK script can monitor for dialog appearance and react

**Adaptation:** File and registry operations use `cmd.exe` (echo/redirect, reg add/query),
`/run/python` (Linux Python writes to prefix), or `docker cp` for file injection.
GUI apps should accept command-line file path arguments to avoid dialogs entirely.
In the demo, file dialogs are bypassed: file creation uses `cmd.exe echo > file`,
registry uses `reg add/query/delete`, and Notepad demonstrates pure input only.

**Future path: AHK Pipe-Based Dialog Replacement.**
A resident AHK script (`automation/core/dialog_replacement.ahk`) has been
prototyped. The design:
1. AHK script runs as a detached process, monitors for "Save As" / "Open" windows
2. When detected, closes the Wine dialog (WinClose / Send Escape)  
3. Opens an AHK Gui replacement with Edit controls and Save/Cancel buttons
4. Accepts commands via a named pipe file (`C:\dialog_handler\pipe.txt`):
   `set_filename:myfile.txt`, `click_save`, `click_cancel`, `get_state`
5. Uses AHK's `GuiControl` to set control values internally (works in-process)
6. Results written back to the pipe file as JSON

The controls ARE reachable via DllCall from within the AHK process (same
wineserver connection). The AHK Gui responds to pipe commands because
`GuiControl` operates in-process. External X11 injection still cannot
reach the Edit controls (same comdlg32 USER32 child window limitation),
but the pipe pathway bypasses this entirely.

### 4. XInput2 Disabled

Wine's XInput2 support is unstable with xdotool and VNC input injection. WineBot
sets `UseXInput2=N` at startup (verified by `diagnose-wine-registry.sh`). This
sacrifices touch/pen input and high-precision scroll events. For GUI automation,
this is the correct tradeoff.

**Managed keys:** `UseXInput2=N`, `Managed=Y`, `GrabFullscreen=N`, `UseTakeFocus=N`.

### 5. Desktop Supervisor Required

Wine's `explorer.exe` (desktop shell) can crash, leaving the screen as blue X11 root
("ghost desktop"). A supervisor loop monitors the process and restarts it with
exponential backoff and a circuit breaker. Configurable via:
- `WINEBOT_SUPERVISE_EXPLORER` (enable/disable)
- `WINEBOT_SUPERVISOR_RESTART_WINDOW_SECONDS` (reset window)
- `WINEBOT_SUPERVISOR_MAX_RESTARTS_PER_WINDOW` (circuit breaker threshold)

### 6. Window Focus Management

Wine lacks Windows' sophisticated foreground window management. WineBot provides
`WINE_FORCE_FOCUS=1` which sets aggressive registry keys:
`ForegroundFlashCount=0`, `ActiveWndTrkTimeout=0`, `BlockSendInputResets=0`.

Window titles in Wine may differ by locale or Wine version. Always verify titles
with `GET /health/windows` before targeting.

### 7. WinSpy Exists But Cannot Inject

WinSpy can inspect dialog control class names and positions but cannot inject text
into Wine's internal control hierarchy. Use it only for inspection during debugging.

---

## Process Model

### 8. wineserver as User-Space Daemon

Unlike Windows where the kernel is always present, Wine's `wineserver` runs as a
user-space daemon that can crash, hang, or fail to start. WineBot manages this with:
- Stale socket cleanup at startup (`/tmp/.wine-*/server-*`)
- `wineserver -k` and `wineserver -p` lifecycle orchestration
- 30-second timeout waits with warning fallback
- Crash detection in the supervisor loop

### 9. No Windows Services

Wine does not run Windows services natively. No Services Control Manager exists.
All applications are launched directly via `wine <exe>` with no dependency
resolution. If an app requires a running service, it must be launched manually.

### 10. AHK/AutoIt Startup Overhead (~2-3s per call)

Every AHK or AutoIt invocation requires a full Wine process initialization through
wineserver. Each `/input/key` call with the AHK backend incurs this overhead.
Mitigation: send the full text string in one call rather than per-character calls.
The `WINEBOT_TIMEOUT_INPUT_KEY_SECONDS` config (default: 10s) accounts for this.

### 11. cmd.exe /c Return Codes

`cmd.exe /c` with `detach=false` may report `status: failed` even when the
actual command succeeded. Wine's cmd.exe can return exit code 1 for startup
diagnostics before executing the command. **Recommendation:** use `detach=true`
for cmd.exe operations and verify output via `docker exec` or file content checks.

### 12. wineserver Zombie Sockets

If wineserver crashes hard, it can leave a stale socket at
`/tmp/.wine-1000/server-*` that blocks future wineserver startup. The entrypoint
cleans these on boot. In severe cases, container recreation is required.

---

## File System

### 13. Z:\ Drive Mapping and Path Conversion

Wine maps the Linux root filesystem to `Z:\`. The API's `to_wine_path()` function
handles conversion. Windows tools receive `Z:\path\to\file` paths. When using
`/run/python` (Linux Python), use Linux paths (`/wineprefix/drive_c/...`).

### 14. Backslash Handling

Wine accepts both `\` and `/` in most contexts (cmd.exe, reg.exe). However,
when passing paths through JSON APIs, backslashes require double-escaping (`\\\\`).
Prefer forward slashes where possible: `C:/artifacts/file.txt`.

### 15. WINEPREFIX as Single Directory

Wine stores all system state in the `WINEPREFIX` directory (registry as `.reg`
files, installed apps, user profiles). This is different from real Windows
where state is distributed across the filesystem. The prefix is backed by a
pre-warmed template that saves ~60s of startup time.

### 16. WINEPREFIX Ownership

The prefix must be world-writable (`chmod 777`) due to UID mapping in containers.
wineserver sockets are user-specific. Running wineserver as root then switching
users creates stale sockets that must be cleaned.

### 17. winetricks Available But Not Automatic

Winetricks is installed (pinned to v20260125) but does not run automatically.
Set `WINE_WINETRICKS=vcrun2019,dotnet48` to auto-install components at startup.
Components install sequentially with `--unattended` mode.

---

## Registry

### 18. Registry Stored as Flat Files

Wine stores the registry as text files (`system.reg`, `user.reg`) rather than
binary hives. The init script reads these directly to check prefix readiness.
`wine reg query` output format can vary between Wine versions; diagnostic
scripts handle this with fallback parsing.

### 19. DLL Overrides Required

Wine requires explicit `WINEDLLOVERRIDES="mscoree,mshtml="` during initialization
to disable Mono (.NET) and Gecko (HTML) engine prompts. These engines are not
needed for WineBot's automation use case and disabling them speeds up startup.

---

## Fonts & Rendering

### 20. No Proprietary Windows Fonts

Wine does not include Microsoft fonts (Segoe UI, Tahoma, Verdana, etc.).
WineBot substitutes them with metric-compatible Liberation fonts (Liberation Sans,
Liberation Serif, Liberation Mono). These are installed at build time
(`fonts-liberation` package).

For pixel-identical OCR/CV template matching with real Windows:
- **Option A:** Capture OCR templates on WineBot itself (the Liberation fonts are
  consistent within the same environment)
- **Option B:** Set `WINE_INSTALL_MS_FONTS=1` to run `winetricks corefonts` at
  startup, installing Microsoft's freely redistributable Core Fonts (Arial,
  Times New Roman, Courier New, Verdana, etc.)

### 21. No Desktop Window Manager (DWM)

Wine has no DWM compositor. WineBot provides Openbox for window management
(decoration, focus, keyboard bindings) and tint2 for the taskbar panel.
Window decorations are controlled via Openbox `rc.xml` and Motif hints.

### 22. No Hardware Acceleration in Headless Mode

Headless mode (no physical GPU) means no D3D/OpenGL hardware acceleration.
Wine falls back to software rendering. This is correct for automation use
cases where rendering fidelity is secondary to input reliability.

### 23. Font Smoothing Configurable

`WINE_FONT_SMOOTHING` controls text rendering quality:
- `grayscale` (default): best for CV/OCR and automation
- `cleartype`: better for human VNC viewers
- `off`: raw rendering, lowest resource usage

---

## UI Automation

### 24. UI Automation (UIA) Not Functional

Wine 10.0's UI Automation support is incomplete. `pywinauto`'s `uia` backend
fails during `comtypes`/UIA typelib initialization even with `UIAutomationCore.dll`
present. WineBot does not use pywinauto or UIA-based automation.

**Adaptation:** AHK, AutoIt, xdotool, and computer vision (CV/OCR) provide
equivalent automation capabilities without UIA dependency.

**Future:** Tracked in GitHub issue for UIA support monitoring. Wine has been
improving UIA since v10.0; re-evaluate with each major Wine release.

### 25. WinSpy Inspection Only

The `WinSpy` tool can inspect window class names, control IDs, and positions.
However, it cannot inject text or interact with Wine's internal controls.
Use it for debugging window structure, not for automation.

---

## Networking

### 26. mDNS Port Conflicts

WineBot runs mDNS on port 5353/UDP. On Windows hosts with Docker Desktop, this
may conflict with the host's Bonjour/mDNS service. Workaround: remap the port
in `docker-compose.yml`.

### 27. Architecture Decision: Debian Trixie

Alpine (musl libc) is incompatible with Wine's glibc dependency. Ubuntu + WineHQ
introduces third-party repository risk. Debian Trixie was selected for native
Wine packages without external repos, providing the most recent stable Wine
available through Debian's own channels.

---

## Diagnostics

### 28. winedbg Limitations

`winedbg --gdb` and `winedbg --auto` have known flakiness in headless Xvfb
environments. Process inspection may fail silently. For crash diagnostics,
prefer session logs and Wine debug channels (`WINEDEBUG=+seh,+tid`).

### 29. Wine Registry Output Format Variability

`wine reg query` output format varies between Wine versions. Diagnostic scripts
use fallback `awk` parsing to handle this. The `diagnose-wine-registry.sh` script
validates key registry settings are applied correctly.

---

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
| Windows API access | `/run/ahk` invoking `winpy` | N/A |
| Inspect window structure | `WinSpy` (read-only) | `xwininfo -tree` |
| Crash diagnostics | Session logs + `WINEDEBUG=+seh` | `winedbg --auto` |
| Install runtimes | `WINE_WINETRICKS=vcrun2019,dotnet48` | Manual `winetricks` via docker exec |
| Install MS fonts | `WINE_INSTALL_MS_FONTS=1` | Manual `winetricks corefonts` |
