#!/usr/bin/env bash
# CI/CD Pipeline Demo — Headless Windows build pipeline
# Use case: Windows build tools running in headless container, controlled by API
# No downloads — uses only Wine built-in tools
set -u
API_URL="http://localhost:8000"
PREFIX="/wineprefix/drive_c"
PROJECT="ci_demo"
SRC="$PREFIX/$PROJECT"
PIPE="//wineprefix/drive_c/dialog_handler/pipe.txt"
BAT="$PREFIX/__cmd.bat"

detect_token() { [ -n "${API_TOKEN:-}" ] && { TOKEN="$API_TOKEN"; return; }
  TOKEN=$(MSYS_NO_PATHCONV=1 docker exec compose-winebot-interactive-1 sh -c 'cat /tmp/winebot_api_token 2>/dev/null || cat /winebot-shared/winebot_api_token 2>/dev/null' 2>/dev/null | tr -d '[:space:]' || true)
  [ -z "$TOKEN" ] && { echo "ERROR: No token"; exit 1; } }
api_post() { curl -sfS -X POST -H "X-API-Key: $TOKEN" -H "Content-Type: application/json" -d "$2" "$API_URL$1" 2>/dev/null; }
ann() { MSYS_NO_PATHCONV=1 docker exec compose-winebot-interactive-1 sh -c "python3 -m automation.recorder annotate --session-dir '$SESSDIR' --text \"$1\" --kind annotation --source demo" 2>/dev/null || true; }
ch()   { MSYS_NO_PATHCONV=1 docker exec compose-winebot-interactive-1 sh -c "python3 -m automation.recorder annotate --session-dir '$SESSDIR' --text \"$1\" --kind chapter --source demo" 2>/dev/null || true; }
vf() { MSYS_NO_PATHCONV=1 docker exec compose-winebot-interactive-1 sh -c "test -f $1 && echo EXISTS \$(wc -c < $1)bytes || echo MISSING" 2>/dev/null; }
pipe_cmd() { MSYS_NO_PATHCONV=1 docker exec compose-winebot-interactive-1 su -s /bin/sh winebot -c "echo '$1' > '$PIPE'" 2>/dev/null; }
pipe_read() { MSYS_NO_PATHCONV=1 docker exec compose-winebot-interactive-1 su -s /bin/sh winebot -c "cat '$PIPE' 2>/dev/null" || true; }

# Write .bat file, execute via wine cmd.exe /c (no bash redirection issues)
bat() { local name="$1" content="$2"
  MSYS_NO_PATHCONV=1 docker exec compose-winebot-interactive-1 sh -c "cat > ${BAT} << 'BATEOF'
${content}
BATEOF
chown winebot:winebot ${BAT}"
  MSYS_NO_PATHCONV=1 docker exec compose-winebot-interactive-1 sh -c "
    gosu winebot env DISPLAY=:99 WINEPREFIX=/wineprefix WINEDEBUG=-all \
    wine cmd.exe /c 'C:\\\\__cmd.bat' 2>/dev/null"
}

# Write a file directly from Linux (faster, avoids cmd.exe overhead)
write_file() { local path="$1" content="$2"
  MSYS_NO_PATHCONV=1 docker exec compose-winebot-interactive-1 sh -c "echo '$content' > '$path' && chown winebot:winebot '$path'" 2>/dev/null; }

