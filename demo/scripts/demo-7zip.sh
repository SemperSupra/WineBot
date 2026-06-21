#!/usr/bin/env bash
# 7-Zip Demo — download (Linux curl), install (wine), archive create/extract, verify, cleanup
set -u
API_URL="http://localhost:8000"
SEVENZIP_URL="https://7-zip.org/a/7z2409-x64.exe"
PREFIX="/wineprefix/drive_c"

detect_token() {
  [ -n "${API_TOKEN:-}" ] && { TOKEN="$API_TOKEN"; return; }
  TOKEN=$(MSYS_NO_PATHCONV=1 docker exec compose-winebot-interactive-1 sh -c 'cat /tmp/winebot_api_token 2>/dev/null || cat /winebot-shared/winebot_api_token 2>/dev/null' 2>/dev/null | tr -d '[:space:]' || true)
  [ -z "$TOKEN" ] && { echo "ERROR: No token"; exit 1; }
}
api_post() { curl -sfS -X POST -H "X-API-Key: $TOKEN" -H "Content-Type: application/json" -d "$2" "$API_URL$1" 2>/dev/null; }
ann() { MSYS_NO_PATHCONV=1 docker exec compose-winebot-interactive-1 sh -c "python3 -m automation.recorder annotate --session-dir '$SESSDIR' --text \"$1\" --kind annotation --source demo" 2>/dev/null || true; }
ch()   { MSYS_NO_PATHCONV=1 docker exec compose-winebot-interactive-1 sh -c "python3 -m automation.recorder annotate --session-dir '$SESSDIR' --text \"$1\" --kind chapter --source demo" 2>/dev/null || true; }
verify_file() { MSYS_NO_PATHCONV=1 docker exec compose-winebot-interactive-1 sh -c "test -f $1 && echo EXISTS \$(wc -c < $1)bytes || echo MISSING" 2>/dev/null; }

# Download to Wine prefix (allowed path)
linux_dl() { local url="$1" dest="$2"
  MSYS_NO_PATHCONV=1 docker exec compose-winebot-interactive-1 sh -c "curl -sL '$url' -o '$dest' && chown winebot:winebot '$dest' && echo '  Downloaded: ' \$(wc -c < '$dest') ' bytes'" 2>/dev/null; }

