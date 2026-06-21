#!/usr/bin/env bash
# Notepad++ Demo — Tests: download (Linux curl), install, keyboard, AHK pipe dialog
set -u
API_URL="http://localhost:8000"
PIPE="//wineprefix/drive_c/dialog_handler/pipe.txt"
ART_WIN="C:/artifacts"
ART_LIN="//wineprefix/drive_c/artifacts"
BAT_DIR="//wineprefix/drive_c/artifacts/bats"
NPP_URL="https://github.com/notepad-plus-plus/notepad-plus-plus/releases/download/v8.7.9/npp.8.7.9.Installer.x64.exe"

detect_token() {
  [ -n "${API_TOKEN:-}" ] && { TOKEN="$API_TOKEN"; return; }
  TOKEN=$(MSYS_NO_PATHCONV=1 docker exec compose-winebot-interactive-1 sh -c 'cat /tmp/winebot_api_token 2>/dev/null || cat /winebot-shared/winebot_api_token 2>/dev/null' 2>/dev/null | tr -d '[:space:]' || true)
  [ -z "$TOKEN" ] && { echo "ERROR: No token"; exit 1; }
}
api_post() { curl -sfS -X POST -H "X-API-Key: $TOKEN" -H "Content-Type: application/json" -d "$2" "$API_URL$1" 2>/dev/null; }
ann() { MSYS_NO_PATHCONV=1 docker exec compose-winebot-interactive-1 sh -c "python3 -m automation.recorder annotate --session-dir '$SESSDIR' --text \"$1\" --kind annotation --source demo" 2>/dev/null || true; }
ch()   { MSYS_NO_PATHCONV=1 docker exec compose-winebot-interactive-1 sh -c "python3 -m automation.recorder annotate --session-dir '$SESSDIR' --text \"$1\" --kind chapter --source demo" 2>/dev/null || true; }
verify_file() { MSYS_NO_PATHCONV=1 docker exec compose-winebot-interactive-1 sh -c "test -f $1 && echo EXISTS && wc -c < $1 || echo MISSING" 2>/dev/null; }
pipe_cmd() { MSYS_NO_PATHCONV=1 docker exec compose-winebot-interactive-1 su -s /bin/sh winebot -c "echo '$1' > '$PIPE'" 2>/dev/null; }
pipe_read() { MSYS_NO_PATHCONV=1 docker exec compose-winebot-interactive-1 su -s /bin/sh winebot -c "cat '$PIPE' 2>/dev/null" || true; }
bat_run() {
  local name="$1" content="$2"
  MSYS_NO_PATHCONV=1 docker exec compose-winebot-interactive-1 sh -c "cat > ${BAT_DIR}/${name}.bat << 'BATEOF'
${content}
BATEOF
chown winebot:winebot ${BAT_DIR}/${name}.bat"
  api_post "/apps/run" "{\"path\":\"cmd.exe\",\"args\":\"/c ${ART_WIN}/bats/${name}.bat\",\"detach\":false}" > /dev/null
}
linux_dl() {
  local url="$1" dest="$2"
  MSYS_NO_PATHCONV=1 docker exec compose-winebot-interactive-1 sh -c "curl -sL '$url' -o '$dest' && chown winebot:winebot '$dest' && echo 'Downloaded: ' \$(wc -c < '$dest') ' bytes'" 2>/dev/null
}

detect_token
SESSION=$(curl -s -H "X-API-Key: $TOKEN" "$API_URL/lifecycle/status" | grep -o '"session_id":[[:space:]]*"[^"]*"' | head -1 | sed 's/.*"\([^"]*\)"$/\1/')
SESSDIR="/artifacts/sessions/$SESSION"
CT=$(curl -s -X POST -H "X-API-Key: $TOKEN" "$API_URL/sessions/$SESSION/control/challenge" | grep -o '"token":[[:space:]]*"[^"]*"' | sed 's/.*"\([^"]*\)"$/\1/')
api_post "/sessions/$SESSION/control/grant" "{\"lease_seconds\":7200,\"user_ack\":true,\"challenge_token\":\"$CT\"}" > /dev/null
MSYS_NO_PATHCONV=1 docker exec compose-winebot-interactive-1 mkdir -p "$ART_LIN" "${BAT_DIR}" //wineprefix/drive_c/dialog_handler 2>/dev/null
MSYS_NO_PATHCONV=1 docker exec compose-winebot-interactive-1 chown -R winebot:winebot "$ART_LIN" //wineprefix/drive_c/dialog_handler 2>/dev/null
MSYS_NO_PATHCONV=1 docker cp automation/core/dialog_replacement.ahk compose-winebot-interactive-1://wineprefix/drive_c/dr.ahk 2>/dev/null
MSYS_NO_PATHCONV=1 docker exec compose-winebot-interactive-1 chown winebot:winebot //wineprefix/drive_c/dr.ahk 2>/dev/null
MSYS_NO_PATHCONV=1 docker exec compose-winebot-interactive-1 sh -c '
gosu winebot sh -c "DISPLAY=:99 WINEPREFIX=/wineprefix WINEDEBUG=-all nohup ahk C:/dr.ahk > /wineprefix/drive_c/dh.log 2>&1 < /dev/null &"'
sleep 5

