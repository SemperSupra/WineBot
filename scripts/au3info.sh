#!/usr/bin/env bash
set -euo pipefail

# Source the X11 helper
if [ -f "/scripts/lib/x11_env.sh" ]; then
    source "/scripts/lib/x11_env.sh"
elif [ -f "$(dirname "$0")/lib/x11_env.sh" ]; then
    source "$(dirname "$0")/lib/x11_env.sh"
fi

winebot_ensure_x11_env

# Check for Au3Info
AU3_DIR="/opt/winebot/windows-tools/AutoIt"
if [ -f "$AU3_DIR/Au3Info.exe" ]; then
    EXE="$AU3_DIR/Au3Info.exe"
elif [ -f "$AU3_DIR/Au3Info_x64.exe" ]; then
    EXE="$AU3_DIR/Au3Info_x64.exe"
else
    echo "Error: Au3Info.exe not found in $AU3_DIR"
    exit 1
fi

echo "Starting Au3Info..."
wine "$EXE" &
PID=$!
echo "Au3Info started with PID $PID"
wait $PID
