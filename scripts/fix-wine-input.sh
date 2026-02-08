#!/usr/bin/env bash
set -euo pipefail

echo "Applying Wine X11 Driver fixes..."

# Disable window manager management (Managed=N)
wine reg add "HKCU\Software\Wine\X11 Driver" /v Managed /t REG_SZ /d "N" /f
# Re-enable XInput2
wine reg add "HKCU\Software\Wine\X11 Driver" /v UseXInput2 /t REG_SZ /d "Y" /f

# Ensure Window Manager manages windows (better focus handling with Openbox)
wine reg add "HKCU\Software\Wine\X11 Driver" /v Managed /t REG_SZ /d "Y" /f

# Disable GrabFullscreen (prevents Wine from stealing mouse exclusive mode)
wine reg add "HKCU\Software\Wine\X11 Driver" /v GrabFullscreen /t REG_SZ /d "N" /f

# Disable UseTakeFocus (let WM handle focus)
wine reg add "HKCU\Software\Wine\X11 Driver" /v UseTakeFocus /t REG_SZ /d "N" /f

# Force Wine virtual desktop to match screen resolution
wine reg add "HKCU\Software\Wine\Explorer" /v Desktop /t REG_SZ /d "Default" /f
wine reg add "HKCU\Software\Wine\Explorer\Desktops" /v Default /t REG_SZ /d "1280x720" /f

echo "Restarting Wine..."
# wineserver -k
# Wait for restart
sleep 2
SCREEN="${SCREEN:-1920x1080x24}"
wine explorer /desktop=Default,${SCREEN%x*} >/dev/null 2>&1 &
sleep 2
echo "Wine restarted with new input settings."