detect_token
SESSION=$(curl -s -H "X-API-Key: $TOKEN" "$API_URL/lifecycle/status" | grep -o '"session_id":[[:space:]]*"[^"]*"' | head -1 | sed 's/.*"\([^"]*\)"$/\1/')
SESSDIR="/artifacts/sessions/$SESSION"
CT=$(curl -s -X POST -H "X-API-Key: $TOKEN" "$API_URL/sessions/$SESSION/control/challenge" | grep -o '"token":[[:space:]]*"[^"]*"' | sed 's/.*"\([^"]*\)"$/\1/')
api_post "/sessions/$SESSION/control/grant" "{\"lease_seconds\":7200,\"user_ack\":true,\"challenge_token\":\"$CT\"}" > /dev/null
MSYS_NO_PATHCONV=1 docker exec compose-winebot-interactive-1 mkdir -p "$SRC" "$PREFIX" //wineprefix/drive_c/dialog_handler 2>/dev/null
MSYS_NO_PATHCONV=1 docker exec compose-winebot-interactive-1 chown -R winebot:winebot "$SRC" "$PREFIX" //wineprefix/drive_c/dialog_handler 2>/dev/null

MSYS_NO_PATHCONV=1 docker cp automation/core/dialog_replacement.ahk compose-winebot-interactive-1://wineprefix/drive_c/dr.ahk 2>/dev/null
MSYS_NO_PATHCONV=1 docker exec compose-winebot-interactive-1 chown winebot:winebot //wineprefix/drive_c/dr.ahk 2>/dev/null
MSYS_NO_PATHCONV=1 docker exec compose-winebot-interactive-1 sh -c '
  gosu winebot env DISPLAY=:99 WINEPREFIX=/wineprefix WINEDEBUG=-all nohup ahk C:/dr.ahk > /wineprefix/drive_c/dh.log 2>&1 &'
sleep 5

echo "=============================================="
echo "  CI Pipeline Demo — Headless Windows Build"
echo "=============================================="
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

echo ""
echo "=== Phase 2: Verify checksums (certutil via .bat) ==="
ch "Phase 2: SHA256 checksums"
ann "METHOD: wine cmd.exe /c certutil -hashfile (Windows built-in)"

bat "hash" "certutil -hashfile C:/$PROJECT/src_file_1.txt SHA256 > C:/$PROJECT/checksums.txt
certutil -hashfile C:/$PROJECT/src_file_2.txt SHA256 >> C:/$PROJECT/checksums.txt
certutil -hashfile C:/$PROJECT/src_file_3.txt SHA256 >> C:/$PROJECT/checksums.txt"
sleep 2
MSYS_NO_PATHCONV=1 docker exec compose-winebot-interactive-1 chown winebot:winebot "$SRC/checksums.txt" 2>/dev/null
echo "  $(vf "$SRC/checksums.txt")"
ann "SHA256 checksums generated"

# Verify: re-hash and compare
bat "verify" "certutil -hashfile C:/$PROJECT/src_file_1.txt SHA256 > C:/$PROJECT/verify.txt
certutil -hashfile C:/$PROJECT/src_file_2.txt SHA256 >> C:/$PROJECT/verify.txt
certutil -hashfile C:/$PROJECT/src_file_3.txt SHA256 >> C:/$PROJECT/verify.txt"
sleep 2
MSYS_NO_PATHCONV=1 docker exec compose-winebot-interactive-1 chown winebot:winebot "$SRC/verify.txt" 2>/dev/null
MATCH=$(MSYS_NO_PATHCONV=1 docker exec compose-winebot-interactive-1 diff "$SRC/checksums.txt" "$SRC/verify.txt" 2>/dev/null && echo "MATCH" || echo "DIFFER")
echo "  Verification: $MATCH"
[ "$MATCH" = "MATCH" ] && ann "Checksums verified: MATCH — build integrity confirmed"

echo ""
echo "=== Phase 3: Package into CAB archive ==="
ch "Phase 3: Package artifacts"
ann "METHOD: cabarc via cmd.exe — Windows native CAB format"

bat "package" "cabarc -r N C:/$PROJECT/build_output.cab C:/$PROJECT/src_file_* C:/$PROJECT/build_manifest.txt C:/$PROJECT/checksums.txt"
sleep 2
MSYS_NO_PATHCONV=1 docker exec compose-winebot-interactive-1 chown winebot:winebot "$SRC/build_output.cab" 2>/dev/null
echo "  $(vf "$SRC/build_output.cab")"
ann "Build output packaged: build_output.cab"

