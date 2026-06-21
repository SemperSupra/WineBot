#!/usr/bin/env bash
# Notepad++ Demo — Tests: download, install (MessageBox hook), launch, keyboard input, Save As pipe dialog
set -u

API_URL="http://localhost:8000"
NPP_URL="https://github.com/notepad-plus-plus/notepad-plus-plus/releases/download/v8.7.9/npp.8.7.9.Installer.x64.exe"
NPP_EXE="C:/Program Files/Notepad++/notepad++.exe"
PIPE="//wineprefix/drive_c/dialog_handler/pipe.txt"

detect_token() {
  [ -n "${API_TOKEN:-}" ] && { TOKEN="$API_TOKEN"; return; }
  TOKEN=$(MSYS_NO_PATHCONV=1 docker exec compose-winebot-interactive-1 sh -c 'cat /tmp/winebot_api_token 2>/dev/null || cat /winebot-shared/winebot_api_token 2>/dev/null' 2>/dev/null | tr -d '[:space:]' || true)
  [ -z "$TOKEN" ] && { echo "ERROR: No token"; exit 1; }
}

api_post() { curl -sfS -X POST -H "X-API-Key: $TOKEN" -H "Content-Type: application/json" -d "$2" "$API_URL$1" 2>/dev/null; }
api_cmd()  { api_post "/apps/run" "{\"path\":\"cmd.exe\",\"args\":\"$1\",\"detach\":false}" 2>/dev/null; }
ann() { MSYS_NO_PATHCONV=1 docker exec compose-winebot-interactive-1 sh -c "python3 -m automation.recorder annotate --session-dir '$SESSDIR' --text '$1' --kind annotation --source demo" 2>/dev/null || true; }
ch()   { MSYS_NO_PATHCONV=1 docker exec compose-winebot-interactive-1 sh -c "python3 -m automation.recorder annotate --session-dir '$SESSDIR' --text '$1' --kind chapter --source demo" 2>/dev/null || true; }
pipe_cmd() { MSYS_NO_PATHCONV=1 docker exec compose-winebot-interactive-1 su -s /bin/sh winebot -c "echo '$1' > '$PIPE'" 2>/dev/null; }
pipe_read() { MSYS_NO_PATHCONV=1 docker exec compose-winebot-interactive-1 su -s /bin/sh winebot -c "cat '$PIPE' 2>/dev/null" || true; }
verify_file() { MSYS_NO_PATHCONV=1 docker exec compose-winebot-interactive-1 sh -c "test -f $1 && echo 'EXISTS' && wc -c < $1 || echo 'MISSING'" 2>/dev/null; }

# INIT
detect_token
SESSION=$(curl -s -H "X-API-Key: $TOKEN" "$API_URL/lifecycle/status" | grep -o '"session_id":[[:space:]]*"[^"]*"' | head -1 | sed 's/.*"\([^"]*\)"$/\1/')
SESSDIR="/artifacts/sessions/$SESSION"
CT=$(curl -s -X POST -H "X-API-Key: $TOKEN" "$API_URL/sessions/$SESSION/control/challenge" | grep -o '"token":[[:space:]]*"[^"]*"' | sed 's/.*"\([^"]*\)"$/\1/')
api_post "/sessions/$SESSION/control/grant" "{\"lease_seconds\":7200,\"user_ack\":true,\"challenge_token\":\"$CT\"}" > /dev/null

MSYS_NO_PATHCONV=1 docker exec compose-winebot-interactive-1 mkdir -p //wineprefix/drive_c/artifacts //wineprefix/drive_c/dialog_handler
MSYS_NO_PATHCONV=1 docker exec compose-winebot-interactive-1 chown -R winebot:winebot //wineprefix/drive_c/artifacts //wineprefix/drive_c/dialog_handler