echo "=============================================="
echo "  Notepad++ — Linux curl download, /input/key, AHK pipe"
echo "=============================================="
echo ""

echo "=== Step 1: Download (Linux curl) ==="
ch "Download Notepad++"
ann "Downloading via Linux curl (not Wine cmd.exe)"
linux_dl "$NPP_URL" "${ART_LIN}/npp-installer.exe"
sleep 2
echo "  $(verify_file "${ART_LIN}/npp-installer.exe")"

echo ""
echo "=== Step 2: Silent install ==="
ch "Install Notepad++"
ann "Running installer with /S flag"
bat_run "npp_install" "${ART_WIN}/npp-installer.exe /S"
sleep 8
echo "  notepad++.exe: $(verify_file '//wineprefix/drive_c/Program Files/Notepad++/notepad++.exe')"

echo ""
echo "=== Step 3: Launch + type text ==="
ch "Launch and type via /input/key"
api_post "/apps/run" '{"path":"notepad++.exe","detach":true}' > /dev/null
sleep 4
ann "Notepad++ launched"

API="/input/key"
for line in "Notepad++ Demo - WineBot Automation" " " "Created entirely via API:" "  1. Downloaded by Linux curl" "  2. Installed silently (/S)" "  3. Typed via /input/key (AHK Send)" "  4. Saved via AHK pipe dialog" "" "All without touching a keyboard!"; do
  api_post "$API" "{\"keys\":\"$line\",\"window_title\":\"Notepad\"}" > /dev/null
  api_post "$API" '{"keys":"Return","window_title":"Notepad"}' > /dev/null
  sleep 0.12
done
ann "Content typed via /input/key"

echo ""
echo "=== Step 4: Save via AHK pipe dialog ==="
ch "AHK pipe dialog save"
api_post "$API" '{"keys":"ctrl+s","window_title":"Notepad"}' > /dev/null
sleep 4
ann "Ctrl+S pressed"
pipe_cmd "set_filename:Notepadpp_Demo.txt"
sleep 1.5
pipe_cmd "click_save"
sleep 2
echo "  $(verify_file "${ART_LIN}/Notepadpp_Demo.txt")"

echo ""
echo "=== Step 5: Verify file content ==="
ch "Verify saved file"
MSYS_NO_PATHCONV=1 docker exec compose-winebot-interactive-1 cat "${ART_LIN}/Notepadpp_Demo.txt" 2>/dev/null | head -4
ann "File content verified"

echo ""
echo "=== Step 6: Close + uninstall ==="
ch "Uninstall"
api_post "$API" '{"keys":"alt+f4","window_title":"Notepad"}' > /dev/null
sleep 2
bat_run "npp_cleanup" "del /q ${ART_WIN}/Notepadpp_Demo.txt ${ART_WIN}/npp-installer.exe 2>nul & \"C:/Program Files/Notepad++/Uninstall.exe\" /S 2>nul & rmdir /s /q ${ART_WIN}/bats 2>nul"
sleep 4
ann "Notepad++ uninstalled"

echo ""
echo "=============================================="
echo "  Notepad++ Demo Complete!"
echo "  Download: Linux curl | Install: .bat /S"
echo "  Typing: /input/key | Save: AHK pipe dialog"
echo "=============================================="

api_post "/recording/stop" '{}' 2>/dev/null || true
sleep 2; TRIM_SS="${TRIM_SS:-40}"
MSYS_NO_PATHCONV=1 docker exec compose-winebot-interactive-1 sh -c "
  ffmpeg -y -ss ${TRIM_SS} -i ${SESSDIR}/video_001.mkv -c copy -avoid_negative_ts make_zero /tmp/trimmed.mkv 2>/dev/null
  ffmpeg -y -i /tmp/trimmed.mkv -vf 'fps=8,scale=640:-1:flags=lanczos,split[s0][s1];[s0]palettegen=max_colors=128[p];[s1][p]paletteuse' -loop 0 /tmp/trimmed.gif 2>/dev/null
  echo 'Trimmed:' \$(ls -lh /tmp/trimmed.mkv | awk '{print \$5}') 'GIF:' \$(ls -lh /tmp/trimmed.gif | awk '{print \$5}')
"
echo "Output: docker cp compose-winebot-interactive-1:/tmp/trimmed.mkv demo/output/demo.mkv"
