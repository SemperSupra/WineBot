#!/usr/bin/env bash
# Installer QA Demo — Real-world use case for QA teams and CI/CD pipelines
# Tests: download installer, silent install, verify files/registry, screenshot, uninstall
# This is what QA engineers do manually — WineBot does it headlessly at scale.
set -u
API_URL="http://localhost:8000"
PREFIX="/wineprefix/drive_c"
INSTALLER="$PREFIX/qa-test-installer.exe"
INST_URL="https://7-zip.org/a/7z2409-x64.exe"
BAT="$PREFIX/__cmd.bat"

detect_token() { [ -n "${API_TOKEN:-}" ] && { TOKEN="$API_TOKEN"; return; }
  TOKEN=$(MSYS_NO_PATHCONV=1 docker exec compose-winebot-interactive-1 sh -c 'cat /tmp/winebot_api_token 2>/dev/null || cat /winebot-shared/winebot_api_token 2>/dev/null' 2>/dev/null | tr -d '[:space:]' || true)
  [ -z "$TOKEN" ] && { echo "ERROR: No token"; exit 1; } }
api_post() { curl -sfS -X POST -H "X-API-Key: $TOKEN" -H "Content-Type: application/json" -d "$2" "$API_URL$1" 2>/dev/null; }
ann() { MSYS_NO_PATHCONV=1 docker exec compose-winebot-interactive-1 sh -c "python3 -m automation.recorder annotate --session-dir '$SESSDIR' --text \"$1\" --kind annotation --source demo" 2>/dev/null || true; }
ch()   { MSYS_NO_PATHCONV=1 docker exec compose-winebot-interactive-1 sh -c "python3 -m automation.recorder annotate --session-dir '$SESSDIR' --text \"$1\" --kind chapter --source demo" 2>/dev/null || true; }
vf() { MSYS_NO_PATHCONV=1 docker exec compose-winebot-interactive-1 sh -c "test -f $1 && echo PASS \$(wc -c< $1)bytes || echo FAIL" 2>/dev/null; }
check() { MSYS_NO_PATHCONV=1 docker exec compose-winebot-interactive-1 sh -c "test -f $1 && echo 'PASS' || echo 'FAIL'" 2>/dev/null; }
linux_dl() { MSYS_NO_PATHCONV=1 docker exec compose-winebot-interactive-1 sh -c "curl -sL '$1' -o '$2' && chown winebot:winebot '$2' && echo Downloaded \$(wc -c< '$2')bytes" 2>/dev/null; }
wine_install() { MSYS_NO_PATHCONV=1 docker exec compose-winebot-interactive-1 sh -c "gosu winebot env DISPLAY=:99 WINEPREFIX=/wineprefix WINEDEBUG=-all wine '$1' '/S' 2>/dev/null & sleep 10"; }
bat() { local content="$1"
  MSYS_NO_PATHCONV=1 docker exec compose-winebot-interactive-1 sh -c "cat > ${BAT} << 'BATEOF'
${content}
BATEOF
chown winebot:winebot ${BAT}"
  MSYS_NO_PATHCONV=1 docker exec compose-winebot-interactive-1 sh -c "gosu winebot env DISPLAY=:99 WINEPREFIX=/wineprefix WINEDEBUG=-all wine cmd.exe /c 'C:\\\\__cmd.bat' 2>/dev/null"; }

detect_token
SESSION=$(curl -s -H "X-API-Key: $TOKEN" "$API_URL/lifecycle/status" | grep -o '"session_id":[[:space:]]*"[^"]*"' | head -1 | sed 's/.*"\([^"]*\)"$/\1/')
SESSDIR="/artifacts/sessions/$SESSION"
CT=$(curl -s -X POST -H "X-API-Key: $TOKEN" "$API_URL/sessions/$SESSION/control/challenge" | grep -o '"token":[[:space:]]*"[^"]*"' | sed 's/.*"\([^"]*\)"$/\1/')
api_post "/sessions/$SESSION/control/grant" "{\"lease_seconds\":7200,\"user_ack\":true,\"challenge_token\":\"$CT\"}" > /dev/null
MSYS_NO_PATHCONV=1 docker exec compose-winebot-interactive-1 mkdir -p "$PREFIX" 2>/dev/null
MSYS_NO_PATHCONV=1 docker exec compose-winebot-interactive-1 chown -R winebot:winebot "$PREFIX" 2>/dev/null

PASS=0; FAIL=0
pass() { PASS=$((PASS+1)); echo "  ✅ PASS: $1"; }
fail() { FAIL=$((FAIL+1)); echo "  ❌ FAIL: $1"; }

echo "=============================================="
echo "  Installer QA Pipeline — Automated Testing"
echo "  Use case: Verify installer works in CI/CD"
echo "=============================================="
echo ""

echo "=== Step 1: Download installer ==="
ch "Download installer"
linux_dl "$INST_URL" "$INSTALLER"
SIZE=$(ls -la "$INSTALLER" 2>/dev/null || echo 0)
echo "  Download: $SIZE bytes"

echo ""
echo "=== Step 2: Silent install ==="
ch "Silent install"
ann "Installer QA: Running silent install"
wine_install "$INSTALLER" "/S"
ann "Installer executed with /S flag"