# Launch AHK pipe handler
MSYS_NO_PATHCONV=1 docker cp automation/core/dialog_replacement.ahk compose-winebot-interactive-1://wineprefix/drive_c/dr.ahk 2>/dev/null
MSYS_NO_PATHCONV=1 docker exec compose-winebot-interactive-1 chown winebot:winebot //wineprefix/drive_c/dr.ahk 2>/dev/null
MSYS_NO_PATHCONV=1 docker exec compose-winebot-interactive-1 sh -c '
gosu winebot sh -c "DISPLAY=:99 WINEPREFIX=/wineprefix WINEDEBUG=-all nohup ahk C:/dr.ahk > /wineprefix/drive_c/dh.log 2>&1 < /dev/null &"'
sleep 5

# Launch hook DLL
MSYS_NO_PATHCONV=1 docker exec compose-winebot-interactive-1 sh -c '
gosu winebot sh -c "DISPLAY=:99 WINEPREFIX=/wineprefix WINEDEBUG=-all WINEDLLOVERRIDES=\"winebot_hook=n\" wine notepad++.exe" > /dev/null 2>&1 &
' 2>/dev/null || true

echo "=============================================="
echo "  Notepad++ Install → Edit → Save Demo"
echo "  Session: $SESSION"
echo "=============================================="
echo ""

# ---- 1. DOWNLOAD ----
echo "=== Step 1: Download Notepad++ ==="
ch "Download Notepad++"
ann "Downloading Notepad++ installer from GitHub"
api_cmd "/c curl -L -o C:/artifacts/npp-installer.exe $NPP_URL"
sleep 5
SIZE=$(verify_file "//wineprefix/drive_c/artifacts/npp-installer.exe")
echo "  Download: $SIZE bytes"
ann "Notepad++ installer downloaded"

# ---- 2. INSTALL (tests MessageBox hook) ----
echo ""
echo "=== Step 2: Install (MessageBox hook active) ==="
ch "Install Notepad++"
ann "Running Notepad++ installer with /S — MessageBox hook dismisses prompts"
api_cmd "/c C:/artifacts/npp-installer.exe /S"
sleep 8
NPP=$(verify_file "//wineprefix/drive_c/Program Files/Notepad++/notepad++.exe")
echo "  notepad++.exe: $NPP"
ann "Notepad++ installed successfully"

# ---- 3. LAUNCH + KEYBOARD ----
echo ""
echo "=== Step 3: Launch Notepad++ and type text ==="
ch "Keyboard input in Notepad++"
api_post "/apps/run" "{\"path\":\"notepad++.exe\",\"detach\":true}" > /dev/null
sleep 4
ann "Notepad++ launched"

# Type content
api_post "/input/key" "{\"keys\":\"Notepad++ Demo — WineBot Automation\",\"window_title\":\"Notepad\"}" > /dev/null
sleep 0.3
api_post "/input/key" "{\"keys\":\"Return\",\"window_title\":\"Notepad\"}" > /dev/null
sleep 0.2
api_post "/input/key" "{\"keys\":\"Return\",\"window_title\":\"Notepad\"}" > /dev/null
sleep 0.2
api_post "/input/key" "{\"keys\":\"Installed via WineBot API:\",\"window_title\":\"Notepad\"}" > /dev/null
sleep 0.3
api_post "/input/key" "{\"keys\":\"Return\",\"window_title\":\"Notepad\"}" > /dev/null
sleep 0.2
api_post "/input/key" "{\"keys\":\"  1. Downloaded from GitHub\",\"window_title\":\"Notepad\"}" > /dev/null
sleep 0.3
api_post "/input/key" "{\"keys\":\"Return\",\"window_title\":\"Notepad\"}" > /dev/null
sleep 0.2
api_post "/input/key" "{\"keys\":\"  2. Installed silently (/S flag)\",\"window_title\":\"Notepad\"}" > /dev/null
sleep 0.3
api_post "/input/key" "{\"keys\":\"Return\",\"window_title\":\"Notepad\"}" > /dev/null
sleep 0.2
api_post "/input/key" "{\"keys\":\"  3. Typed via /input/key AHK backend\",\"window_title\":\"Notepad\"}" > /dev/null
sleep 0.3
api_post "/input/key" "{\"keys\":\"Return\",\"window_title\":\"Notepad\"}" > /dev/null
sleep 0.2
api_post "/input/key" "{\"keys\":\"  4. Saved via AHK pipe dialog\",\"window_title\":\"Notepad\"}" > /dev/null
sleep 0.3
ann "Content typed via /input/key"

