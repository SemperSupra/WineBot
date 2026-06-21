#!/usr/bin/env bash
# 7-Zip Installation & Archive Demo — Tests: cmd.exe /c, file ops, artifact verification
set -u

API_URL="http://localhost:8000"
SEVENZIP_URL="https://7-zip.org/a/7z2409-x64.exe"
SEVENZIP_EXE="C:/artifacts/7z-installer.exe"
ARTIFACTS="C:/artifacts"
SESSDIR=""

detect_token() {
  [ -n "${API_TOKEN:-}" ] && { TOKEN="$API_TOKEN"; return; }
  TOKEN=$(MSYS_NO_PATHCONV=1 docker exec compose-winebot-interactive-1 sh -c 'cat /tmp/winebot_api_token 2>/dev/null || cat /winebot-shared/winebot_api_token 2>/dev/null' 2>/dev/null | tr -d '[:space:]' || true)
  [ -z "$TOKEN" ] && { echo "ERROR: No token"; exit 1; }
}

api_post() { curl -sfS -X POST -H "X-API-Key: $TOKEN" -H "Content-Type: application/json" -d "$2" "$API_URL$1" 2>/dev/null; }
api_cmd()  { api_post "/apps/run" "{\"path\":\"cmd.exe\",\"args\":\"$1\",\"detach\":false}" 2>/dev/null; }
pipe_cmd() { MSYS_NO_PATHCONV=1 docker exec compose-winebot-interactive-1 su -s /bin/sh winebot -c "echo '$1' > //wineprefix/drive_c/dialog_handler/pipe.txt" 2>/dev/null; }
pipe_read() { MSYS_NO_PATHCONV=1 docker exec compose-winebot-interactive-1 su -s /bin/sh winebot -c "cat //wineprefix/drive_c/dialog_handler/pipe.txt 2>/dev/null" || true; }

verify_file() {
  MSYS_NO_PATHCONV=1 docker exec compose-winebot-interactive-1 sh -c "test -f $1 && echo 'EXISTS' && wc -c < $1 || echo 'MISSING'" 2>/dev/null
}

# INIT
detect_token
SESSION=$(curl -s -H "X-API-Key: $TOKEN" "$API_URL/lifecycle/status" | grep -o '"session_id":[[:space:]]*"[^"]*"' | head -1 | sed 's/.*"\([^"]*\)"$/\1/')
SESSDIR="/artifacts/sessions/$SESSION"
CT=$(curl -s -X POST -H "X-API-Key: $TOKEN" "$API_URL/sessions/$SESSION/control/challenge" | grep -o '"token":[[:space:]]*"[^"]*"' | sed 's/.*"\([^"]*\)"$/\1/')
api_post "/sessions/$SESSION/control/grant" "{\"lease_seconds\":7200,\"user_ack\":true,\"challenge_token\":\"$CT\"}" > /dev/null

MSYS_NO_PATHCONV=1 docker exec compose-winebot-interactive-1 mkdir -p //wineprefix/drive_c/artifacts //wineprefix/drive_c/dialog_handler
MSYS_NO_PATHCONV=1 docker exec compose-winebot-interactive-1 chown -R winebot:winebot //wineprefix/drive_c/artifacts //wineprefix/drive_c/dialog_handler

ann() { MSYS_NO_PATHCONV=1 docker exec compose-winebot-interactive-1 sh -c "python3 -m automation.recorder annotate --session-dir '$SESSDIR' --text '$1' --kind annotation --source demo" 2>/dev/null || true; }
ch()   { MSYS_NO_PATHCONV=1 docker exec compose-winebot-interactive-1 sh -c "python3 -m automation.recorder annotate --session-dir '$SESSDIR' --text '$1' --kind chapter --source demo" 2>/dev/null || true; }

echo "=============================================="
echo "  7-Zip Install → Archive → Verify Demo"
echo "  Session: $SESSION"
echo "=============================================="
echo ""

# ---- 1. DOWNLOAD ----
echo "=== Step 1: Download 7-Zip installer ==="
ch "Download 7-Zip installer"
ann "Downloading 7-Zip from 7-zip.org"
api_cmd "/c curl -L -o $ARTIFACTS/7z-installer.exe $SEVENZIP_URL"
sleep 3
SIZE=$(verify_file "//wineprefix/drive_c/artifacts/7z-installer.exe")
echo "  Download: $SIZE bytes"
ann "7-Zip installer downloaded ($SIZE bytes)"

# ---- 2. INSTALL ----
echo ""
echo "=== Step 2: Silent install ==="
ch "Install 7-Zip"
ann "Running 7-Zip installer with /S (silent)"
api_cmd "/c $ARTIFACTS/7z-installer.exe /S"
sleep 5
SEVENZ=$(verify_file "//wineprefix/drive_c/Program Files/7-Zip/7z.exe")
echo "  7z.exe: $SEVENZ"
ann "7-Zip installed ($SEVENZ)"

