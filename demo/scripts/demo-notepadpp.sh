#!/usr/bin/env bash
# Notepad++ Demo — download (Linux curl), install (wine /S), keyboard input, pipe dialog save
set -u
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
source "$SCRIPT_DIR/_demo_common.sh"
init_session
ensure_dirs

NPP_URL="https://github.com/notepad-plus-plus/notepad-plus-plus/releases/download/v8.7.9/npp.8.7.9.Installer.x64.exe"

echo "=============================================="
echo "  Notepad++ Demo — Install / Edit / Save"
echo "=============================================="
echo ""

echo "=== Setup: Deploy AHK Pipe Handler ==="
ch "AHK handler setup"
setup_ahk_handler 0   # No dialog watcher needed for Notepad++

echo ""
echo "=== Step 1: Download Notepad++ ==="
ch "Download Notepad++"
linux_dl "$NPP_URL" "$PREFIX/npp-installer.exe"

echo ""
echo "=== Step 2: Install via wine ==="
ch "Install Notepad++"
ann "Running Notepad++ installer via gosu winebot wine /S"
wine_install "$PREFIX/npp-installer.exe" "/S"
NPP=$(verify_file "$PREFIX/Program Files/Notepad++/notepad++.exe")
echo "  notepad++.exe: $NPP"
ann "Notepad++ installed"

echo ""
echo "=== Step 3: Launch + type via /input/key ==="
ch "Type text via /input/key"
api_post "/apps/run" '{"path":"notepad++.exe","detach":true}' > /dev/null
cv_wait "Notepad" 15 || sleep 4
ann "Notepad++ launched via /apps/run"
snap "notepadpp_launched"
ann_expect "Notepad++ editor visible" "Notepad"

API="/input/key"
for line in "Notepad++ Demo - WineBot Automation" " " "Created via API:" "  1. Linux curl download" "  2. wine /S install" "  3. /input/key for text entry" "  4. AHK pipe dialog for file save" "" "All through the API pipeline!"; do
  api_post "$API" "{\"keys\":\"$line\",\"window_title\":\"Notepad\"}" > /dev/null
  api_post "$API" '{"keys":"Return","window_title":"Notepad"}' > /dev/null
  sleep 0.1
done
ann "Content typed via /input/key (AHK Send backend)"

echo ""
echo "=== Step 4: Save via AHK pipe dialog ==="
ch "Save via pipe dialog"
api_post "$API" '{"keys":"ctrl+s","window_title":"Notepad"}' > /dev/null
sleep 4
ann "Ctrl+S pressed — AHK pipe dialog opened"
snap "notepadpp_save_dialog"
ann_expect "Save dialog replacement visible" "WineBot Save Dialog"
pipe_cmd "set_filename:Notepadpp_Demo_v2.txt"
sleep 1.5
pipe_cmd "click_save"
sleep 2
echo "  $(verify_file "$PREFIX/Notepadpp_Demo_v2.txt")"

echo ""
echo "=== Step 5: Verify file ==="
ch "Verify file content"
MSYS_NO_PATHCONV=1 docker exec "$CONTAINER" cat "$PREFIX/Notepadpp_Demo_v2.txt" 2>/dev/null | head -3
ann "File content verified on disk"
snap "notepadpp_file_verified"

echo ""
echo "=== Step 6: Close + uninstall ==="
ch "Uninstall"
api_post "$API" '{"keys":"alt+f4","window_title":"Notepad"}' > /dev/null
sleep 2
MSYS_NO_PATHCONV=1 docker exec "$CONTAINER" sh -c "rm -f $PREFIX/Notepadpp_Demo_v2.txt $PREFIX/npp-installer.exe 2>/dev/null"
MSYS_NO_PATHCONV=1 docker exec "$CONTAINER" sh -c "
  gosu winebot env DISPLAY=:99 WINEPREFIX=/wineprefix WINEDEBUG=-all \
  wine '$PREFIX/Program Files/Notepad++/Uninstall.exe' /S 2>/dev/null &
  sleep 4"
MSYS_NO_PATHCONV=1 docker exec "$CONTAINER" sh -c "rm -rf '$PREFIX/Program Files/Notepad++' 2>/dev/null"
ann "Notepad++ uninstalled"

echo ""
echo "=============================================="
echo "  Notepad++ Demo Complete!"
echo "  Download: Linux curl  Install: wine /S"
echo "  Type: /input/key    Save: AHK pipe dialog"
echo "=============================================="

stop_recording
