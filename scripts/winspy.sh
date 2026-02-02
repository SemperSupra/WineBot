#!/usr/bin/env bash
set -euo pipefail

# Source the X11 helper
if [ -f "/scripts/lib/x11_env.sh" ]; then
    source "/scripts/lib/x11_env.sh"
elif [ -f "$(dirname "$0")/lib/x11_env.sh" ]; then
    source "$(dirname "$0")/lib/x11_env.sh"
fi

winebot_ensure_x11_env

WINSPY_DIR="/opt/winebot/windows-tools/WinSpy"
# Often standard unzip puts it in current dir or subdir.
# The zip has "WinSpy.exe".
EXE="$WINSPY_DIR/WinSpy.exe"

if [ ! -f "$EXE" ]; then
    # Try finding it in case structure differs
    FOUND=$(find "$WINSPY_DIR" -name "WinSpy.exe" -print -quit)
    if [ -n "$FOUND" ]; then
        EXE="$FOUND"
    else
        echo "Error: WinSpy.exe not found."
        echo "Please run 'bash /opt/winebot/windows-tools/install_inspectors.sh' (if inside container)"
        echo "or 'windows-tools/install_inspectors.sh' (if outside and mounting volume)."
        exit 1
    fi
fi

echo "Starting WinSpy..."
wine "$EXE" &
PID=$!
echo "WinSpy started with PID $PID"
wait $PID