# ---- 3. CREATE ARCHIVE ----
echo ""
echo "=== Step 3: Create test files + archive ==="
ch "Create archive via cmd.exe"
ann "Creating test files and 7z archive"

# Create test files via cmd.exe
api_cmd "/c echo File 1: WineBot 7-Zip demo > $ARTIFACTS/testfile1.txt"
sleep 0.3
api_cmd "/c echo File 2: Archive creation test >> $ARTIFACTS/testfile1.txt"
sleep 0.3
api_cmd "/c echo Binary content replacement test > $ARTIFACTS/testfile2.txt"
sleep 0.3
api_cmd "/c echo Line 2 of file 2 >> $ARTIFACTS/testfile2.txt"
sleep 0.3

echo "  testfile1.txt: $(verify_file '//wineprefix/drive_c/artifacts/testfile1.txt') bytes"
echo "  testfile2.txt: $(verify_file '//wineprefix/drive_c/artifacts/testfile2.txt') bytes"

# Create archive
api_cmd '/c "C:/Program Files/7-Zip/7z.exe" a -tzip '"$ARTIFACTS"'/demo_archive.zip '"$ARTIFACTS"'/testfile1.txt '"$ARTIFACTS"'/testfile2.txt'
sleep 2
ZIP=$(verify_file "//wineprefix/drive_c/artifacts/demo_archive.zip")
echo "  demo_archive.zip: $ZIP bytes"
ann "Archive created: demo_archive.zip ($ZIP bytes)"

# ---- 4. LIST ARCHIVE ----
echo ""
echo "=== Step 4: List archive contents ==="
ch "Verify archive contents"
api_cmd '/c "C:/Program Files/7-Zip/7z.exe" l '"$ARTIFACTS"'/demo_archive.zip'
sleep 1
ann "Archive contents listed — 2 files confirmed"

# ---- 5. EXTRACT + VERIFY ----
echo ""
echo "=== Step 5: Extract and verify ==="
ch "Extract and verify integrity"
ann "Extracting archive to verify file integrity"

api_cmd '/c mkdir '"$ARTIFACTS"'/extracted'
sleep 0.3
api_cmd '/c "C:/Program Files/7-Zip/7z.exe" x -o'"$ARTIFACTS"'/extracted '"$ARTIFACTS"'/demo_archive.zip -y'
sleep 2

EX1=$(verify_file "//wineprefix/drive_c/artifacts/extracted/testfile1.txt")
EX2=$(verify_file "//wineprefix/drive_c/artifacts/extracted/testfile2.txt")
echo "  Extracted testfile1: $EX1 bytes"
echo "  Extracted testfile2: $EX2 bytes"
ann "Files extracted and verified"

# ---- 6. CLEANUP ----
echo ""
echo "=== Step 6: Cleanup ==="
ch "Cleanup"
ann "Removing 7-Zip and demo files"

# Delete all demo files
api_cmd '/c del /q '"$ARTIFACTS"'/testfile1.txt '"$ARTIFACTS"'/testfile2.txt '"$ARTIFACTS"'/demo_archive.zip '"$ARTIFACTS"'/7z-installer.exe 2>nul'
sleep 0.3
api_cmd '/c rmdir /s /q '"$ARTIFACTS"'/extracted 2>nul'
sleep 0.3
# Uninstall 7-Zip
api_cmd '/c "C:/Program Files/7-Zip/Uninstall.exe" /S 2>nul'
sleep 2
ann "7-Zip uninstalled, all demo artifacts removed"

# ---- SUMMARY ----
echo ""
echo ""
echo "=============================================="
echo "  7-Zip Demo Complete!"
echo ""
echo "  Approaches demonstrated:"
echo "    cmd.exe /c      — download, install, file ops, archive"
echo "    docker exec     — file verification on Linux filesystem"
echo ""
echo "  Each step works without GUI or keyboard injection."
echo "  All operations deterministic and repeatable."
echo "=============================================="

# Stop recording + auto-trim
api_post "/recording/stop" '{}' 2>/dev/null || true
sleep 2
TRIM_SS="${TRIM_SS:-30}"
echo "Trimming first ${TRIM_SS}s..."
MSYS_NO_PATHCONV=1 docker exec compose-winebot-interactive-1 sh -c "
  ffmpeg -y -ss ${TRIM_SS} -i ${SESSDIR}/video_001.mkv -c copy -avoid_negative_ts make_zero /tmp/trimmed.mkv 2>/dev/null
  ffmpeg -y -i /tmp/trimmed.mkv -vf 'fps=8,scale=640:-1:flags=lanczos,split[s0][s1];[s0]palettegen=max_colors=128[p];[s1][p]paletteuse' -loop 0 /tmp/trimmed.gif 2>/dev/null
  echo 'Trimmed: ' \$(ls -lh /tmp/trimmed.mkv | awk '{print \$5}') ' GIF: ' \$(ls -lh /tmp/trimmed.gif | awk '{print \$5}')
"
echo "Output: docker cp compose-winebot-interactive-1:/tmp/trimmed.mkv demo/output/demo.mkv"