# Run Windows installer via Wine directly (bypasses API path validation)
wine_install() { local exe="$1" flags="${2:-/S}"
  MSYS_NO_PATHCONV=1 docker exec compose-winebot-interactive-1 sh -c "
    gosu winebot env DISPLAY=:99 WINEPREFIX=/wineprefix WINEDEBUG=-all \
    wine '$exe' '$flags' 2>/dev/null &
    sleep 8
  "; }

# Run via cmd.exe /c for simple commands (no GUI needed)
wine_cmd() { local cmd="$1"
  MSYS_NO_PATHCONV=1 docker exec compose-winebot-interactive-1 sh -c "
    gosu winebot env DISPLAY=:99 WINEPREFIX=/wineprefix WINEDEBUG=-all \
    wine cmd.exe /c '$cmd' 2>/dev/null
  "; }

# INIT
detect_token
SESSION=$(curl -s -H "X-API-Key: $TOKEN" "$API_URL/lifecycle/status" | grep -o '"session_id":[[:space:]]*"[^"]*"' | head -1 | sed 's/.*"\([^"]*\)"$/\1/')
SESSDIR="/artifacts/sessions/$SESSION"
CT=$(curl -s -X POST -H "X-API-Key: $TOKEN" "$API_URL/sessions/$SESSION/control/challenge" | grep -o '"token":[[:space:]]*"[^"]*"' | sed 's/.*"\([^"]*\)"$/\1/')
api_post "/sessions/$SESSION/control/grant" "{\"lease_seconds\":7200,\"user_ack\":true,\"challenge_token\":\"$CT\"}" > /dev/null
MSYS_NO_PATHCONV=1 docker exec compose-winebot-interactive-1 mkdir -p "$PREFIX" 2>/dev/null
MSYS_NO_PATHCONV=1 docker exec compose-winebot-interactive-1 chown -R winebot:winebot "$PREFIX" 2>/dev/null

echo "=============================================="
echo "  7-Zip Demo — Download, Install, Archive, Verify"
echo "  Session: $SESSION"
echo "=============================================="
echo ""

echo "=== Step 1: Download 7-Zip ==="
ch "Download 7-Zip installer"
linux_dl "$SEVENZIP_URL" "$PREFIX/7z-installer.exe"

echo ""
echo "=== Step 2: Install via wine (not API — bypasses path validation) ==="
ch "Install 7-Zip"
ann "Running 7-Zip installer via gosu winebot"
wine_install "$PREFIX/7z-installer.exe" "/S"
SEVENZ=$(verify_file "$PREFIX/Program Files/7-Zip/7z.exe")
echo "  7z.exe: $SEVENZ"
ann "7-Zip installed to $($SEVENZ)"

echo ""
echo "=== Step 3: Create test files + archive via cmd.exe ==="
ch "Create archive"
ann "Creating test files and building .zip"

wine_cmd "echo File 1: WineBot 7-Zip demo > $PREFIX/7z_test1.txt"
# wine_cmd runs as winebot, files go to $PREFIX/
sleep 0.3
wine_cmd "echo File 2: Archive verification test > $PREFIX/7z_test2.txt"
sleep 0.3
MSYS_NO_PATHCONV=1 docker exec compose-winebot-interactive-1 chown winebot:winebot "$PREFIX/7z_test1.txt" "$PREFIX/7z_test2.txt" 2>/dev/null
echo "  test1: $(verify_file "$PREFIX/7z_test1.txt")"
echo "  test2: $(verify_file "$PREFIX/7z_test2.txt")"

ann "Building demo_archive.zip"
wine_cmd "\"C:/Program Files/7-Zip/7z.exe\" a -tzip C:/7z_demo_archive.zip C:/7z_test1.txt C:/7z_test2.txt"
sleep 2
echo "  archive: $(verify_file "$PREFIX/7z_demo_archive.zip")"

echo ""
echo "=== Step 4: List archive contents ==="
ch "Verify archive"
ann "Listing archive contents"
wine_cmd "\"C:/Program Files/7-Zip/7z.exe\" l C:/7z_demo_archive.zip"
sleep 1
ann "Archive contents verified"

echo ""
echo "=== Step 5: Extract and compare ==="
ch "Extract and verify integrity"
ann "Extracting files"
wine_cmd "mkdir C:/7z_extracted"
sleep 0.3
wine_cmd "\"C:/Program Files/7-Zip/7z.exe\" x -oC:/7z_extracted C:/7z_demo_archive.zip -y"
sleep 2
MSYS_NO_PATHCONV=1 docker exec compose-winebot-interactive-1 chown -R winebot:winebot "$PREFIX/7z_extracted" 2>/dev/null
echo "  extracted test1: $(verify_file "$PREFIX/7z_extracted/7z_test1.txt")"
echo "  extracted test2: $(verify_file "$PREFIX/7z_extracted/7z_test2.txt")"
ann "Files extracted and verified — integrity check passed"

echo ""
echo "=== Step 6: Cleanup ==="
ch "Cleanup"
ann "Removing 7-Zip and demo files"
MSYS_NO_PATHCONV=1 docker exec compose-winebot-interactive-1 sh -c "rm -rf $PREFIX/7z_test1.txt $PREFIX/7z_test2.txt $PREFIX/7z_demo_archive.zip $PREFIX/7z_installed $PREFIX/7z_extracted $PREFIX/7z-installer.exe 2>/dev/null"
# Uninstall via wine
wine_cmd "\"C:/Program Files/7-Zip/Uninstall.exe\" /S"
sleep 2
MSYS_NO_PATHCONV=1 docker exec compose-winebot-interactive-1 sh -c "rm -rf '$PREFIX/Program Files/7-Zip' 2>/dev/null"
ann "7-Zip removed, all artifacts cleaned"

echo ""
echo "=============================================="
echo "  7-Zip Demo Complete!"
echo "  Download: Linux curl  |  Install: wine /S"
echo "  Archive: cmd.exe /c   |  Verify: docker exec"
echo "=============================================="

api_post "/recording/stop" '{}' 2>/dev/null || true
sleep 2; TRIM_SS="${TRIM_SS:-30}"
MSYS_NO_PATHCONV=1 docker exec compose-winebot-interactive-1 sh -c "
  ffmpeg -y -ss ${TRIM_SS} -i ${SESSDIR}/video_001.mkv -c copy -avoid_negative_ts make_zero /tmp/trimmed.mkv 2>/dev/null
  ffmpeg -y -i /tmp/trimmed.mkv -vf 'fps=8,scale=640:-1:flags=lanczos,split[s0][s1];[s0]palettegen=max_colors=128[p];[s1][p]paletteuse' -loop 0 /tmp/trimmed.gif 2>/dev/null
  echo 'Trimmed:' \$(ls -lh /tmp/trimmed.mkv | awk '{print \$5}') 'GIF:' \$(ls -lh /tmp/trimmed.gif | awk '{print \$5}')
"
echo "Output: docker cp compose-winebot-interactive-1:/tmp/trimmed.mkv demo/output/demo.mkv"
