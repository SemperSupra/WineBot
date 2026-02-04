#!/usr/bin/env bash
set -euo pipefail

echo "Applying Wine X11 Driver fixes..."

# Disable XInput2 (forces Core X11 input, usually fixes vnc/xdotool injection)
wine reg add "HKCU\Software\Wine\X11 Driver" /v UseXInput2 /t REG_SZ /d "N" /f

# Ensure Window Manager manages windows (better focus handling with Openbox)
wine reg add "HKCU\Software\Wine\X11 Driver" /v Managed /t REG_SZ /d "Y" /f

# Disable GrabFullscreen (prevents Wine from stealing mouse exclusive mode)
wine reg add "HKCU\Software\Wine\X11 Driver" /v GrabFullscreen /t REG_SZ /d "N" /f

# Disable UseTakeFocus (let WM handle focus)
wine reg add "HKCU\Software\Wine\X11 Driver" /v UseTakeFocus /t REG_SZ /d "N" /f

echo "Restarting Wine..."
wineserver -k
# Wait for restart
sleep 2
wine explorer >/dev/null 2>&1 &
sleep 2
echo "Wine restarted with new input settings."
