#!/usr/bin/env bash
# VLC Demo — download (Linux curl), install (wine /S), keyboard menu navigation
set -u
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
source "$SCRIPT_DIR/_demo_common.sh"
init_session
ensure_dirs

VLC_URL="https://get.videolan.org/vlc/3.0.21/win64/vlc-3.0.21-win64.exe"

echo "=============================================="
echo "  VLC Demo — Install / Keyboard Nav"
echo "=============================================="
echo ""

echo "=== Step 1: Download + Install ==="
ch "Download and install VLC"
linux_dl "$VLC_URL" "$PREFIX/vlc-installer.exe"
ann "Installing VLC"
wine_install "$PREFIX/vlc-installer.exe" "/S"
echo "  vlc.exe: $(verify_file "$PREFIX/Program Files/VideoLAN/VLC/vlc.exe")"

echo ""
echo "=== Step 2: Launch VLC ==="
ch "Launch and navigate menus"
api_post "/apps/run" '{"path":"vlc.exe","args":"--no-qt-privacy-ask","detach":true}' > /dev/null
cv_wait "VLC" 15 || sleep 6
ann "VLC launched via /apps/run"

echo ""
echo "=== Step 3: Keyboard menu navigation ==="
ch "Keyboard shortcuts: Alt+M, Alt+H, arrows"
K="/input/key"

ann "Alt+M opens Media menu"
api_post "$K" '{"keys":"alt+m","window_title":"VLC"}' > /dev/null; sleep 1
ann "Media menu open — escape to close"
api_post "$K" '{"keys":"Escape","window_title":"VLC"}' > /dev/null; sleep 1

ann "Alt+H opens Help → About"
api_post "$K" '{"keys":"alt+h","window_title":"VLC"}' > /dev/null; sleep 1
api_post "$K" '{"keys":"Down","window_title":"VLC"}' > /dev/null; sleep 0.3
api_post "$K" '{"keys":"Down","window_title":"VLC"}' > /dev/null; sleep 0.3
api_post "$K" '{"keys":"Down","window_title":"VLC"}' > /dev/null; sleep 0.3
api_post "$K" '{"keys":"Return","window_title":"VLC"}' > /dev/null; sleep 2
ann "About dialog opened via keyboard navigation"
api_post "$K" '{"keys":"Escape","window_title":"VLC"}' > /dev/null; sleep 1
ann "About dialog dismissed"

ann "Ctrl+O — Open File dialog (Shell32 hook target)"
api_post "$K" '{"keys":"ctrl+o","window_title":"VLC"}' > /dev/null; sleep 3
api_post "$K" '{"keys":"Escape","window_title":"VLC"}' > /dev/null; sleep 1
ann "Open File invoked via Ctrl+O"

echo ""
echo "=== Step 4: Close + cleanup ==="
ch "Close and uninstall"
ann "Closing VLC"
api_post "$K" '{"keys":"alt+f4","window_title":"VLC"}' > /dev/null; sleep 2
MSYS_NO_PATHCONV=1 docker exec "$CONTAINER" sh -c "rm -f $PREFIX/vlc-installer.exe 2>/dev/null"
MSYS_NO_PATHCONV=1 docker exec "$CONTAINER" sh -c "
  gosu winebot env DISPLAY=:99 WINEPREFIX=/wineprefix WINEDEBUG=-all \
  wine '$PREFIX/Program Files/VideoLAN/VLC/Uninstall.exe' /S 2>/dev/null &
  sleep 5"
MSYS_NO_PATHCONV=1 docker exec "$CONTAINER" sh -c "rm -rf '$PREFIX/Program Files/VideoLAN' 2>/dev/null"
ann "VLC uninstalled"

echo ""
echo "=============================================="
echo "  VLC Demo Complete!"
echo "  /input/key chords (Alt+M/H), arrows, Escape"
echo "=============================================="

stop_recording
