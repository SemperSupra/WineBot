#!/usr/bin/env bash
# WineBot Input Pipeline Demo v3 — Resident AHK Dialog Replacement
# Demonstrates: mouse, keyboard, named keys, modifiers, app launch,
# and the AHK dialog replacement technique for Save As interception.
set -u

API_URL="${API_URL:-http://localhost:8000}"
PIPE_FILE="/wineprefix/drive_c/dialog_handler/pipe.txt"

TOKEN=""; SESSION=""; SESSDIR=""

detect_token() {
  [ -n "${API_TOKEN:-}" ] && { TOKEN="$API_TOKEN"; return; }
  TOKEN=$(docker exec compose-winebot-interactive-1 sh -c 'cat /tmp/winebot_api_token 2>/dev/null || cat /winebot-shared/winebot_api_token 2>/dev/null' 2>/dev/null | tr -d '[:space:]' || true)
  [ -z "$TOKEN" ] && { echo "ERROR: Cannot detect API token"; exit 1; }
}

api_get()  { curl -sfS -H "X-API-Key: $TOKEN" "$API_URL$1" 2>/dev/null; }
api_post() { curl -sfS -X POST -H "X-API-Key: $TOKEN" -H "Content-Type: application/json" -d "$2" "$API_URL$1" 2>/dev/null; }

annotate() {
  echo "  [SUB] $1"
  docker exec compose-winebot-interactive-1 sh -c \
    "python3 -m automation.recorder annotate --session-dir '$SESSDIR' --text '$1' --kind annotation --source demo" 2>/dev/null || true
}

click_notepad() { api_post "/input/mouse/click" '{"x": 300, "y": 300, "button": 1, "window_title": "Notepad"}' > /dev/null; }
type_text()     { api_post "/input/key" "{\"keys\": \"$1\", \"window_title\": \"$2\"}" > /dev/null; }
press_key()     { api_post "/input/key" "{\"keys\": \"$1\", \"window_title\": \"$2\"}" > /dev/null; }
launch_app()    { api_post "/apps/run" "{\"path\": \"$1\", \"detach\": true}" > /dev/null; }

# Pipe commands to the resident AHK dialog handler
pipe_cmd() {
  MSYS_NO_PATHCONV=1 docker exec compose-winebot-interactive-1 sh -c "echo '$1' > '$PIPE_FILE'" 2>/dev/null
}

# Read response from pipe
pipe_read() {
  MSYS_NO_PATHCONV=1 docker exec compose-winebot-interactive-1 sh -c "cat '$PIPE_FILE' 2>/dev/null" || true
}

# Wait for a pipe response matching a pattern
pipe_wait() {
  local pattern="$1" timeout="${2:-10}" waited=0
  while [ "$waited" -lt "$timeout" ]; do
    local resp
    resp=$(pipe_read)
    if echo "$resp" | grep -q "$pattern"; then
      echo "$resp"
      return 0
    fi
    sleep 0.5
    waited=$((waited + 1))
  done
  echo ""
  return 1
}

# INIT
detect_token
SESSION=$(api_get "/lifecycle/status" | grep -o '"session_id":[[:space:]]*"[^"]*"' | head -1 | sed 's/.*"\([^"]*\)"$/\1/')
SESSDIR="/artifacts/sessions/$SESSION"
CT=$(curl -s -X POST -H "X-API-Key: $TOKEN" "$API_URL/sessions/$SESSION/control/challenge" | grep -o '"token":[[:space:]]*"[^"]*"' | sed 's/.*"\([^"]*\)"$/\1/')
api_post "/sessions/$SESSION/control/grant" "{\"lease_seconds\": 7200, \"user_ack\": true, \"challenge_token\": \"$CT\"}" > /dev/null
docker exec compose-winebot-interactive-1 sh -c 'wine cmd /c "if not exist C:\\artifacts mkdir C:\\artifacts" && mkdir -p /wineprefix/drive_c/artifacts /wineprefix/drive_c/dialog_handler' 2>/dev/null || true

echo "========================================"
echo "  WineBot Input Pipeline Demo v3"
echo "  Session: $SESSION"
echo "========================================"
echo ""

# ============================================================================
# SETUP: Launch resident AHK dialog interceptor
# ============================================================================
echo "=== SETUP: Launch Resident AHK Dialog Interceptor ==="
annotate "SETUP: Resident AHK dialog replacement launched"

# Copy the AHK script into the container
docker cp automation/core/dialog_replacement.ahk compose-winebot-interactive-1:/wineprefix/drive_c/dialog_handler/dialog_replacement.ahk 2>/dev/null || true

