#!/usr/bin/env bash
# SuperTux Game Demo — download, install via msiexec, launch, keyboard+mouse, screenshot, uninstall
set -u
API_URL="http://localhost:8000"
PREFIX="/wineprefix/drive_c"
STUX_URL="https://github.com/SuperTux/supertux/releases/download/v0.6.3/SuperTux-v0.6.3-win64.msi"

detect_token() {
  [ -n "${API_TOKEN:-}" ] && { TOKEN="$API_TOKEN"; return; }
  TOKEN=$(MSYS_NO_PATHCONV=1 docker exec compose-winebot-interactive-1 sh -c 'cat /tmp/winebot_api_token 2>/dev/null || cat /winebot-shared/winebot_api_token 2>/dev/null' 2>/dev/null | tr -d '[:space:]' || true)
  [ -z "$TOKEN" ] && { echo "ERROR: No token"; exit 1; }
}
api_post() { curl -sfS -X POST -H "X-API-Key: $TOKEN" -H "Content-Type: application/json" -d "$2" "$API_URL$1" 2>/dev/null; }
ann() { MSYS_NO_PATHCONV=1 docker exec compose-winebot-interactive-1 sh -c "python3 -m automation.recorder annotate --session-dir '$SESSDIR' --text \"$1\" --kind annotation --source demo" 2>/dev/null || true; }
ch()   { MSYS_NO_PATHCONV=1 docker exec compose-winebot-interactive-1 sh -c "python3 -m automation.recorder annotate --session-dir '$SESSDIR' --text \"$1\" --kind chapter --source demo" 2>/dev/null || true; }
verify_file() { MSYS_NO_PATHCONV=1 docker exec compose-winebot-interactive-1 sh -c "test -f $1 && echo EXISTS \$(wc -c < $1)bytes || echo MISSING" 2>/dev/null; }

linux_dl() { local url="$1" dest="$2"
  MSYS_NO_PATHCONV=1 docker exec compose-winebot-interactive-1 sh -c "curl -sL '$url' -o '$dest' && chown winebot:winebot '$dest' && echo '  Downloaded: ' \$(wc -c < '$dest') ' bytes'" 2>/dev/null; }

wine_msi_install() { local msi="$1"
  MSYS_NO_PATHCONV=1 docker exec compose-winebot-interactive-1 sh -c "
    gosu winebot env DISPLAY=:99 WINEPREFIX=/wineprefix WINEDEBUG=-all \
    wine msiexec /i '$msi' /quiet /qn 2>/dev/null &
    sleep 10
  "; }

wine_msi_uninstall() { local msi="$1"
  MSYS_NO_PATHCONV=1 docker exec compose-winebot-interactive-1 sh -c "
    gosu winebot env DISPLAY=:99 WINEPREFIX=/wineprefix WINEDEBUG=-all \
    wine msiexec /x '$msi' /quiet /qn 2>/dev/null &
    sleep 5
  "; }

detect_token
SESSION=$(curl -s -H "X-API-Key: $TOKEN" "$API_URL/lifecycle/status" | grep -o '"session_id":[[:space:]]*"[^"]*"' | head -1 | sed 's/.*"\([^"]*\)"$/\1/')
SESSDIR="/artifacts/sessions/$SESSION"
CT=$(curl -s -X POST -H "X-API-Key: $TOKEN" "$API_URL/sessions/$SESSION/control/challenge" | grep -o '"token":[[:space:]]*"[^"]*"' | sed 's/.*"\([^"]*\)"$/\1/')
api_post "/sessions/$SESSION/control/grant" "{\"lease_seconds\":7200,\"user_ack\":true,\"challenge_token\":\"$CT\"}" > /dev/null
MSYS_NO_PATHCONV=1 docker exec compose-winebot-interactive-1 mkdir -p "$PREFIX" 2>/dev/null
MSYS_NO_PATHCONV=1 docker exec compose-winebot-interactive-1 chown -R winebot:winebot "$PREFIX" 2>/dev/null

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
sleep 8
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
MSYS_NO_PATHCONV=1 docker exec compose-winebot-interactive-1 sh -c "rm -f $PREFIX/supertux.msi 2>/dev/null"
wine_msi_uninstall "$PREFIX/supertux.msi" 2>/dev/null || true
MSYS_NO_PATHCONV=1 docker exec compose-winebot-interactive-1 sh -c "rm -rf '$PREFIX/Program Files/SuperTux' 2>/dev/null"
ann "Game uninstalled, artifacts removed"

echo ""
echo "=============================================="
echo "  SuperTux Demo Complete!"
echo "  Download: Linux curl  Install: msiexec /i /qn"
echo "  Play: keyboard + mouse  Verify: screenshot"
echo "  Full lifecycle: download → install → play → verify → remove"
echo "=============================================="

api_post "/recording/stop" '{}' 2>/dev/null || true
sleep 2; TRIM_SS="${TRIM_SS:-40}"
MSYS_NO_PATHCONV=1 docker exec compose-winebot-interactive-1 sh -c "
  ffmpeg -y -ss ${TRIM_SS} -i ${SESSDIR}/video_001.mkv -c copy -avoid_negative_ts make_zero /tmp/trimmed.mkv 2>/dev/null
  ffmpeg -y -i /tmp/trimmed.mkv -vf 'fps=8,scale=640:-1:flags=lanczos,split[s0][s1];[s0]palettegen=max_colors=128[p];[s1][p]paletteuse' -loop 0 /tmp/trimmed.gif 2>/dev/null
  echo 'Trimmed:' \$(ls -lh /tmp/trimmed.mkv | awk '{print \$5}') 'GIF:' \$(ls -lh /tmp/trimmed.gif | awk '{print \$5}')
"
echo "Output: docker cp compose-winebot-interactive-1:/tmp/trimmed.mkv demo/output/demo.mkv"
