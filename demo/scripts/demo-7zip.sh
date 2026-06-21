#!/usr/bin/env bash
# 7-Zip Install + Archive Demo
set -u

API_URL="http://localhost:8000"
SEVENZIP_URL="https://7-zip.org/a/7z2409-x64.exe"
ARTIFACTS_LIN="//wineprefix/drive_c/artifacts"
ARTIFACTS_WIN="C:/artifacts"
BAT_DIR="//wineprefix/drive_c/artifacts/bats"

detect_token() {
  [ -n "${API_TOKEN:-}" ] && { TOKEN="$API_TOKEN"; return; }
  TOKEN=$(MSYS_NO_PATHCONV=1 docker exec compose-winebot-interactive-1 sh -c 'cat /tmp/winebot_api_token 2>/dev/null || cat /winebot-shared/winebot_api_token 2>/dev/null' 2>/dev/null | tr -d '[:space:]' || true)
  [ -z "$TOKEN" ] && { echo "ERROR: No token"; exit 1; }
}

api_post() { curl -sfS -X POST -H "X-API-Key: $TOKEN" -H "Content-Type: application/json" -d "$2" "$API_URL$1" 2>/dev/null; }
ann() { MSYS_NO_PATHCONV=1 docker exec compose-winebot-interactive-1 sh -c "python3 -m automation.recorder annotate --session-dir '$SESSDIR' --text \"$1\" --kind annotation --source demo" 2>/dev/null || true; }
ch()   { MSYS_NO_PATHCONV=1 docker exec compose-winebot-interactive-1 sh -c "python3 -m automation.recorder annotate --session-dir '$SESSDIR' --text \"$1\" --kind chapter --source demo" 2>/dev/null || true; }
verify_file() { MSYS_NO_PATHCONV=1 docker exec compose-winebot-interactive-1 sh -c "test -f $1 && echo EXISTS && wc -c < $1 || echo MISSING" 2>/dev/null; }

# Write a .bat file and run it via /apps/run
bat_run() {
  local name="$1" content="$2"
  MSYS_NO_PATHCONV=1 docker exec compose-winebot-interactive-1 sh -c "cat > ${BAT_DIR}/${name}.bat << 'BATEOF'
${content}
BATEOF
chown winebot:winebot ${BAT_DIR}/${name}.bat"
  api_post "/apps/run" "{\"path\":\"cmd.exe\",\"args\":\"/c ${ARTIFACTS_WIN}/bats/${name}.bat\",\"detach\":false}" > /dev/null
}

# Download from Linux host (curl NOT available inside Wine cmd.exe)
linux_dl() {
  local url="$1" dest="$2"
  MSYS_NO_PATHCONV=1 docker exec compose-winebot-interactive-1 sh -c "curl -sL '$url' -o '$dest' && chown winebot:winebot '$dest' && echo 'Downloaded: ' \$(wc -c < '$dest') ' bytes'" 2>/dev/null
}

# INIT
detect_token
SESSION=$(curl -s -H "X-API-Key: $TOKEN" "$API_URL/lifecycle/status" | grep -o '"session_id":[[:space:]]*"[^"]*"' | head -1 | sed 's/.*"\([^"]*\)"$/\1/')
SESSDIR="/artifacts/sessions/$SESSION"
CT=$(curl -s -X POST -H "X-API-Key: $TOKEN" "$API_URL/sessions/$SESSION/control/challenge" | grep -o '"token":[[:space:]]*"[^"]*"' | sed 's/.*"\([^"]*\)"$/\1/')
api_post "/sessions/$SESSION/control/grant" "{\"lease_seconds\":7200,\"user_ack\":true,\"challenge_token\":\"$CT\"}" > /dev/null
MSYS_NO_PATHCONV=1 docker exec compose-winebot-interactive-1 mkdir -p "$ARTIFACTS_LIN" "${BAT_DIR}" 2>/dev/null
MSYS_NO_PATHCONV=1 docker exec compose-winebot-interactive-1 chown -R winebot:winebot "$ARTIFACTS_LIN" 2>/dev/null

echo "=============================================="
echo "  7-Zip Demo — All via cmd.exe /c .bat files"
echo "  Session: $SESSION"
echo "=============================================="
echo ""

# ---- 1. DOWNLOAD ----
echo "=== Step 1: Download 7-Zip ==="
ch "Download 7-Zip installer"
ann "Downloading 7-Zip via Linux curl (not available in Wine cmd.exe)"
linux_dl "$SEVENZIP_URL" "${ARTIFACTS_LIN}/7z-installer.exe"
sleep 2
echo "  $(verify_file "${ARTIFACTS_LIN}/7z-installer.exe")"

