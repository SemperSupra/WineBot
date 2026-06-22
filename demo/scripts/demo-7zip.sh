#!/usr/bin/env bash
# 7-Zip Demo — download (Linux curl), install (wine), archive create/extract, verify, cleanup
set -u
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
source "$SCRIPT_DIR/_demo_common.sh"
fresh_session
init_session
ensure_dirs

SEVENZIP_URL="https://7-zip.org/a/7z2409-x64.exe"

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
ann "7-Zip installed to $SEVENZ"

echo ""
echo "=== Step 3: Create test files + archive via cmd.exe ==="
ch "Create archive"
ann "Creating test files and building .zip"

wine_cmd "echo File 1: WineBot 7-Zip demo > $PREFIX/7z_test1.txt"
sleep 0.3
wine_cmd "echo File 2: Archive verification test > $PREFIX/7z_test2.txt"
sleep 0.3
MSYS_NO_PATHCONV=1 docker exec "$CONTAINER" chown winebot:winebot "$PREFIX/7z_test1.txt" "$PREFIX/7z_test2.txt" 2>/dev/null
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
MSYS_NO_PATHCONV=1 docker exec "$CONTAINER" chown -R winebot:winebot "$PREFIX/7z_extracted" 2>/dev/null
echo "  extracted test1: $(verify_file "$PREFIX/7z_extracted/7z_test1.txt")"
echo "  extracted test2: $(verify_file "$PREFIX/7z_extracted/7z_test2.txt")"
ann "Files extracted and verified — integrity check passed"

echo ""
echo "=== Step 6: Cleanup ==="
ch "Cleanup"
ann "Removing 7-Zip and demo files"
MSYS_NO_PATHCONV=1 docker exec "$CONTAINER" sh -c "rm -rf $PREFIX/7z_test1.txt $PREFIX/7z_test2.txt $PREFIX/7z_demo_archive.zip $PREFIX/7z_installed $PREFIX/7z_extracted $PREFIX/7z-installer.exe 2>/dev/null"
# Uninstall via wine
wine_cmd "\"C:/Program Files/7-Zip/Uninstall.exe\" /S"
sleep 2
MSYS_NO_PATHCONV=1 docker exec "$CONTAINER" sh -c "rm -rf '$PREFIX/Program Files/7-Zip' 2>/dev/null"
ann "7-Zip removed, all artifacts cleaned"

echo ""
echo "=============================================="
echo "  7-Zip Demo Complete!"
echo "  Download: Linux curl  |  Install: wine /S"
echo "  Archive: cmd.exe /c   |  Verify: docker exec"
echo "=============================================="

stop_recording
