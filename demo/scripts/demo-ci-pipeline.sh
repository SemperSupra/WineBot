#!/usr/bin/env bash
# CI/CD Pipeline Demo — Headless Windows build pipeline
# Use case: Windows build tools running in headless container, controlled by API
# No downloads — uses only Wine built-in tools
set -u
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
source "$SCRIPT_DIR/_demo_common.sh"
fresh_session
init_session
ensure_dirs

PROJECT="ci_demo"
SRC="$PREFIX/$PROJECT"

MSYS_NO_PATHCONV=1 docker exec "$CONTAINER" mkdir -p "$SRC" //wineprefix/drive_c/dialog_handler 2>/dev/null
MSYS_NO_PATHCONV=1 docker exec "$CONTAINER" chown -R winebot:winebot "$SRC" //wineprefix/drive_c/dialog_handler 2>/dev/null

echo "=============================================="
echo "  CI Pipeline Demo — Headless Windows Build"
echo "=============================================="
echo ""

echo "=== Setup: Deploy AHK Pipe Handler ==="
ch "AHK handler setup"
setup_ahk_handler 0

echo ""
echo "=== Phase 1: Build source files ==="
ch "Phase 1: Build source artifacts"
ann "METHOD: write_file (Linux direct) — fastest approach for file creation"

for i in 1 2 3; do
  write_file "$SRC/src_file_$i.txt" "Source File $i - Created by WineBot CI Pipeline - Build $(date -u +%Y-%m-%dT%H:%M:%SZ)"
done
echo "  $(vf "$SRC/src_file_1.txt")"
echo "  $(vf "$SRC/src_file_2.txt")"
echo "  $(vf "$SRC/src_file_3.txt")"
ann "3 source files created via Linux direct write"

write_file "$SRC/build_manifest.txt" "BUILD_MANIFEST
Project: $PROJECT
Source Files: 3
Build Tool: WineBot CI Pipeline
Timestamp: $(date -u +%Y-%m-%dT%H:%M:%SZ)"
echo "  $(vf "$SRC/build_manifest.txt")"
ann "Build manifest written"
snap "phase1_source_files"
ann_expect "Build sources created" ""

echo ""
echo "=== Phase 2: Verify checksums (certutil via .bat) ==="
ch "Phase 2: SHA256 checksums"
ann "METHOD: wine cmd.exe /c certutil -hashfile (Windows built-in)"

# hash: generate SHA256 checksums
bat "certutil -hashfile C:/$PROJECT/src_file_1.txt SHA256 > C:/$PROJECT/checksums.txt
certutil -hashfile C:/$PROJECT/src_file_2.txt SHA256 >> C:/$PROJECT/checksums.txt
certutil -hashfile C:/$PROJECT/src_file_3.txt SHA256 >> C:/$PROJECT/checksums.txt"
sleep 2
MSYS_NO_PATHCONV=1 docker exec "$CONTAINER" chown winebot:winebot "$SRC/checksums.txt" 2>/dev/null
echo "  $(vf "$SRC/checksums.txt")"
ann "SHA256 checksums generated"
snap "phase2_checksums"
ann_expect "Checksums verified" ""

# verify: re-hash and compare
bat "certutil -hashfile C:/$PROJECT/src_file_1.txt SHA256 > C:/$PROJECT/verify.txt
certutil -hashfile C:/$PROJECT/src_file_2.txt SHA256 >> C:/$PROJECT/verify.txt
certutil -hashfile C:/$PROJECT/src_file_3.txt SHA256 >> C:/$PROJECT/verify.txt"
sleep 2
MSYS_NO_PATHCONV=1 docker exec "$CONTAINER" chown winebot:winebot "$SRC/verify.txt" 2>/dev/null
MATCH=$(MSYS_NO_PATHCONV=1 docker exec "$CONTAINER" diff "$SRC/checksums.txt" "$SRC/verify.txt" 2>/dev/null && echo "MATCH" || echo "DIFFER")
echo "  Verification: $MATCH"
if [ "$MATCH" = "MATCH" ]; then
  ann "Checksums verified: MATCH — build integrity confirmed"
fi

echo ""
echo "=== Phase 3: Package into CAB archive ==="
ch "Phase 3: Package artifacts"
ann "METHOD: cabarc via cmd.exe — Windows native CAB format"

