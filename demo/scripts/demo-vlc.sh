#!/usr/bin/env bash
# VLC Demo — Tests: download, install, keyboard menu nav, Shell32 hook
set -u
API_URL="http://localhost:8000"
ART_WIN="C:/artifacts"
ART_LIN="//wineprefix/drive_c/artifacts"
BAT_DIR="//wineprefix/drive_c/artifacts/bats"
VLC_URL="https://get.videolan.org/vlc/3.0.21/win64/vlc-3.0.21-win64.exe"

detect_token() {
  [ -n "${API_TOKEN:-}" ] && { TOKEN="$API_TOKEN"; return; }
  TOKEN=$(MSYS_NO_PATHCONV=1 docker exec compose-winebot-interactive-1 sh -c 'cat /tmp/winebot_api_token 2>/dev/null || cat /winebot-shared/winebot_api_token 2>/dev/null' 2>/dev/null | tr -d '[:space:]' || true)
  [ -z "$TOKEN" ] && { echo "ERROR: No token"; exit 1; }
}
api_post() { curl -sfS -X POST -H "X-API-Key: $TOKEN" -H "Content-Type: application/json" -d "$2" "$API_URL$1" 2>/dev/null; }
ann() { MSYS_NO_PATHCONV=1 docker exec compose-winebot-interactive-1 sh -c "python3 -m automation.recorder annotate --session-dir '$SESSDIR' --text \"$1\" --kind annotation --source demo" 2>/dev/null || true; }
ch()   { MSYS_NO_PATHCONV=1 docker exec compose-winebot-interactive-1 sh -c "python3 -m automation.recorder annotate --session-dir '$SESSDIR' --text \"$1\" --kind chapter --source demo" 2>/dev/null || true; }
verify_file() { MSYS_NO_PATHCONV=1 docker exec compose-winebot-interactive-1 sh -c "test -f $1 && echo EXISTS && wc -c < $1 || echo MISSING" 2>/dev/null; }
bat_run() {
  local name="$1" content="$2"
  MSYS_NO_PATHCONV=1 docker exec compose-winebot-interactive-1 sh -c "cat > ${BAT_DIR}/${name}.bat << 'BATEOF'
${content}
BATEOF
chown winebot:winebot ${BAT_DIR}/${name}.bat"
  api_post "/apps/run" "{\"path\":\"cmd.exe\",\"args\":\"/c ${ART_WIN}/bats/${name}.bat\",\"detach\":false}" > /dev/null
}

detect_token
SESSION=$(curl -s -H "X-API-Key: $TOKEN" "$API_URL/lifecycle/status" | grep -o '"session_id":[[:space:]]*"[^"]*"' | head -1 | sed 's/.*"\([^"]*\)"$/\1/')
SESSDIR="/artifacts/sessions/$SESSION"
CT=$(curl -s -X POST -H "X-API-Key: $TOKEN" "$API_URL/sessions/$SESSION/control/challenge" | grep -o '"token":[[:space:]]*"[^"]*"' | sed 's/.*"\([^"]*\)"$/\1/')
api_post "/sessions/$SESSION/control/grant" "{\"lease_seconds\":7200,\"user_ack\":true,\"challenge_token\":\"$CT\"}" > /dev/null
MSYS_NO_PATHCONV=1 docker exec compose-winebot-interactive-1 mkdir -p "$ART_LIN" "${BAT_DIR}" 2>/dev/null
MSYS_NO_PATHCONV=1 docker exec compose-winebot-interactive-1 chown -R winebot:winebot "$ART_LIN" 2>/dev/null

echo "=============================================="
echo "  VLC Demo — Menu Navigation + Shell32 Hook"
echo "=============================================="
echo ""

echo "=== Step 1: Download + Install VLC ==="
ch "Download and install VLC"
ann "Downloading VLC installer via .bat script"
bat_run "vlc_dl" "curl -L -o ${ART_WIN}/vlc-installer.exe ${VLC_URL}"
sleep 10
echo "  $(verify_file "${ART_LIN}/vlc-installer.exe")"