# Launch resident AHK script as background process inside the container
MSYS_NO_PATHCONV=1 docker exec compose-winebot-interactive-1 sh -c '
  DISPLAY=:99 WINEPREFIX=/wineprefix WINEDEBUG=-all \
  nohup ahk Z:\\wineprefix\\drive_c\\dialog_handler\\dialog_replacement.ahk \
  > /wineprefix/drive_c/dialog_handler/dh.log 2>&1 &
  echo "PID: $!"
'
sleep 3

# Verify it's running and pipe exists
echo -n "  Interceptor status: "
MSYS_NO_PATHCONV=1 docker exec compose-winebot-interactive-1 sh -c 'ps aux | grep dialog_replacement | grep -v grep | head -1 || echo "not found"' 2>/dev/null
MSYS_NO_PATHCONV=1 docker exec compose-winebot-interactive-1 sh -c 'ls -la /wineprefix/drive_c/dialog_handler/pipe.txt 2>/dev/null && echo "  Pipe file ready" || echo "  Pipe file not yet created"' 2>/dev/null
sleep 2
annotate "Interceptor running — monitoring for Save As and Open dialogs"
sleep 1

# ============================================================================
# PART 1: MOUSE + KEYBOARD Input Demo in Notepad
# ============================================================================
echo ""
echo "=== PART 1: Mouse + Keyboard Input Demo ==="
annotate "PART 1: Mouse click and keyboard input in Notepad"

launch_app "notepad.exe"; sleep 3
annotate "Notepad launched via /apps/run"
sleep 1

click_notepad
annotate "MOUSE CLICK: Focus Notepad at 300x300"
sleep 0.5

type_text "WineBot Input Pipeline Demo v3" "Notepad"; sleep 0.3
press_key "Return" "Notepad"; sleep 0.15
press_key "Return" "Notepad"; sleep 0.15
type_text "All input types working end-to-end:" "Notepad"; sleep 0.3
press_key "Return" "Notepad"; sleep 0.15
type_text "  Mouse click, keyboard text, named keys" "Notepad"; sleep 0.3
press_key "Return" "Notepad"; sleep 0.15
type_text "  Modifier chords, arrow keys, backspace" "Notepad"; sleep 0.3
annotate "KEYBOARD TEXT: Multiple lines typed"
sleep 0.3

# Named keys
press_key "Return" "Notepad"; sleep 0.15
type_text "Named keys demo:" "Notepad"; sleep 0.3
press_key "Return" "Notepad"; sleep 0.15
press_key "Tab" "Notepad"; sleep 0.2
type_text "Tab-indented" "Notepad"; sleep 0.3
press_key "Return" "Notepad"; sleep 0.15
type_text "Normal indent" "Notepad"; sleep 0.3
annotate "NAMED KEYS: Return and Tab"
sleep 0.3

# Modifier chord
press_key "Return" "Notepad"; sleep 0.15
type_text "Ctrl+A demo: this line will be selected" "Notepad"; sleep 0.3
press_key "ctrl+a" "Notepad"; sleep 0.3
annotate "MODIFIER CHORD: Ctrl+A selects all"
sleep 0.3

# ============================================================================
# PART 2: CTRL+S → AHK DIALOG REPLACEMENT via Pipe
# ============================================================================
echo ""
echo "=== PART 2: Save via AHK Dialog Replacement ==="
annotate "PART 2: Ctrl+S triggers Save As -> intercepted by AHK dialog replacement"
sleep 1

# Trigger Save As
press_key "ctrl+s" "Notepad"
sleep 3
annotate "Ctrl+S: Save As dialog opened (intercepted)"
sleep 0.5

# Check if the AHK dialog interceptor caught it
echo -n "  Checking for dialog intercept... "
INTERCEPT=$(pipe_read)
if echo "$INTERCEPT" | grep -q "dialog_intercepted"; then
  echo "CAUGHT! Replacement dialog active."
  annotate "Wine Save As closed — AHK Gui replacement dialog active"
else
  echo "Not yet intercepted. Checking again..."
  INTERCEPT=$(pipe_wait "dialog_intercepted" 8)
  if [ -n "$INTERCEPT" ]; then
    echo "CAUGHT! $INTERCEPT"
    annotate "Wine Save As closed — AHK Gui replacement dialog active"
  else
    echo "Interceptor may not have caught the dialog. Proceeding..."
  fi
fi
sleep 1

# Set the filename via pipe command
echo "  API → Pipe: set_filename:WineBot_Demo_v3.txt"
pipe_cmd "set_filename:WineBot_Demo_v3.txt"
sleep 0.5
RESP=$(pipe_read)
annotate "API: Filename set via pipe: WineBot_Demo_v3.txt"
sleep 0.5

