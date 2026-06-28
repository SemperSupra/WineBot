# Known Limitations

This document catalogs fundamental limitations of the tools and subsystems
used by WineBot. These are not bugs — they are constraints of the underlying
platforms ([Wine](https://www.winehq.org), X11, AHK, [xdotool](https://github.com/jordansissel/xdotool)) that agents and users should understand.

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
VNC Client -> [x11vnc](https://github.com/LibVNC/x11vnc)(:5900) -> Xvfb(:99) -> explorer.exe /desktop -> app.exe
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

**Solution: AHK Pipe-Based Dialog (WORKING).**
A pipe-driven AHK Gui (`automation/core/dialog_replacement.ahk`) replaces
Save As dialogs entirely. No Wine dialogs are triggered — the AHK Gui IS
the dialog interface.

**How it works:**
1. Launch AHK via `/apps/run {"path":"ahk","args":"C:/dr.ahk","detach":true}`
2. Script waits for pipe commands at `C:\dialog_handler\pipe.txt`
3. `open_gui` → Shows "WineBot Save Dialog" with filename field + Save/Cancel
4. `set_filename:file.txt` → Sets filename in global variable
5. `click_save` → Writes file via AHK `FileAppend` to `C:/artifacts/file.txt`
6. Responses: `{"status":"gui_opened"}`, `{"status":"set_ok"}`, `{"status":"saved"}`

**CV-confirmed: No Wine Save As dialog appears.** The CV watcher
(`scripts/diagnostics/cv-watcher.py`) confirmed via pixel diff analysis that
only the AHK Gui appears on screen — no comdlg32 dialog is triggered.

**Why interception was removed:**
The interceptor's PollDialogs timer had a race condition: `if (gGuiOpen) return`
silently ignored Wine Save As dialogs that appeared while the AHK Gui was open.
The CV watcher showed the Wine dialog at +106,616px change and persisting for
7+ frames (~3.5 seconds) without being caught. The correct approach is to never
trigger Wine dialogs — use the AHK Gui directly as the save interface.

**Pipe protocol (zero chown, su winebot throughout).**

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

[WinSpy](https://github.com/stefj/winspy) can inspect dialog control class names and positions but cannot inject text
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

Wine has no DWM compositor. WineBot provides [Openbox](http://openbox.org) for window management
(decoration, focus, keyboard bindings) and [tint2](https://gitlab.com/o9000/tint2) for the taskbar panel.
Window decorations are controlled via Openbox `rc.xml` and Motif hints.

### 22. No Hardware Acceleration in Headless Mode

Headless mode uses Xvfb (X Virtual Framebuffer) — a purely software memory
framebuffer. Xvfb provides a 2D pixel buffer at a fixed resolution but has
**no GPU, no OpenGL, and no Direct3D or Vulkan support**. This is the most
significant architectural difference between WineBot and WinBot.

#### Impact by Application Type

| Application Type | WineBot (Xvfb) | WinBot (Windows GPU) |
|:---|:---|:---|
| Standard Win32 GUI (Notepad, cmd, regedit) | ✅ Works | ✅ Works |
| 2D GDI applications | ✅ Works | ✅ Works |
| 2D DirectDraw games (Alpha Centauri, Civ II) | ✅ with `DirectDraw=0` | ✅ Works |
| OpenGL 2D games (Baldur's Gate, StarCraft) | ✅ Software fallback | ✅ Hardware |
| OpenGL 3D games (SuperTux, 0 A.D.) | ❌ No GL context | ✅ Hardware |
| Direct3D 9/10/11 applications | ❌ Requires GPU | ✅ Hardware |
| CAD / 3D modeling tools | ❌ Requires GPU | ✅ Hardware |
| Games with software renderer option | ✅ CPU rendering only | ✅ Hardware |

#### Wine Configuration for Software Rendering

To maximize Xvfb compatibility, Wine can be forced to use the GDI software
renderer for all Direct3D calls:

```
wine reg add 'HKCU\Software\Wine\Direct3D' /v renderer /t REG_SZ /d gdi /f
```

This setting is **not applied by default** in WineBot — it is set per-session
by demo scripts that need it. Games that require OpenGL 3.x+ will fail
regardless because Xvfb provides no GLX (GL extension) support whatsoever.

#### Xvfb Technical Constraints

- **No GPU access** — Xvfb has no link to any GPU. No `/dev/dri`, no DRM, no hardware
  rasterization. This is architectural, not configurable.
- **GLX is software-only** — Xvfb *can* report a GLX extension (`+extension GLX`) but
  it maps to Mesa's CPU-based software rasterizer (llvmpipe). There is no hardware
  OpenGL. `glxinfo` will report the software renderer if Mesa libraries are installed.
- **No Vulkan ICD** — Xvfb does not register a Vulkan Installable Client Driver.
  Translation layers like [DXVK](https://github.com/doitsujin/dxvk) (DirectX → Vulkan) and [VKD3D](https://github.com/HansKristian-Work/vkd3d-proton) will find no Vulkan device.
- **Wine's `opengl32`** built-in maps to whatever GLX/Xvfb provides — a software
  surface with no GPU backing.
- **Software OpenGL is possible via LLVMpipe** — installing `mesa-utils` and
  `libgl1-mesa-dri` provides software OpenGL 4.5 through llvmpipe. This is CPU-only
  and slow but sufficient for basic GL applications. Not included in the base image.

#### Games Tested Against Xvfb

| Game | Result | Failure Mode |
|:---|:---|:---|
| SuperTux (OpenGL 3.3) | ❌ | Starts but unusable — software GL (llvmpipe) renders at <5 FPS; segfaults without Mesa installed |
| Alpha Centauri (DirectDraw 2D) | ✅ with `DirectDraw=0` | Forces GDI software path |
| Civilization II (2D) | ✅ Expected | GDI-based rendering |
| Diablo II (DirectDraw 2D) | ✅ with `-w -nofixaspect` | DirectDraw software fallback |
| StarCraft (2D) | ✅ Expected | 2D sprite-based |

#### Future Options for 3D Support

- **LLVMpipe** — CPU-based OpenGL implementation. Adds ~10MB to image. Enables
  OpenGL 4.5 in software. Available via `apt install libgl1-mesa-dri`.
- **virgl** — Virtualized GPU for QEMU/KVM containers. Requires host GPU.
- **GPU passthrough** — Mount `/dev/dri` into container. Requires Linux host
  with GPU. Non-portable (breaks macOS/Windows Docker Desktop hosts).
- **VNC with [VirtualGL](https://virtualgl.org) / [TurboVNC](https://turbovnc.org)** — Render on host GPU, stream to container. Complex.

For WinBot parity, games and 3D applications should run on WinBot where the
native Windows GPU driver is available. For WineBot, use the GDI software
renderer and test each application individually.

#### GPU Command Proxy ("Software GPU Passthrough")

A common question is whether Mesa/llvmpipe could be modified to forward
rendering commands over a Unix socket to a GPU-accessible host service,
effectively creating a "software GPU passthrough." This pattern **has been
implemented** in production by several projects:

| Project | Technique | Status | Applicable? |
|:---|:---|:---|:---|
| **Anbox / Waydroid** | Android GLES stub → pipe → host renderer | Production | ❌ OpenGL ES only, not Wine's GLX |
| **VirGL (virglrenderer)** | virtio-gpu + Mesa Gallium driver → host GPU | Production | ❌ Requires QEMU VM with virtio-gpu kernel driver; Docker containers can't do this |
| **Android emulator (emugl)** | Pipe-based GLES forwarding from guest to host GPU | Production | ❌ OpenGL ES only, not GLX |
| **Mesa Gallium Remote ST** | TCP-forwarded Gallium state tracker (experimental) | Dead since ~2011 | ❌ Removed from Mesa tree, not usable |

**Why none of these help WineBot:**

1. **GLX vs EGL/GLES:** Wine uses GLX (X11's OpenGL binding), not EGL or
   OpenGL ES. Every existing GPU proxy project targets OpenGL ES or EGL.
   There is no proxy protocol that speaks desktop GL through GLX.

2. **Wine's rendering path:** Wine's 3D goes through this chain:
   ```
   Win32 app → WineD3D/DXVK → GLX call → X server → Mesa driver → GPU
   ```
   Interception needs to happen before the X server — either in Wine's
   `opengl32` translation layer or in Mesa's GLX implementation. Both
   are deep, invasive modifications.

3. **Windows Docker GPU ceiling:** Even with a perfect proxy, the host GPU
   runs in P8 power state through WSL2. Adding serialize/socket/deserialize/
   render/readback overhead would likely be slower than CPU-only software
   rendering for 2D workloads.

**Verdict:** The GPU command proxy pattern is proven technology, but
adapting it for Wine's GLX stack on Docker Windows is a multi-month
engineering project with marginal payoff for WineBot's 2D UI automation
use case.

**References:**
- [Anbox](https://github.com/anbox/anbox) — Android in a container (archived; reused Android emulator's emugl system for GLES forwarding)
- [Waydroid](https://github.com/waydroid) — Modern Android-in-container, active development, same GLES proxy pattern
- [virglrenderer](https://gitlab.freedesktop.org/virgl/virglrenderer) — Host-side OpenGL/Vulkan renderer for virtio-gpu virtual GPU
- [Mesa Gallium3D](https://docs.mesa3d.org/gallium/) — Mesa 3D Graphics Library documentation (Gallium driver architecture)
- [Android emulator emugl](https://android.googlesource.com/platform/external/qemu/+/refs/heads/main/android/emugl/) — Source tree for Android emulator's OpenGL ES emulation (emugl / libOpenglRender)

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
