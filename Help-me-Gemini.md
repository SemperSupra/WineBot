# Help-me-Gemini.md

## Goal
Help me debug a **mouse click mapping issue** in a Wine + X11 + noVNC stack. Keyboard input works, but **mouse clicks do not open menus or folders** inside Wine apps (e.g., Wine Explorer, Notepad). I need a root cause and a reliable fix.

## Environment
- Host: Linux, Docker Compose, interactive container
- X server: `Xvfb :99` (1920x1080x24)
- Window manager: **Openbox**
- VNC server: **x11vnc**
- noVNC: **websockify + noVNC** (embedded in `/ui` dashboard)
- Wine: running `explorer.exe /desktop` and apps like Notepad

## Symptom
- You can **move/activate** windows with the mouse.
- **Keyboard input works** (Alt+F opens Notepad menu).
- **Mouse clicks inside Wine app client areas** do NOT open menus or open folders.

## Important observations
I wrote an automated diagnostic script that opens Wine Notepad and compares screenshots before/after menu opens:

- Keyboard opens menu → **diff ~27k pixels**
- Mouse click (via `xdotool` *inside X*, not via noVNC) **does open menu** → diff > 0

That proves:
- Openbox and Wine accept mouse input when injected at the X server level.
- The problem is likely **noVNC input mapping/scaling**, not Openbox.

## Diagnostic Script (already in repo)
`scripts/diagnose-mouse-input.sh`
- Launches Wine Notepad
- Captures window screenshot
- Opens menu via keyboard (Alt+F) and via mouse click using `xdotool` relative to window
- Uses ImageMagick `compare -metric AE` to detect changes

Recent run output:
```
Keyboard diff pixels: 27780
Mouse menu opened with offset 45.
```
So X-level mouse input is OK.

## What I’ve tried (no success)
1. Adjusted Openbox mouse bindings (removed Client binds, only Titlebar/Frame/Root binds left).
2. Tweaked noVNC settings:
   - `scaleViewport = true/false`
   - `resizeSession = false`
   - `clipViewport = true/false`
3. Adjusted CSS canvas scaling:
   - Removed forced `width/height: 100%`
   - Ensured `max-width/height` is none
4. Logged canvas vs client sizes to detect scaling mismatch.

## What I need from you
Please propose **specific fixes** and **diagnostic steps** to verify the noVNC input mapping.

### Things to consider
- noVNC RFB options (`scaleViewport`, `resizeSession`, `clipViewport`, `viewOnly`, `focus`)
- Canvas/CSS scaling issues (client size vs framebuffer size)
- Browser zoom or device pixel ratio issues
- x11vnc options that might affect pointer events (e.g., `-noxrecord`, `-noxfixes`, `-noxdamage`, `-cursor`, `-ncache`)
- VNC server scaling vs client scaling
- How to force true **1:1 input mapping** reliably

## What you can output
- A prioritized list of root-cause hypotheses.
- A step-by-step test plan.
- Recommended config changes for noVNC, x11vnc, or Openbox.
- Optional: code snippets or diffs for a fix.

## Bonus
If possible, propose a UI toggle to switch between "scale-to-fit" and "1:1" modes in noVNC, with a note on correct CSS/canvas configuration.