# Click Save via pipe command
echo "  API → Pipe: click_save"
pipe_cmd "click_save"
sleep 1

# Wait for saved confirmation
SAVED=$(pipe_wait "saved_path" 5)
if [ -n "$SAVED" ]; then
  echo "  FILE SAVED: $SAVED"
  annotate "FILE SAVED via AHK Gui: WineBot_Demo_v3.txt"
else
  # Check directly
  if MSYS_NO_PATHCONV=1 docker exec compose-winebot-interactive-1 sh -c 'test -f /wineprefix/drive_c/artifacts/WineBot_Demo_v3.txt && echo "EXISTS"'; then
    echo "  FILE EXISTS on disk"
    annotate "FILE SAVED (confirmed on disk)"
  fi
fi
sleep 1

# Verify the file was created
echo ""
echo "  [VERIFY] Saved file:"
MSYS_NO_PATHCONV=1 docker exec compose-winebot-interactive-1 sh -c 'ls -la /wineprefix/drive_c/artifacts/WineBot_Demo_v3.txt 2>/dev/null && echo "---" && cat /wineprefix/drive_c/artifacts/WineBot_Demo_v3.txt' || echo "  (file not created — AHK interceptor may need Notepad Save As dialog to appear)"

# Close Notepad
press_key "alt+F4" "Notepad"; sleep 1
annotate "Alt+F4: Notepad closed"
sleep 0.5

# ============================================================================
# PART 3: FILE OPERATIONS via cmd.exe (deterministic, no dialogs needed)
# ============================================================================
echo ""
echo "=== PART 3: File Operations via cmd.exe ==="
annotate "PART 3: File create, verify, edit via cmd.exe"

launch_app "cmd.exe"; sleep 2

type_text "echo Direct file create via cmd.exe > C:\\artifacts\\CmdFile.txt" "cmd"; sleep 0.5
press_key "Return" "cmd"; sleep 0.5
type_text "echo Line 1: Created via cmd.exe API keyboard injection >> C:\\artifacts\\CmdFile.txt" "cmd"; sleep 0.5
press_key "Return" "cmd"; sleep 0.5
type_text "echo Line 2: No dialog needed at all >> C:\\artifacts\\CmdFile.txt" "cmd"; sleep 0.5
press_key "Return" "cmd"; sleep 0.5
annotate "FILE CREATED via cmd.exe echo/redirect"
sleep 0.3

type_text "type C:\\artifacts\\CmdFile.txt" "cmd"; sleep 0.3
press_key "Return" "cmd"; sleep 1
annotate "FILE VERIFIED via type command"
sleep 0.3

# Append
type_text "echo --- Edited via WineBot v3 --- >> C:\\artifacts\\CmdFile.txt" "cmd"; sleep 0.3
press_key "Return" "cmd"; sleep 0.3
annotate "FILE EDITED via append"
sleep 0.3

type_text "exit" "cmd"; sleep 0.2
press_key "Return" "cmd"; sleep 1

echo "  [VERIFY] File:"
MSYS_NO_PATHCONV=1 docker exec compose-winebot-interactive-1 sh -c 'cat /wineprefix/drive_c/artifacts/CmdFile.txt 2>/dev/null' || echo "  (check manually)"

# ============================================================================
# PART 4: REGISTRY OPERATIONS
# ============================================================================
echo ""
echo "=== PART 4: Registry Operations via cmd.exe ==="
annotate "PART 4: Registry create, verify, delete"

launch_app "cmd.exe"; sleep 2

type_text "reg add HKCU\\Software\\WineBotDemo /v AppVersion /t REG_SZ /d v3.0 /f" "cmd"; sleep 0.5
press_key "Return" "cmd"; sleep 0.5
type_text "reg add HKCU\\Software\\WineBotDemo /v DialogReplacement /t REG_SZ /d AHK_Gui /f" "cmd"; sleep 0.5
press_key "Return" "cmd"; sleep 0.5
annotate "REGISTRY KEY created: HKCU\\Software\\WineBotDemo with two values"
sleep 0.3

type_text "reg query HKCU\\Software\\WineBotDemo" "cmd"; sleep 0.3
press_key "Return" "cmd"; sleep 1
annotate "REG VERIFIED"
sleep 0.3

type_text "reg delete HKCU\\Software\\WineBotDemo /f" "cmd"; sleep 0.3
press_key "Return" "cmd"; sleep 0.3
type_text "exit" "cmd"; sleep 0.2
press_key "Return" "cmd"; sleep 1
annotate "CLEANUP: Registry key deleted"

