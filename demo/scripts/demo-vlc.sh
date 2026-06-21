#!/usr/bin/env bash
# VLC Demo — download (Linux curl), install (wine /S), keyboard menu navigation
set -u
API_URL="http://localhost:8000"
PREFIX="/wineprefix/drive_c"
VLC_URL="https://get.videolan.org/vlc/3.0.21/win64/vlc-3.0.21-win64.exe"

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

wine_install() { local exe="$1" flags="${2:-/S}"
  MSYS_NO_PATHCONV=1 docker exec compose-winebot-interactive-1 sh -c "
    gosu winebot env DISPLAY=:99 WINEPREFIX=/wineprefix WINEDEBUG=-all \
    wine '$exe' '$flags' 2>/dev/null &
    sleep 8
  "; }

detect_token
SESSION=$(curl -s -H "X-API-Key: $TOKEN" "$API_URL/lifecycle/status" | grep -o '"session_id":[[:space:]]*"[^"]*"' | head -1 | sed 's/.*"\([^"]*\)"$/\1/')
SESSDIR="/artifacts/sessions/$SESSION"
CT=$(curl -s -X POST -H "X-API-Key: $TOKEN" "$API_URL/sessions/$SESSION/control/challenge" | grep -o '"token":[[:space:]]*"[^"]*"' | sed 's/.*"\([^"]*\)"$/\1/')
api_post "/sessions/$SESSION/control/grant" "{\"lease_seconds\":7200,\"user_ack\":true,\"challenge_token\":\"$CT\"}" > /dev/null
MSYS_NO_PATHCONV=1 docker exec compose-winebot-interactive-1 mkdir -p "$PREFIX" 2>/dev/null
MSYS_NO_PATHCONV=1 docker exec compose-winebot-interactive-1 chown -R winebot:winebot "$PREFIX" 2>/dev/null

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
sleep 6
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
MSYS_NO_PATHCONV=1 docker exec compose-winebot-interactive-1 sh -c "rm -f $PREFIX/vlc-installer.exe 2>/dev/null"
MSYS_NO_PATHCONV=1 docker exec compose-winebot-interactive-1 sh -c "
  gosu winebot env DISPLAY=:99 WINEPREFIX=/wineprefix WINEDEBUG=-all \
  wine '$PREFIX/Program Files/VideoLAN/VLC/Uninstall.exe' /S 2>/dev/null &
  sleep 5"
MSYS_NO_PATHCONV=1 docker exec compose-winebot-interactive-1 sh -c "rm -rf '$PREFIX/Program Files/VideoLAN' 2>/dev/null"
ann "VLC uninstalled"

echo ""
echo "=============================================="
echo "  VLC Demo Complete!"
echo "  /input/key chords (Alt+M/H), arrows, Escape"
echo "=============================================="

api_post "/recording/stop" '{}' 2>/dev/null || true
sleep 2; TRIM_SS="${TRIM_SS:-40}"
MSYS_NO_PATHCONV=1 docker exec compose-winebot-interactive-1 sh -c "
  ffmpeg -y -ss ${TRIM_SS} -i ${SESSDIR}/video_001.mkv -c copy -avoid_negative_ts make_zero /tmp/trimmed.mkv 2>/dev/null
  ffmpeg -y -i /tmp/trimmed.mkv -vf 'fps=8,scale=640:-1:flags=lanczos,split[s0][s1];[s0]palettegen=max_colors=128[p];[s1][p]paletteuse' -loop 0 /tmp/trimmed.gif 2>/dev/null
  echo 'Trimmed:' \$(ls -lh /tmp/trimmed.mkv | awk '{print \$5}') 'GIF:' \$(ls -lh /tmp/trimmed.gif | awk '{print \$5}')
"
echo "Output: docker cp compose-winebot-interactive-1:/tmp/trimmed.mkv demo/output/demo.mkv"
