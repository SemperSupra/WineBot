# Troubleshooting

## Missing DLLs or runtimes

Use winetricks to install Visual C++ or .NET dependencies:

`winetricks vcrun2019`

## 32-bit vs 64-bit prefix

Some applications require 32-bit Wine:

`WINEARCH=win32`

## Fonts look wrong

Install core fonts:

`winetricks corefonts`

## No window focus

Ensure `openbox` is running and the app is visible on the virtual desktop.

## VNC/xdotool keyboard events don't reach the application

**Symptom:** VNC key presses or `xdotool key` commands execute but don't affect the
Windows application. `/proc/PID/mem` reads show no state changes. The app appears
frozen or unresponsive to injected input.

**Root cause:** Wine's `explorer.exe /desktop` creates a virtual Windows desktop
as an X11 window. All VNC/xdotool keyboard events go to this desktop window, not
to individual app windows within it. This is identical to how a real Windows
desktop works — typing on the desktop background doesn't reach the foreground
application.

**Input pipeline:**
```
VNC Client → x11vnc(:5900) → Xvfb(:99) → explorer.exe /desktop → app.exe
                                                    ^
                                           KEYBOARD EVENTS STOP HERE
```

**Confirmed:** The `explorer.exe /desktop` process (visible via `pgrep -f "explorer.exe /desktop"`)
intercepts all X11 keyboard input. A container supervisor continuously restarts
it if killed, making standalone app windows impossible in the default configuration.

**Solutions (in order of preference):**

1. **Enable hybrid control mode** (recommended for API users):
   ```bash
   WINEBOT_ALLOW_HEADLESS_HYBRID=1
   WINEBOT_INSTANCE_CONTROL_MODE=hybrid
   ```
   This enables `/apps/run`, `/run/ahk`, and `/run/python` endpoints that use
   Windows hooks (AutoHotkey/Windows messages) for keyboard injection — these
   bypass the X11 interception layer entirely.

2. **Disable the desktop supervisor** (for xdotool/VNC keyboard users):
   ```bash
   WINEBOT_SUPERVISE_EXPLORER=0
   ```
   Then kill the desktop: `pkill -f "explorer.exe"`
   Apps will create standalone X11 windows targetable by xdotool/VNC.

3. **Use mouse-only VNC interaction** (workaround):
   Mouse click events do reach the desktop and are forwarded to the app.
   Use VNC framebuffer reads to visually locate UI elements, then click.
   Keyboard shortcuts (Ctrl+L, Escape) can be simulated via on-screen
   keyboard or menu navigation with mouse clicks.

## Agent control denied by policy (HTTP 423)

**Symptom:** API endpoints `/apps/run`, `/run/ahk`, `/run/python`, `/input/*`
return `HTTP 423: Agent control denied by policy`.

**Root cause:** The container is in `agent-only` control mode (default for headless).
This mode blocks all agent-initiated app launches and code execution for safety.

**Fix:** Set `WINEBOT_ALLOW_HEADLESS_HYBRID=1` and
`WINEBOT_INSTANCE_CONTROL_MODE=hybrid` in the docker-compose environment.
Then call `POST /control/mode {"mode": "hybrid"}` or restart the container.

## CV matching fails

Enforce a fixed resolution and avoid UI scaling. Always use the same `SCREEN` value.

## VNC security

Set `VNC_PASSWORD` and avoid exposing ports publicly. Bind to localhost when running without a password.

## Crash dumps and winedbg

Use winedbg to capture minidumps or automatic crash summaries:

`winedbg --minidump /tmp/crash.mdmp <wpid>`

`winedbg --auto <wpid>`

## Verbose Wine logs

Set `WINEDEBUG` to enable trace channels. Example:

`WINEDEBUG=+seh,+tid,+timestamp`

## docker-compose v1 ContainerConfig error

On some hosts with `docker-compose` v1, you may see `ContainerConfig` errors when recreating containers.
Remove the old container and re-run:

`docker-compose -f compose/docker-compose.yml --profile headless rm -f -s winebot`

`docker-compose -f compose/docker-compose.yml --profile headless up -d --build`
