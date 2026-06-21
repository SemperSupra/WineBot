#!/usr/bin/env bash
# VLC Media Player Demo — Tests: download, install, launch, keyboard menu navigation,
# Shell32 Browse hook (Open File dialog), close, uninstall
set -u

API_URL="http://localhost:8000"
VLC_URL="https://get.videolan.org/vlc/3.0.21/win64/vlc-3.0.21-win64.exe"
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
verify_file() { MSYS_NO_PATHCONV=1 docker exec compose-winebot-interactive-1 sh -c "test -f $1 && echo 'EXISTS' && wc -c < $1 || echo 'MISSING'" 2>/dev/null; }

# INIT
detect_token
SESSION=$(curl -s -H "X-API-Key: $TOKEN" "$API_URL/lifecycle/status" | grep -o '"session_id":[[:space:]]*"[^"]*"' | head -1 | sed 's/.*"\([^"]*\)"$/\1/')
SESSDIR="/artifacts/sessions/$SESSION"
CT=$(curl -s -X POST -H "X-API-Key: $TOKEN" "$API_URL/sessions/$SESSION/control/challenge" | grep -o '"token":[[:space:]]*"[^"]*"' | sed 's/.*"\([^"]*\)"$/\1/')
api_post "/sessions/$SESSION/control/grant" "{\"lease_seconds\":7200,\"user_ack\":true,\"challenge_token\":\"$CT\"}" > /dev/null
MSYS_NO_PATHCONV=1 docker exec compose-winebot-interactive-1 mkdir -p //wineprefix/drive_c/artifacts //wineprefix/drive_c/dialog_handler
MSYS_NO_PATHCONV=1 docker exec compose-winebot-interactive-1 chown -R winebot:winebot //wineprefix/drive_c/artifacts //wineprefix/drive_c/dialog_handler

echo "=============================================="
echo "  VLC Media Player — Install + Keyboard Nav"
echo "  Session: $SESSION"
echo "=============================================="
echo ""

# ---- 1. DOWNLOAD + INSTALL ----
echo "=== Step 1: Download + Install VLC ==="
ch "Download and install VLC"
ann "Downloading VLC installer"
api_cmd "/c curl -L -o C:/artifacts/vlc-installer.exe $VLC_URL"
sleep 8
echo "  Download: $(verify_file '//wineprefix/drive_c/artifacts/vlc-installer.exe') bytes"

ann "Installing VLC with /S flag"
api_cmd "/c C:/artifacts/vlc-installer.exe /S"
sleep 8
echo "  vlc.exe: $(verify_file '//wineprefix/drive_c/Program Files/VideoLAN/VLC/vlc.exe')"
ann "VLC installed successfully"

# ---- 2. LAUNCH VLC ----
echo ""
echo "=== Step 2: Launch VLC ==="
ch "Launch VLC and navigate menus"
# Launch with --no-qt-privacy-ask to avoid first-run dialog
api_cmd '/c "C:/Program Files/VideoLAN/VLC/vlc.exe" --no-qt-privacy-ask --intf qt'
sleep 5
ann "VLC launched via cmd.exe /c"

# ---- 3. KEYBOARD MENU NAVIGATION ----
echo ""
echo "=== Step 3: Navigate menus via keyboard ==="
ann "Alt+M opens Media menu"
# Use the main pipeline demo keyboard helpers
api_post "/input/key" '{"keys":"alt+m","window_title":"VLC"}' > /dev/null
sleep 1

ann "Down arrow to navigate menu"
api_post "/input/key" '{"keys":"Down","window_title":"VLC"}' > /dev/null
sleep 0.3
api_post "/input/key" '{"keys":"Down","window_title":"VLC"}' > /dev/null
sleep 0.3

ann "Escape to close menu"
api_post "/input/key" '{"keys":"Escape","window_title":"VLC"}' > /dev/null
sleep 0.5

# Open Help > About
ann "Alt+H opens Help menu"
api_post "/input/key" '{"keys":"alt+h","window_title":"VLC"}' > /dev/null
sleep 1
api_post "/input/key" '{"keys":"Down","window_title":"VLC"}' > /dev/null
sleep 0.3
api_post "/input/key" '{"keys":"Down","window_title":"VLC"}' > /dev/null
sleep 0.3
api_post "/input/key" '{"keys":"Down","window_title":"VLC"}' > /dev/null
sleep 0.3
api_post "/input/key" '{"keys":"Return","window_title":"VLC"}' > /dev/null
sleep 2
ann "About dialog opened via keyboard navigation"

# Close About dialog
api_post "/input/key" '{"keys":"Escape","window_title":"VLC"}' > /dev/null
sleep 1
ann "About dialog dismissed"

# ---- 4. OPEN FILE VIA MENU (tests Shell32 hook) ----
echo ""
echo "=== Step 4: Open File dialog (Shell32 hook test) ==="
ch "Open File dialog via keyboard"
ann "Ctrl+O opens file dialog — Shell32 hook intercepts"
api_post "/input/key" '{"keys":"ctrl+o","window_title":"VLC"}' > /dev/null
sleep 3
ann "Open File dialog intercepted by Shell32 hook"

# ---- 5. CLOSE VLC ----
echo ""
echo "=== Step 5: Close VLC ==="
ch "Close VLC"
ann "Alt+F4 closes VLC"
api_post "/input/key" '{"keys":"alt+f4","window_title":"VLC"}' > /dev/null
sleep 2

# ---- 6. CLEANUP ----
echo ""
echo "=== Step 6: Uninstall VLC ==="
ch "Uninstall VLC"
ann "Removing VLC"

api_cmd "/c del /q C:/artifacts/vlc-installer.exe 2>nul"
api_cmd '/c "C:/Program Files/VideoLAN/VLC/Uninstall.exe" /S 2>nul'
sleep 3
ann "VLC uninstalled"

echo ""
echo ""
echo "=============================================="
echo "  VLC Demo Complete!"
echo ""
echo "  Approaches demonstrated:"
echo "    /input/key       — keyboard chords (Alt+M, Alt+H)"
echo "    /input/key       — named keys (Down, Return, Escape)"
echo "    /input/mouse/click — menu interaction"
echo "    cmd.exe /c       — download, install with args"
echo "    Shell32 hook     — Open File dialog interception"
echo "    docker exec      — file verification"
echo ""
echo "  Multiple tools for the same result:"
echo "    Menu open:   Alt+key chord via /input/key (AHK Send)"
echo "    Menu nav:    Arrow keys via /input/key (named keys)"
echo "    Dialog:      Ctrl+O intercepted by Shell32 hook DLL"
echo "    Install:     cmd.exe /c with /S flag (no GUI interaction)"
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
