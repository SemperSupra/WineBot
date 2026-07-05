#!/usr/bin/env bash
set -euo pipefail

if [ "${WINEBOT_SUPPRESS_DEPRECATION:-0}" != "1" ]; then
    echo "DEPRECATED: scripts/winspy.sh compatibility wrapper is deprecated. Use WinInspect directly or the /inspect/window API." >&2
fi

# Source the X11 helper
if [ -f "/scripts/lib/x11_env.sh" ]; then
    source "/scripts/lib/x11_env.sh"
elif [ -f "$(dirname "$0")/lib/x11_env.sh" ]; then
    source "$(dirname "$0")/lib/x11_env.sh"
fi

winebot_ensure_x11_env

WINSPY_DIR="/opt/winebot/windows-tools/WinSpy"
EXE="$WINSPY_DIR/wininspect-gui.exe"

if [ ! -f "$EXE" ]; then
    if [ -f "$HOME/windows-tools/WinSpy/wininspect-gui.exe" ]; then
        WINSPY_DIR="$HOME/windows-tools/WinSpy"
        EXE="$WINSPY_DIR/wininspect-gui.exe"
    fi
fi

if [ ! -f "$EXE" ]; then
    FOUND=$(find "$WINSPY_DIR" -iname "wininspect-gui.exe" -print -quit 2>/dev/null || true)
    if [ -z "$FOUND" ] && [ -d "$HOME/windows-tools/WinSpy" ]; then
         FOUND=$(find "$HOME/windows-tools/WinSpy" -iname "wininspect-gui.exe" -print -quit 2>/dev/null || true)
    fi
    if [ -n "$FOUND" ]; then
        EXE="$FOUND"
    else
        echo "Error: wininspect-gui.exe not found."
        echo "Please rebuild the image or run 'bash /scripts/setup/install-inspectors.sh' inside the container."
        exit 1
    fi
fi

echo "Starting WinInspect GUI..."
wine "$EXE" &
PID=$!
echo "WinInspect GUI started with PID $PID"
wait $PID