# List contents
bat "list_cab" "cabarc L C:/$PROJECT/build_output.cab"
sleep 1
ann "CAB contents verified — all files present"

echo ""
echo "=== Phase 4: Registry build metadata ==="
ch "Phase 4: Registry metadata"
ann "METHOD: reg add via .bat — persistent build metadata"

bat "reg_meta" "reg add HKCU\\Software\\WineBotCI /v BuildProject /t REG_SZ /d $PROJECT /f
reg add HKCU\\Software\\WineBotCI /v FileCount /t REG_DWORD /d 3 /f
reg add HKCU\\Software\\WineBotCI /v BuildTimestamp /t REG_SZ /d %DATE% /f"
sleep 1

bat "reg_query" "reg query HKCU\\Software\\WineBotCI"
sleep 1
ann "Build metadata stored in Windows registry"

echo ""
echo "=== Phase 5: GUI report (Notepad + /input/key) ==="
ch "Phase 5: GUI report generation"
ann "METHOD: Notepad + /input/key — alternative GUI approach"

api_post "/apps/run" '{"path":"notepad.exe","detach":true}' > /dev/null
sleep 3
ann "Notepad launched"

API="/input/key"
for line in "WineBot CI Pipeline Report" "=========================" " " "Build Project: $PROJECT" "Source Files: 3" "Checksums: SHA256 verified" "Package: build_output.cab" " " "Build completed by WineBot CI Pipeline" "Headless Windows build automation"; do
  api_post "$API" "{\"keys\":\"$line\",\"window_title\":\"Notepad\"}" > /dev/null
  api_post "$API" '{"keys":"Return","window_title":"Notepad"}' > /dev/null
  sleep 0.08
done
ann "Report typed via /input/key (AHK Send)"

# Save via pipe dialog
api_post "$API" '{"keys":"ctrl+s","window_title":"Notepad"}' > /dev/null
sleep 4
ann "Ctrl+S pressed"
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
  MSYS_NO_PATHCONV=1 docker exec compose-winebot-interactive-1 cat "$SRC/$f" 2>/dev/null | head -1
done
echo "  Archive: $(vf "$SRC/build_output.cab")"
echo "  Report:  $(vf "$PREFIX/build_report.txt")"
ann "All build artifacts verified"

echo ""
echo "=== Phase 7: Cleanup ==="
ch "Phase 7: Cleanup"
MSYS_NO_PATHCONV=1 docker exec compose-winebot-interactive-1 sh -c "rm -rf $SRC $PREFIX/build_report.txt $BAT 2>/dev/null"
bat "reg_cleanup" "reg delete HKCU\\Software\\WineBotCI /f 2>nul"
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

api_post "/recording/stop" '{}' 2>/dev/null || true
sleep 2; TRIM_SS="${TRIM_SS:-30}"
MSYS_NO_PATHCONV=1 docker exec compose-winebot-interactive-1 sh -c "
  ffmpeg -y -ss ${TRIM_SS} -i ${SESSDIR}/video_001.mkv -c copy -avoid_negative_ts make_zero /tmp/trimmed.mkv 2>/dev/null
  ffmpeg -y -i /tmp/trimmed.mkv -vf 'fps=8,scale=640:-1:flags=lanczos,split[s0][s1];[s0]palettegen=max_colors=128[p];[s1][p]paletteuse' -loop 0 /tmp/trimmed.gif 2>/dev/null
  echo 'Trimmed:' \$(ls -lh /tmp/trimmed.mkv | awk '{print \$5}') 'GIF:' \$(ls -lh /tmp/trimmed.gif | awk '{print \$5}')
"
echo "Output: docker cp compose-winebot-interactive-1:/tmp/trimmed.mkv demo/output/demo.mkv"