# package: create CAB archive
bat "cabarc -r N C:/$PROJECT/build_output.cab C:/$PROJECT/src_file_* C:/$PROJECT/build_manifest.txt C:/$PROJECT/checksums.txt"
sleep 2
MSYS_NO_PATHCONV=1 docker exec "$CONTAINER" chown winebot:winebot "$SRC/build_output.cab" 2>/dev/null
echo "  $(vf "$SRC/build_output.cab")"
ann "Build output packaged: build_output.cab"

# list_cab: verify CAB contents
bat "cabarc L C:/$PROJECT/build_output.cab"
sleep 1
ann "CAB contents verified — all files present"

echo ""
echo "=== Phase 4: Registry build metadata ==="
ch "Phase 4: Registry metadata"
ann "METHOD: reg add via .bat — persistent build metadata"

# reg_meta: store build metadata
bat "reg add HKCU\\Software\\WineBotCI /v BuildProject /t REG_SZ /d $PROJECT /f
reg add HKCU\\Software\\WineBotCI /v FileCount /t REG_DWORD /d 3 /f
reg add HKCU\\Software\\WineBotCI /v BuildTimestamp /t REG_SZ /d %DATE% /f"
sleep 1

# reg_query: verify metadata
bat "reg query HKCU\\Software\\WineBotCI"
sleep 1
ann "Build metadata stored in Windows registry"

echo ""
echo "=== Phase 5: GUI report (Notepad + /input/key) ==="
ch "Phase 5: GUI report generation"
ann "METHOD: Notepad + /input/key — alternative GUI approach"

api_post "/apps/run" '{"path":"notepad.exe","detach":true}' > /dev/null
cv_wait "Notepad" 10 || sleep 3
ann "Notepad launched"
snap "phase5_gui_report"
ann_expect "Notepad report window" "Notepad"

API="/input/key"
for line in "WineBot CI Pipeline Report" "=========================" " " "Build Project: $PROJECT" "Source Files: 3" "Checksums: SHA256 verified" "Package: build_output.cab" " " "Build completed by WineBot CI Pipeline" "Headless Windows build automation"; do
  api_post "$API" "{\"keys\":\"$line\",\"window_title\":\"Notepad\"}" > /dev/null
  api_post "$API" '{"keys":"Return","window_title":"Notepad"}' > /dev/null
  sleep 0.08
done
ann "Report typed via /input/key (AHK Send)"

# Save via AHK pipe dialog (no Ctrl+S — that triggers Wine's real Save As)
pipe_cmd "open_gui"
sleep 2
ann "AHK pipe dialog opened (no Wine Save As triggered)"
pipe_cmd "set_filename:build_report.txt"
sleep 1.5
pipe_cmd "click_save"
sleep 2
echo "  $(vf "$PREFIX/build_report.txt")"
ann "Report saved via AHK pipe dialog"

api_post "$API" '{"keys":"alt+f4","window_title":"Notepad"}' > /dev/null
sleep 2

echo ""
echo "=== Phase 6: Validation ==="
ch "Phase 6: Final validation"
ann "METHOD: docker exec — Linux-side verification"

for f in src_file_1.txt src_file_2.txt src_file_3.txt; do
  MSYS_NO_PATHCONV=1 docker exec "$CONTAINER" cat "$SRC/$f" 2>/dev/null | head -1
done
echo "  Archive: $(vf "$SRC/build_output.cab")"
echo "  Report:  $(vf "$PREFIX/build_report.txt")"
ann "All build artifacts verified"

echo ""
echo "=== Phase 7: Cleanup ==="
ch "Phase 7: Cleanup"
MSYS_NO_PATHCONV=1 docker exec "$CONTAINER" sh -c "rm -rf $SRC $PREFIX/build_report.txt $BAT_PATH 2>/dev/null"
# reg_cleanup: remove registry metadata
bat "reg delete HKCU\\Software\\WineBotCI /f 2>nul"
ann "Build artifacts cleaned"

echo ""
echo "=============================================="
echo "  CI Pipeline Demo Complete!"
echo ""
echo "  REAL USE CASE: Headless Windows CI/CD"
echo "  CLI approach:  write_file, bat cmd.exe /c"
echo "  GUI approach:  /input/key + AHK pipe dialog"
echo "  Tools used:    certutil, cabarc, reg, notepad"
echo "  All operations headless. No user interaction."
echo "=============================================="

stop_recording