ann "Installing VLC with /S flag"
bat_run "vlc_install" "${ART_WIN}/vlc-installer.exe /S"
sleep 8
echo "  vlc.exe: $(verify_file '//wineprefix/drive_c/Program Files/VideoLAN/VLC/vlc.exe')"

echo ""
echo "=== Step 2: Launch VLC ==="
ch "Launch VLC"
bat_run "vlc_launch" "start \"\" /b \"C:/Program Files/VideoLAN/VLC/vlc.exe\" --no-qt-privacy-ask"
sleep 6
ann "VLC launched"

echo ""
echo "=== Step 3: Navigate menus via /input/key ==="
ch "Keyboard menu navigation"
K="/input/key"
ann "Alt+M opens Media menu"
api_post "$K" '{"keys":"alt+m","window_title":"VLC"}' > /dev/null; sleep 1
api_post "$K" '{"keys":"Escape","window_title":"VLC"}' > /dev/null; sleep 1
ann "Media menu opened and closed via keyboard"

ann "Alt+H opens Help menu, navigate to About"
api_post "$K" '{"keys":"alt+h","window_title":"VLC"}' > /dev/null; sleep 1
api_post "$K" '{"keys":"Down","window_title":"VLC"}' > /dev/null; sleep 0.3
api_post "$K" '{"keys":"Down","window_title":"VLC"}' > /dev/null; sleep 0.3
api_post "$K" '{"keys":"Down","window_title":"VLC"}' > /dev/null; sleep 0.3
api_post "$K" '{"keys":"Return","window_title":"VLC"}' > /dev/null; sleep 2
ann "About dialog opened via Alt+H + Down + Return"
api_post "$K" '{"keys":"Escape","window_title":"VLC"}' > /dev/null; sleep 1
ann "About dialog dismissed"

echo ""
echo "=== Step 4: Ctrl+O Open File (Shell32 hook) ==="
ch "Shell32 hook: Open File dialog"
ann "Ctrl+O triggers Shell32 SHBrowseForFolderW hook"
api_post "$K" '{"keys":"ctrl+o","window_title":"VLC"}' > /dev/null; sleep 3
api_post "$K" '{"keys":"Escape","window_title":"VLC"}' > /dev/null; sleep 1
ann "Open File dialog intercepted by Shell32 hook"

echo ""
echo "=== Step 5: Close + Uninstall ==="
ch "Close and uninstall"
ann "Closing VLC"
api_post "$K" '{"keys":"alt+f4","window_title":"VLC"}' > /dev/null; sleep 2
bat_run "vlc_rm" "del /q ${ART_WIN}/vlc-installer.exe 2>nul & \"C:/Program Files/VideoLAN/VLC/Uninstall.exe\" /S 2>nul & rmdir /s /q ${ART_WIN}/bats 2>nul"
sleep 5
ann "VLC uninstalled"

echo ""
echo "=============================================="
echo "  VLC Demo Complete!"
echo "  /input/key for menus, Shell32 hook for Open"
echo "=============================================="

api_post "/recording/stop" '{}' 2>/dev/null || true
sleep 2
TRIM_SS="${TRIM_SS:-40}"
MSYS_NO_PATHCONV=1 docker exec compose-winebot-interactive-1 sh -c "
  ffmpeg -y -ss ${TRIM_SS} -i ${SESSDIR}/video_001.mkv -c copy -avoid_negative_ts make_zero /tmp/trimmed.mkv 2>/dev/null
  ffmpeg -y -i /tmp/trimmed.mkv -vf 'fps=8,scale=640:-1:flags=lanczos,split[s0][s1];[s0]palettegen=max_colors=128[p];[s1][p]paletteuse' -loop 0 /tmp/trimmed.gif 2>/dev/null
  echo Trimmed: \$(ls -lh /tmp/trimmed.mkv | awk '{print \$5}') GIF: \$(ls -lh /tmp/trimmed.gif | awk '{print \$5}')
"
echo "Output: docker cp compose-winebot-interactive-1:/tmp/trimmed.mkv demo/output/demo.mkv"
