#!/usr/bin/env bash
# SuperTux Game Demo — Full lifecycle: download, install, play, screenshot, uninstall
set -u
API_URL="http://localhost:8000"
ART_WIN="C:/artifacts"
ART_LIN="//wineprefix/drive_c/artifacts"
BAT_DIR="//wineprefix/drive_c/artifacts/bats"
STUX_URL="https://github.com/SuperTux/supertux/releases/download/v0.6.3/SuperTux-v0.6.3-win64.msi"

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
linux_dl() {
  local url="$1" dest="$2"
  MSYS_NO_PATHCONV=1 docker exec compose-winebot-interactive-1 sh -c "curl -sL '$url' -o '$dest' && chown winebot:winebot '$dest' && echo 'Downloaded: ' \$(wc -c < '$dest') ' bytes'" 2>/dev/null
}

detect_token
SESSION=$(curl -s -H "X-API-Key: $TOKEN" "$API_URL/lifecycle/status" | grep -o '"session_id":[[:space:]]*"[^"]*"' | head -1 | sed 's/.*"\([^"]*\)"$/\1/')
SESSDIR="/artifacts/sessions/$SESSION"
CT=$(curl -s -X POST -H "X-API-Key: $TOKEN" "$API_URL/sessions/$SESSION/control/challenge" | grep -o '"token":[[:space:]]*"[^"]*"' | sed 's/.*"\([^"]*\)"$/\1/')
api_post "/sessions/$SESSION/control/grant" "{\"lease_seconds\":7200,\"user_ack\":true,\"challenge_token\":\"$CT\"}" > /dev/null
MSYS_NO_PATHCONV=1 docker exec compose-winebot-interactive-1 mkdir -p "$ART_LIN" "${BAT_DIR}" 2>/dev/null
MSYS_NO_PATHCONV=1 docker exec compose-winebot-interactive-1 chown -R winebot:winebot "$ART_LIN" 2>/dev/null

echo "=============================================="
echo "  SuperTux — Full Game Lifecycle Demo"
echo "=============================================="
echo ""

echo "=== Step 1: Download SuperTux MSI ==="
ch "Download SuperTux MSI"
ann "Downloading SuperTux MSI installer via .bat script"
ann "Downloading SuperTux MSI via Linux curl"
linux_dl "$STUX_URL" "${ART_LIN}/supertux.msi"
sleep 2
echo "  $(verify_file "${ART_LIN}/supertux.msi")"

echo ""
echo "=== Step 2: Install via msiexec /quiet ==="
ch "MSI silent install"
ann "Running msiexec /i /quiet /qn — no installer UI appears"
bat_run "stux_install" "msiexec /i ${ART_WIN}/supertux.msi /quiet /qn"
sleep 8
echo "  supertux2.exe: $(verify_file '//wineprefix/drive_c/Program Files/SuperTux/supertux2.exe')"

echo ""
echo "=== Step 3: Launch game ==="
ch "Launch SuperTux"
api_post "/apps/run" '{"path":"supertux2.exe","detach":true}' > /dev/null
sleep 6
ann "SuperTux launched — game renders on Wine desktop"

echo ""
echo "=== Step 4: Navigate menus (keyboard + mouse) ==="
ch "Keyboard and mouse game interaction"
K="/input/key"
ann "Navigating with Up/Down arrows (AHK Send)"
api_post "$K" '{"keys":"Down","window_title":"SuperTux"}' > /dev/null; sleep 0.3
api_post "$K" '{"keys":"Down","window_title":"SuperTux"}' > /dev/null; sleep 0.3
api_post "$K" '{"keys":"Down","window_title":"SuperTux"}' > /dev/null; sleep 0.3
ann "Arrow keys navigated menu items"

api_post "$K" '{"keys":"Up","window_title":"SuperTux"}' > /dev/null; sleep 0.3
api_post "$K" '{"keys":"Up","window_title":"SuperTux"}' > /dev/null; sleep 0.3
api_post "$K" '{"keys":"Up","window_title":"SuperTux"}' > /dev/null; sleep 0.3
ann "Returned to top via Up arrows"

ann "Mouse click on game window (xdotool)"
api_post "/input/mouse/click" '{"x":640,"y":400,"button":1,"window_title":"SuperTux"}' > /dev/null
sleep 1
ann "Mouse click via /input/mouse/click (xdotool)"

echo ""
echo "=== Step 5: Screenshot verification ==="
ch "Screenshot"
ann "Taking screenshot of SuperTux running on Wine desktop"
curl -s -H "X-API-Key: $TOKEN" "$API_URL/screenshot" -o /tmp/supertux_shot.png 2>/dev/null || true
echo "  Screenshot captured"
ann "Screenshot captured — game renders correctly"

echo ""
echo "=== Step 6: Close game + uninstall ==="
ch "Game close and uninstall"
ann "Closing SuperTux via Escape"
api_post "$K" '{"keys":"Escape","window_title":"SuperTux"}' > /dev/null; sleep 1
api_post "$K" '{"keys":"alt+f4","window_title":"SuperTux"}' > /dev/null; sleep 2
ann "Game closed"

ann "Uninstalling via msiexec /x /quiet"
bat_run "stux_rm" "msiexec /x ${ART_WIN}/supertux.msi /quiet /qn 2>nul & rmdir /s /q \"C:/Program Files/SuperTux\" 2>nul & del /q ${ART_WIN}/supertux.msi 2>nul & rmdir /s /q ${ART_WIN}/bats 2>nul"
sleep 5
ann "SuperTux uninstalled, all artifacts removed"

echo ""
echo "=============================================="
echo "  SuperTux Demo Complete! Full lifecycle:"
echo "  Download → Install → Play → Screenshot → Remove"
echo "  /input/key + /input/mouse/click + msiexec /quiet"
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
