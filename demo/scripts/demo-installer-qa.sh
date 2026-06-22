#!/usr/bin/env bash
# Installer QA Demo — Real-world use case for QA teams and CI/CD pipelines
# Tests: download installer, silent install, verify files/registry, screenshot, uninstall
# This is what QA engineers do manually — WineBot does it headlessly at scale.
set -u
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
source "$SCRIPT_DIR/_demo_common.sh"
fresh_session
init_session
ensure_dirs

INSTALLER="$PREFIX/qa-test-installer.exe"
INST_URL="https://7-zip.org/a/7z2409-x64.exe"

echo "=============================================="
echo "  Installer QA Pipeline — Automated Testing"
echo "  Use case: Verify installer works in CI/CD"
echo "=============================================="
echo ""

echo "=== Step 1: Download installer ==="
ch "Download installer"
linux_dl "$INST_URL" "$INSTALLER"
# Fixed: use verify_file instead of host-side ls -la on container path
echo "  Download: $(verify_file "$INSTALLER")"

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
  if [ "$RESULT" = "PASS" ]; then
    pass "${f##*/}"
  else
    fail "${f##*/}"
  fi
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
if [ "$ARCHIVE" = "PASS" ]; then
  pass "Archive creation"
else
  fail "Archive creation"
fi

bat "\"C:/Program Files/7-Zip/7z.exe\" x -oC:/qa_extracted C:/qa_archive.zip -y"
sleep 2
EXTRACTED=$(check "$PREFIX/qa_extracted/qa_test.txt")
if [ "$EXTRACTED" = "PASS" ]; then
  pass "Archive extraction"
else
  fail "Archive extraction"
fi
ann "Installer QA: Functional test complete"

echo ""
echo "=== Step 6: Screenshot verification ==="
ch "Screenshot"
ann "Installer QA: Capturing desktop screenshot"
curl -s -H "X-API-Key: $TOKEN" "$API_URL/screenshot" -o /tmp/qa_screenshot.png 2>/dev/null || true
SIZE=$(ls -la /tmp/qa_screenshot.png 2>/dev/null | awk '{print $5}')
if [ -n "$SIZE" ] && [ "$SIZE" -gt 1000 ]; then
  pass "Screenshot captured ($SIZE bytes)"
else
  fail "Screenshot"
fi
ann "Installer QA: Screenshot captured"

echo ""
echo "=== Step 7: Uninstall + verify removal ==="
ch "Uninstall and verify"
ann "Installer QA: Uninstalling"
MSYS_NO_PATHCONV=1 docker exec "$CONTAINER" sh -c "
  gosu winebot env DISPLAY=:99 WINEPREFIX=/wineprefix WINEDEBUG=-all \
  wine '$PREFIX/Program Files/7-Zip/Uninstall.exe' /S 2>/dev/null &
  sleep 5"
MSYS_NO_PATHCONV=1 docker exec "$CONTAINER" sh -c "rm -rf '$PREFIX/Program Files/7-Zip' 2>/dev/null"
# Verify files are gone
for f in "${CHECKS[@]}"; do
  RESULT=$(check "$f")
  if [ "$RESULT" = "PASS" ]; then
    fail "${f##*/} (still present)"
  else
    pass "${f##*/} removed"
  fi
done
ann "Installer QA: Uninstall verified"

echo ""
echo "=== Step 8: Cleanup ==="
ch "Cleanup"
MSYS_NO_PATHCONV=1 docker exec "$CONTAINER" sh -c "rm -f $INSTALLER $PREFIX/qa_test.txt $PREFIX/qa_archive.zip $BAT_PATH 2>/dev/null; rm -rf $PREFIX/qa_extracted 2>/dev/null"
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

stop_recording