# ---- 2. INSTALL ----
echo ""
echo "=== Step 2: Silent install ==="
ch "Install 7-Zip"
ann "Running 7-Zip installer with /S flag"
bat_run "install" "${ARTIFACTS_WIN}/7z-installer.exe /S"
sleep 5
echo "  7z.exe: $(verify_file '//wineprefix/drive_c/Program Files/7-Zip/7z.exe')"

# ---- 3. CREATE FILES + ARCHIVE ----
echo ""
echo "=== Step 3: Create test files + archive ==="
ch "Create test files and archive"
ann "Creating test content and building .zip archive"
bat_run "create_files" "echo File 1 content > ${ARTIFACTS_WIN}/testfile1.txt"
sleep 0.5
bat_run "append_file" "echo File 2 content > ${ARTIFACTS_WIN}/testfile2.txt"
sleep 0.5
echo "  testfile1: $(verify_file "${ARTIFACTS_LIN}/testfile1.txt")"
echo "  testfile2: $(verify_file "${ARTIFACTS_LIN}/testfile2.txt")"

ann "Building demo_archive.zip with 7z"
bat_run "archive" "\"C:/Program Files/7-Zip/7z.exe\" a -tzip ${ARTIFACTS_WIN}/demo_archive.zip ${ARTIFACTS_WIN}/testfile1.txt ${ARTIFACTS_WIN}/testfile2.txt"
sleep 2
echo "  archive: $(verify_file "${ARTIFACTS_LIN}/demo_archive.zip")"

# ---- 4. LIST + EXTRACT + VERIFY ----
echo ""
echo "=== Step 4: List, extract, and verify ==="
ch "Verify archive integrity"
ann "Listing archive contents"
bat_run "list" "\"C:/Program Files/7-Zip/7z.exe\" l ${ARTIFACTS_WIN}/demo_archive.zip"
sleep 1

ann "Extracting archive"
bat_run "extract" "mkdir ${ARTIFACTS_WIN}/extracted & \"C:/Program Files/7-Zip/7z.exe\" x -o${ARTIFACTS_WIN}/extracted ${ARTIFACTS_WIN}/demo_archive.zip -y"
sleep 2
echo "  extracted testfile1: $(verify_file "${ARTIFACTS_LIN}/extracted/testfile1.txt")"
echo "  extracted testfile2: $(verify_file "${ARTIFACTS_LIN}/extracted/testfile2.txt")"

# ---- 5. CLEANUP ----
echo ""
echo "=== Step 5: Uninstall + cleanup ==="
ch "Uninstall and cleanup"
ann "Removing 7-Zip and all demo artifacts"
bat_run "cleanup" "del /q ${ARTIFACTS_WIN}/testfile1.txt ${ARTIFACTS_WIN}/testfile2.txt ${ARTIFACTS_WIN}/demo_archive.zip ${ARTIFACTS_WIN}/7z-installer.exe 2>nul & rmdir /s /q ${ARTIFACTS_WIN}/extracted ${ARTIFACTS_WIN}/bats 2>nul & \"C:/Program Files/7-Zip/Uninstall.exe\" /S 2>nul"
sleep 3
ann "Cleanup complete"

echo ""
echo "=============================================="
echo "  7-Zip Demo Complete! (cmd.exe /c via .bat)"
echo "=============================================="

api_post "/recording/stop" '{}' 2>/dev/null || true
sleep 2
echo "Trimming first ${TRIM_SS:-30}s..."
MSYS_NO_PATHCONV=1 docker exec compose-winebot-interactive-1 sh -c "
  ffmpeg -y -ss ${TRIM_SS:-30} -i ${SESSDIR}/video_001.mkv -c copy -avoid_negative_ts make_zero /tmp/trimmed.mkv 2>/dev/null
  ffmpeg -y -i /tmp/trimmed.mkv -vf 'fps=8,scale=640:-1:flags=lanczos,split[s0][s1];[s0]palettegen=max_colors=128[p];[s1][p]paletteuse' -loop 0 /tmp/trimmed.gif 2>/dev/null
  echo Trimmed: \$(ls -lh /tmp/trimmed.mkv | awk '{print \$5}') GIF: \$(ls -lh /tmp/trimmed.gif | awk '{print \$5}')
"
echo "Output: docker cp compose-winebot-interactive-1:/tmp/trimmed.mkv demo/output/demo.mkv"