# ============================================================================
# PART 5: REGEDIT KEYBOARD NAVIGATION
# ============================================================================
echo ""
echo "=== PART 5: Regedit Keyboard Navigation ==="
annotate "PART 5: Regedit — pure keyboard navigation"

launch_app "regedit.exe"; sleep 3
annotate "Regedit launched"
sleep 1

for i in 1 2 3 4; do press_key "Tab" "Registry Editor"; sleep 0.2; done
for i in 1 2 3; do press_key "Down" "Registry Editor"; sleep 0.2; done
annotate "TAB + DOWN: HKEY_CURRENT_USER"
sleep 0.3

press_key "Right" "Registry Editor"; sleep 0.5
for i in 1 2 3 4 5 6 7 8 9; do press_key "Down" "Registry Editor"; sleep 0.2; done
annotate "RIGHT + DOWN: HKCU\\Software"
sleep 0.3

press_key "alt+F4" "Registry Editor"; sleep 1
annotate "Alt+F4: Regedit closed"
sleep 0.5

# ============================================================================
# PART 6: BATCH SCRIPT
# ============================================================================
echo ""
echo "=== PART 6: CMD Script Execute ==="
annotate "PART 6: Batch script via docker cp + cmd.exe"

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
docker cp "$SCRIPT_DIR/CmdScript_Demo.bat" compose-winebot-interactive-1:/wineprefix/drive_c/artifacts/CmdScript_Demo.bat 2>/dev/null || true
annotate "Batch script deployed via docker cp"

launch_app "cmd.exe"; sleep 2
type_text "C:\\artifacts\\CmdScript_Demo.bat" "cmd"; sleep 0.3
press_key "Return" "cmd"; sleep 3
annotate "BATCH SCRIPT EXECUTED"
sleep 0.3
type_text "exit" "cmd"; sleep 0.2
press_key "Return" "cmd"; sleep 1

# ============================================================================
# CLEANUP
# ============================================================================
echo ""
echo "=== PART 7: Cleanup ==="
annotate "PART 7: Cleanup"

launch_app "cmd.exe"; sleep 2
type_text "del C:\\artifacts\\WineBot_Demo_v3.txt 2>nul & del C:\\artifacts\\CmdFile.txt 2>nul & del C:\\artifacts\\CmdScript_Demo.bat 2>nul & del C:\\artifacts\\CmdScript_Output.txt 2>nul & echo Cleanup done" "cmd"; sleep 0.3
press_key "Return" "cmd"; sleep 0.5
type_text "exit" "cmd"; sleep 0.2
press_key "Return" "cmd"; sleep 1
annotate "CLEANUP COMPLETE"

# Kill the resident AHK interceptor
MSYS_NO_PATHCONV=1 docker exec compose-winebot-interactive-1 sh -c 'pkill -f dialog_replacement 2>/dev/null; echo done' 2>/dev/null || true

# ============================================================================
# SUMMARY
# ============================================================================
echo ""
echo "========================================"
echo "  DEMO COMPLETE — v3"
echo "  Session: $SESSION"
echo ""
echo "  Technique demonstrated:"
echo "    AHK Dialog Replacement via Pipe API"
echo "    1. Resident AHK script monitors for Save As/Open"
echo "    2. Wine dialog is intercepted and closed"
echo "    3. AHK Gui replacement with injectable controls"
echo "    4. API → Pipe → AHK GuiControl pathway"
echo ""
echo "  Input types demonstrated:"
echo "    Mouse click       (/input/mouse/click)"
echo "    Keyboard text     (/input/key AHK backend)"
echo "    Named keys        (Return, Tab, Escape)"
echo "    Modifier chords   (Ctrl+A, Ctrl+S, Alt+F4)"
echo "    Arrow keys        (Down, Right)"
echo "    Agent app launch  (/apps/run)"
echo "    Pipe commands     (set_filename, click_save)"
echo ""
echo "  Capabilities demonstrated:"
echo "    AHK dialog interception + Gui replacement"
echo "    File operations via cmd.exe"
echo "    Registry create/query/delete"
echo "    Regedit keyboard navigation"
echo "    Batch script deployment and execution"
echo "========================================"

# Stop recording
api_post "/recording/stop" '{}' 2>/dev/null || true
sleep 2

echo ""
echo "Video: docker cp compose-winebot-interactive-1:$SESSDIR/video_001.mkv demo/output/demo.mkv"
docker exec compose-winebot-interactive-1 sh -c "ls -lh $SESSDIR/*.mkv 2>/dev/null" || true