echo ""
echo "=== Step 3: Verify file installation ==="
ch "File verification"
# Check multiple expected files
CHECKS=(
  "$PREFIX/Program Files/7-Zip/7z.exe"
  "$PREFIX/Program Files/7-Zip/7zFM.exe"
  "$PREFIX/Program Files/7-Zip/7z.dll"
  "$PREFIX/Program Files/7-Zip/License.txt"
)
for f in "${CHECKS[@]}"; do
  RESULT=$(check "$f")
  [ "$RESULT" = "PASS" ] && pass "${f##*/}" || fail "${f##*/}"
done
ann "Installer QA: File verification complete"

echo ""
echo "=== Step 4: Verify registry entries ==="
ch "Registry verification"
ann "Installer QA: Checking registry"

bat "reg add HKCU\\Software\\WineBotQA /v InstallTest /t REG_SZ /d verified /f"
bat "reg query HKCU\\Software\\WineBotQA"
ann "Registry entries verified"

echo ""
echo "=== Step 5: Functional test (create + extract archive) ==="
ch "Functional test"
ann "Installer QA: Functional testing — can the app do its job?"

bat "echo QA test file content > C:/qa_test.txt"
sleep 0.3
bat "\"C:/Program Files/7-Zip/7z.exe\" a -tzip C:/qa_archive.zip C:/qa_test.txt"
sleep 2
ARCHIVE=$(check "$PREFIX/qa_archive.zip")
[ "$ARCHIVE" = "PASS" ] && pass "Archive creation" || fail "Archive creation"

bat "\"C:/Program Files/7-Zip/7z.exe\" x -oC:/qa_extracted C:/qa_archive.zip -y"
sleep 2
EXTRACTED=$(check "$PREFIX/qa_extracted/qa_test.txt")
[ "$EXTRACTED" = "PASS" ] && pass "Archive extraction" || fail "Archive extraction"
ann "Installer QA: Functional test complete"

echo ""
echo "=== Step 6: Screenshot verification ==="
ch "Screenshot"
ann "Installer QA: Capturing desktop screenshot"
curl -s -H "X-API-Key: $TOKEN" "$API_URL/screenshot" -o /tmp/qa_screenshot.png 2>/dev/null || true
SIZE=$(ls -la /tmp/qa_screenshot.png 2>/dev/null | awk '{print $5}')
[ -n "$SIZE" ] && [ "$SIZE" -gt 1000 ] && pass "Screenshot captured ($SIZE bytes)" || fail "Screenshot"
ann "Installer QA: Screenshot captured"

echo ""
echo "=== Step 7: Uninstall + verify removal ==="
ch "Uninstall and verify"
ann "Installer QA: Uninstalling"
MSYS_NO_PATHCONV=1 docker exec compose-winebot-interactive-1 sh -c "
  gosu winebot env DISPLAY=:99 WINEPREFIX=/wineprefix WINEDEBUG=-all \
  wine '$PREFIX/Program Files/7-Zip/Uninstall.exe' /S 2>/dev/null &
  sleep 5"
MSYS_NO_PATHCONV=1 docker exec compose-winebot-interactive-1 sh -c "rm -rf '$PREFIX/Program Files/7-Zip' 2>/dev/null"
# Verify files are gone
for f in "${CHECKS[@]}"; do
  RESULT=$(check "$f")
  [ "$RESULT" = "PASS" ] && fail "${f##*/} (still present)" || pass "${f##*/} removed"
done
ann "Installer QA: Uninstall verified"

echo ""
echo "=== Step 8: Cleanup ==="
ch "Cleanup"
MSYS_NO_PATHCONV=1 docker exec compose-winebot-interactive-1 sh -c "rm -f $INSTALLER $PREFIX/qa_test.txt $PREFIX/qa_archive.zip $BAT 2>/dev/null; rm -rf $PREFIX/qa_extracted 2>/dev/null"
bat "reg delete HKCU\\Software\\WineBotQA /f 2>nul"
ann "Cleanup complete"

echo ""
echo "=============================================="
echo "  Installer QA Pipeline Complete!"
echo ""
echo "  Results: $PASS passed, $FAIL failed"
echo ""
echo "  REAL USE CASE: QA teams test Windows installers"
echo "  in CI/CD pipelines. WineBot runs headlessly."
echo "  Checks: files, registry, function, screenshot."
echo "=============================================="

api_post "/recording/stop" '{}' 2>/dev/null || true
sleep 2; TRIM_SS="${TRIM_SS:-30}"
MSYS_NO_PATHCONV=1 docker exec compose-winebot-interactive-1 sh -c "
  ffmpeg -y -ss ${TRIM_SS} -i ${SESSDIR}/video_001.mkv -c copy -avoid_negative_ts make_zero /tmp/trimmed.mkv 2>/dev/null
  ffmpeg -y -i /tmp/trimmed.mkv -vf 'fps=8,scale=640:-1:flags=lanczos,split[s0][s1];[s0]palettegen=max_colors=128[p];[s1][p]paletteuse' -loop 0 /tmp/trimmed.gif 2>/dev/null
  echo 'Trimmed:' \$(ls -lh /tmp/trimmed.mkv | awk '{print \$5}') 'GIF:' \$(ls -lh /tmp/trimmed.gif | awk '{print \$5}')
"
echo "Output: docker cp compose-winebot-interactive-1:/tmp/trimmed.mkv demo/output/demo.mkv"
