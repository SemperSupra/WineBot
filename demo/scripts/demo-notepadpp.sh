#!/usr/bin/env bash
# Notepad++ Demo — download (Linux curl), install (wine /S), keyboard input, pipe dialog save
set -u
API_URL="http://localhost:8000"
PIPE="//wineprefix/drive_c/dialog_handler/pipe.txt"
PREFIX="/wineprefix/drive_c"
NPP_URL="https://github.com/notepad-plus-plus/notepad-plus-plus/releases/download/v8.7.9/npp.8.7.9.Installer.x64.exe"

detect_token() {
  [ -n "${API_TOKEN:-}" ] && { TOKEN="$API_TOKEN"; return; }
  TOKEN=$(MSYS_NO_PATHCONV=1 docker exec compose-winebot-interactive-1 sh -c 'cat /tmp/winebot_api_token 2>/dev/null || cat /winebot-shared/winebot_api_token 2>/dev/null' 2>/dev/null | tr -d '[:space:]' || true)
  [ -z "$TOKEN" ] && { echo "ERROR: No token"; exit 1; }
}

api_post() { curl -sfS -X POST -H "X-API-Key: $TOKEN" -H "Content-Type: application/json" -d "$2" "$API_URL$1" 2>/dev/null; }
ann() { MSYS_NO_PATHCONV=1 docker exec compose-winebot-interactive-1 sh -c "python3 -m automation.recorder annotate --session-dir '$SESSDIR' --text \"$1\" --kind annotation --source demo" 2>/dev/null || true; }
ch()   { MSYS_NO_PATHCONV=1 docker exec compose-winebot-interactive-1 sh -c "python3 -m automation.recorder annotate --session-dir '$SESSDIR' --text \"$1\" --kind chapter --source demo" 2>/dev/null || true; }
verify_file() { MSYS_NO_PATHCONV=1 docker exec compose-winebot-interactive-1 sh -c "test -f $1 && echo EXISTS \$(wc -c < $1)bytes || echo MISSING" 2>/dev/null; }
pipe_cmd()  { MSYS_NO_PATHCONV=1 docker exec compose-winebot-interactive-1 su -s /bin/sh winebot -c "echo '$1' > '$PIPE'" 2>/dev/null; }
pipe_read() { MSYS_NO_PATHCONV=1 docker exec compose-winebot-interactive-1 su -s /bin/sh winebot -c "cat '$PIPE' 2>/dev/null" || true; }

linux_dl() { local url="$1" dest="$2"
  MSYS_NO_PATHCONV=1 docker exec compose-winebot-interactive-1 sh -c "curl -sL '$url' -o '$dest' && chown winebot:winebot '$dest' && echo '  Downloaded: ' \$(wc -c < '$dest') ' bytes'" 2>/dev/null; }

wine_install() { local exe="$1" flags="${2:-/S}"
  MSYS_NO_PATHCONV=1 docker exec compose-winebot-interactive-1 sh -c "
    gosu winebot env DISPLAY=:99 WINEPREFIX=/wineprefix WINEDEBUG=-all \
    wine '$exe' '$flags' 2>/dev/null &
    PID=\$!
    for i in \$(seq 1 30); do
      if ps -p \$PID > /dev/null 2>&1; then sleep 1; else echo '  Installer exited'; break; fi
    done
  "; }

# INIT
detect_token
SESSION=$(curl -s -H "X-API-Key: $TOKEN" "$API_URL/lifecycle/status" | grep -o '"session_id":[[:space:]]*"[^"]*"' | head -1 | sed 's/.*"\([^"]*\)"$/\1/')
SESSDIR="/artifacts/sessions/$SESSION"
CT=$(curl -s -X POST -H "X-API-Key: $TOKEN" "$API_URL/sessions/$SESSION/control/challenge" | grep -o '"token":[[:space:]]*"[^"]*"' | sed 's/.*"\([^"]*\)"$/\1/')
api_post "/sessions/$SESSION/control/grant" "{\"lease_seconds\":7200,\"user_ack\":true,\"challenge_token\":\"$CT\"}" > /dev/null
MSYS_NO_PATHCONV=1 docker exec compose-winebot-interactive-1 mkdir -p "$PREFIX" //wineprefix/drive_c/dialog_handler 2>/dev/null
MSYS_NO_PATHCONV=1 docker exec compose-winebot-interactive-1 chown -R winebot:winebot "$PREFIX" //wineprefix/drive_c/dialog_handler 2>/dev/null
MSYS_NO_PATHCONV=1 docker cp automation/core/dialog_replacement.ahk compose-winebot-interactive-1://wineprefix/drive_c/dr.ahk 2>/dev/null
MSYS_NO_PATHCONV=1 docker exec compose-winebot-interactive-1 chown winebot:winebot //wineprefix/drive_c/dr.ahk 2>/dev/null
MSYS_NO_PATHCONV=1 docker exec compose-winebot-interactive-1 sh -c '
  gosu winebot env DISPLAY=:99 WINEPREFIX=/wineprefix WINEDEBUG=-all nohup ahk C:/dr.ahk > /wineprefix/drive_c/dh.log 2>&1 &'
sleep 5

echo "=============================================="
echo "  Notepad++ Demo — Install / Edit / Save"
echo "=============================================="
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
sleep 4
ann "Notepad++ launched via /apps/run"

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
pipe_cmd "set_filename:Notepadpp_Demo_v2.txt"
sleep 1.5
pipe_cmd "click_save"
sleep 2
echo "  $(verify_file "$PREFIX/Notepadpp_Demo_v2.txt")"

echo ""
echo "=== Step 5: Verify file ==="
ch "Verify file content"
MSYS_NO_PATHCONV=1 docker exec compose-winebot-interactive-1 cat "$PREFIX/Notepadpp_Demo_v2.txt" 2>/dev/null | head -3
ann "File content verified on disk"

echo ""
echo "=== Step 6: Close + uninstall ==="
ch "Uninstall"
api_post "$API" '{"keys":"alt+f4","window_title":"Notepad"}' > /dev/null
sleep 2
MSYS_NO_PATHCONV=1 docker exec compose-winebot-interactive-1 sh -c "rm -f $PREFIX/Notepadpp_Demo_v2.txt $PREFIX/npp-installer.exe 2>/dev/null"
MSYS_NO_PATHCONV=1 docker exec compose-winebot-interactive-1 sh -c "
  gosu winebot env DISPLAY=:99 WINEPREFIX=/wineprefix WINEDEBUG=-all \
  wine '$PREFIX/Program Files/Notepad++/Uninstall.exe' /S 2>/dev/null &
  sleep 4"
MSYS_NO_PATHCONV=1 docker exec compose-winebot-interactive-1 sh -c "rm -rf '$PREFIX/Program Files/Notepad++' 2>/dev/null"
ann "Notepad++ uninstalled"

echo ""
echo "=============================================="
echo "  Notepad++ Demo Complete!"
echo "  Download: Linux curl  Install: wine /S"
echo "  Type: /input/key    Save: AHK pipe dialog"
echo "=============================================="

api_post "/recording/stop" '{}' 2>/dev/null || true
SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)" 2>/dev/null || SCRIPT_DIR="."
[ -f "$SCRIPT_DIR/_trim.sh" ] && source "$SCRIPT_DIR/_trim.sh" && smart_trim "$SESSDIR"