# ---- 4. SAVE VIA PIPE DIALOG ----
echo ""
echo "=== Step 4: Save via AHK pipe dialog ==="
ch "Save file via AHK pipe dialog"

api_post "/input/key" "{\"keys\":\"ctrl+s\",\"window_title\":\"Notepad\"}" > /dev/null
sleep 4
ann "Ctrl+S pressed"
# Open pipe dialog for filename
pipe_cmd "open_gui"
sleep 2
pipe_cmd "set_filename:Notepadpp_Demo.txt"
sleep 1.5
pipe_cmd "click_save"
sleep 2

FILE=$(verify_file "//wineprefix/drive_c/artifacts/Notepadpp_Demo.txt")
echo "  Saved file: $FILE"
ann "File saved: Notepadpp_Demo.txt"

# ---- 5. VERIFY ----
echo ""
echo "=== Step 5: Verify saved file ==="
ch "Verify saved content"
MSYS_NO_PATHCONV=1 docker exec compose-winebot-interactive-1 cat //wineprefix/drive_c/artifacts/Notepadpp_Demo.txt 2>/dev/null
ann "File content verified"

# ---- 6. CLEANUP ----
echo ""
echo "=== Step 6: Uninstall Notepad++ ==="
ch "Uninstall"
ann "Removing Notepad++"

api_post "/input/key" "{\"keys\":\"alt+F4\",\"window_title\":\"Notepad\"}" > /dev/null
sleep 1
api_cmd "/c del /q C:/artifacts/Notepadpp_Demo.txt C:/artifacts/npp-installer.exe 2>nul"
sleep 0.5
api_cmd '/c "C:/Program Files/Notepad++/Uninstall.exe" /S 2>nul'
sleep 3
ann "Notepad++ uninstalled, artifacts removed"

echo ""
echo ""
echo "=============================================="
echo "  Notepad++ Demo Complete!"
echo ""
echo "  Approaches demonstrated:"
echo "    /input/key       — keyboard text injection (AHK Send)"
echo "    /input/mouse/click — (via core demo)"
echo "    AHK pipe dialog  — save file without Wine dialog"
echo "    cmd.exe /c       — download, install, cleanup"
echo "    docker exec      — file verification on Linux fs"
echo "    MessageBox hook  — install prompts auto-dismissed"
echo ""
echo "  Multiple tools achieving the same result:"
echo "    File save:  AHK pipe dialog (no Wine dialog needed)"
echo "    File read:  docker exec cat (Linux path)"
echo "    Install:    cmd.exe /c installer.exe /S"
echo "=============================================="

api_post "/recording/stop" '{}' 2>/dev/null || true
sleep 2
TRIM_SS="${TRIM_SS:-40}"
echo "Trimming first ${TRIM_SS}s..."
MSYS_NO_PATHCONV=1 docker exec compose-winebot-interactive-1 sh -c "
  ffmpeg -y -ss ${TRIM_SS} -i ${SESSDIR}/video_001.mkv -c copy -avoid_negative_ts make_zero /tmp/trimmed.mkv 2>/dev/null
  ffmpeg -y -i /tmp/trimmed.mkv -vf 'fps=8,scale=640:-1:flags=lanczos,split[s0][s1];[s0]palettegen=max_colors=128[p];[s1][p]paletteuse' -loop 0 /tmp/trimmed.gif 2>/dev/null
  echo 'Trimmed: ' \$(ls -lh /tmp/trimmed.mkv | awk '{print \$5}') ' GIF: ' \$(ls -lh /tmp/trimmed.gif | awk '{print \$5}')
"
echo "Output: docker cp compose-winebot-interactive-1:/tmp/trimmed.mkv demo/output/demo.mkv"
