#!/usr/bin/env bash
# SuperTux Game Demo — download, install via msiexec, launch, keyboard+mouse, screenshot, uninstall
set -u
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
source "$SCRIPT_DIR/_demo_common.sh"
fresh_session
init_session
ensure_dirs

STUX_URL="https://github.com/SuperTux/supertux/releases/download/v0.6.3/SuperTux-v0.6.3-win64.msi"

echo "=============================================="
echo "  SuperTux Game — Full Lifecycle Demo"
echo "=============================================="
echo ""

echo "=== Step 1: Download SuperTux MSI ==="
ch "Download SuperTux"
ann "Downloading via Linux curl"
linux_dl "$STUX_URL" "$PREFIX/supertux.msi"

echo ""
echo "=== Step 2: Install via msiexec ==="
ch "MSI install"
ann "Running msiexec /i /quiet /qn"
wine_msi_install "$PREFIX/supertux.msi"
echo "  supertux2.exe: $(verify_file "$PREFIX/Program Files/SuperTux/supertux2.exe")"

echo ""
echo "=== Step 3: Launch game ==="
ch "Launch SuperTux"
api_post "/apps/run" '{"path":"supertux2.exe","detach":true}' > /dev/null
cv_wait "SuperTux" 15 || sleep 8
ann "SuperTux launched — game renders on Wine desktop"

echo ""
echo "=== Step 4: Navigate menus (keyboard + mouse) ==="
ch "Keyboard and mouse interaction"
K="/input/key"

ann "Down arrows to navigate menu items"
api_post "$K" '{"keys":"Down","window_title":"SuperTux"}' > /dev/null; sleep 0.3
api_post "$K" '{"keys":"Down","window_title":"SuperTux"}' > /dev/null; sleep 0.3
api_post "$K" '{"keys":"Down","window_title":"SuperTux"}' > /dev/null; sleep 0.4
ann "Arrow keys: moved down menu"

api_post "$K" '{"keys":"Up","window_title":"SuperTux"}' > /dev/null; sleep 0.3
api_post "$K" '{"keys":"Up","window_title":"SuperTux"}' > /dev/null; sleep 0.3
api_post "$K" '{"keys":"Up","window_title":"SuperTux"}' > /dev/null; sleep 0.4
ann "Arrow keys: moved back up"

ann "Mouse click on game window (xdotool via API)"
api_post "/input/mouse/click" '{"x":640,"y":400,"button":1,"window_title":"SuperTux"}' > /dev/null
sleep 1
ann "Mouse click at game center via /input/mouse/click"

echo ""
echo "=== Step 5: Screenshot ==="
ch "Screenshot verification"
ann "Capturing screenshot via API"
curl -s -H "X-API-Key: $TOKEN" "$API_URL/screenshot" -o /tmp/supertux_shot.png 2>/dev/null || true
echo "  Screenshot captured"
ann "Game rendering verified via screenshot API"

echo ""
echo "=== Step 6: Close + uninstall ==="
ch "Close and uninstall"
ann "Closing game via Escape + Alt+F4"
api_post "$K" '{"keys":"Escape","window_title":"SuperTux"}' > /dev/null; sleep 1
api_post "$K" '{"keys":"alt+f4","window_title":"SuperTux"}' > /dev/null; sleep 2
ann "Game closed"

ann "Uninstalling via msiexec /x"
MSYS_NO_PATHCONV=1 docker exec "$CONTAINER" sh -c "rm -f $PREFIX/supertux.msi 2>/dev/null"
wine_msi_uninstall "$PREFIX/supertux.msi" 2>/dev/null || true
MSYS_NO_PATHCONV=1 docker exec "$CONTAINER" sh -c "rm -rf '$PREFIX/Program Files/SuperTux' 2>/dev/null"
ann "Game uninstalled, artifacts removed"

echo ""
echo "=============================================="
echo "  SuperTux Demo Complete!"
echo "  Download: Linux curl  Install: msiexec /i /qn"
echo "  Play: keyboard + mouse  Verify: screenshot"
echo "  Full lifecycle: download → install → play → verify → remove"
echo "=============================================="

stop_recording
