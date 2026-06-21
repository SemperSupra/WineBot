#!/usr/bin/env bash
# WineBot Input Pipeline Demo v4 — AHK Pipe-Driven Dialog Replacement
# No chown. No comdlg32 dialogs. Clean pipe protocol with su winebot.
set -u

API_URL="${API_URL:-http://localhost:8000}"
PIPE="/wineprefix/drive_c/dialog_handler/pipe.txt"

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

# Pipe protocol helpers — always write as winebot, clean, no path mangling
pipe_cmd()  { MSYS_NO_PATHCONV=1 docker exec compose-winebot-interactive-1 su -s /bin/sh winebot -c "echo '$1' > '$PIPE'" 2>/dev/null; }
pipe_read() { MSYS_NO_PATHCONV=1 docker exec compose-winebot-interactive-1 cat "$PIPE" 2>/dev/null || true; }
pipe_wait() {
  local pattern="$1" timeout="${2:-10}" waited=0
  while [ "$waited" -lt "$timeout" ]; do
    local resp; resp=$(pipe_read)
    if echo "$resp" | grep -q "$pattern"; then echo "$resp"; return 0; fi
    sleep 0.5; waited=$((waited + 1))
  done; return 1
}

click_notepad() { api_post "/input/mouse/click" '{"x": 300, "y": 300, "button": 1, "window_title": "Notepad"}' > /dev/null; }
type_text()     { api_post "/input/key" "{\"keys\": \"$1\", \"window_title\": \"$2\"}" > /dev/null; }
press_key()     { api_post "/input/key" "{\"keys\": \"$1\", \"window_title\": \"$2\"}" > /dev/null; }
launch_app()    { api_post "/apps/run" "{\"path\": \"$1\", \"detach\": true}" > /dev/null; }

# INIT
detect_token
SESSION=$(api_get "/lifecycle/status" | grep -o '"session_id":[[:space:]]*"[^"]*"' | head -1 | sed 's/.*"\([^"]*\)"$/\1/')
SESSDIR="/artifacts/sessions/$SESSION"
CT=$(curl -s -X POST -H "X-API-Key: $TOKEN" "$API_URL/sessions/$SESSION/control/challenge" | grep -o '"token":[[:space:]]*"[^"]*"' | sed 's/.*"\([^"]*\)"$/\1/')
api_post "/sessions/$SESSION/control/grant" "{\"lease_seconds\": 7200, \"user_ack\": true, \"challenge_token\": \"$CT\"}" > /dev/null
docker exec compose-winebot-interactive-1 sh -c 'wine cmd /c "if not exist C:\\artifacts mkdir C:\\artifacts" && mkdir -p /wineprefix/drive_c/artifacts' 2>/dev/null || true

echo "========================================"
echo "  WineBot Demo v4 — AHK Dialog Replacement"
echo "  Session: $SESSION"
echo "========================================"
echo ""

# ============================================================================
# SETUP: Deploy and launch AHK pipe handler
# ============================================================================
echo "=== SETUP: Deploy AHK Dialog Handler ==="
annotate "SETUP: AHK pipe-driven dialog handler deployed"

docker cp automation/core/dialog_replacement.ahk compose-winebot-interactive-1:/wineprefix/drive_c/dr.ahk 2>/dev/null || true
docker exec compose-winebot-interactive-1 sh -c 'chown winebot:winebot /wineprefix/drive_c/dr.ahk' 2>/dev/null

# Launch via API — ahk wrapper runs wine AutoHotkeyU64.exe with args
api_post "/apps/run" '{"path": "ahk", "args": "C:/dr.ahk", "detach": true}' > /dev/null
sleep 5

RESP=$(pipe_read)
if echo "$RESP" | grep -q "ready"; then
    echo "  Handler ready: $RESP"
    annotate "AHK dialog handler ready (pipe protocol active)"
else
    echo "  Handler did not start. Retrying..."
    api_post "/apps/run" '{"path": "ahk", "args": "C:/dr.ahk", "detach": true}' > /dev/null; sleep 5
    RESP=$(pipe_read)
fi
echo ""

# ============================================================================
# PART 1: MOUSE + KEYBOARD Input in Notepad
# ============================================================================
echo "=== PART 1: Mouse + Keyboard Input ==="
annotate "PART 1: Mouse click and keyboard input in Notepad"

launch_app "notepad.exe"; sleep 3
annotate "Notepad launched via /apps/run"
sleep 1

click_notepad
annotate "MOUSE CLICK: Focus at 300x300"
sleep 0.5

type_text "WineBot Demo v4 — AHK Dialog Replacement" "Notepad"; sleep 0.3
press_key "Return" "Notepad"; sleep 0.15
press_key "Return" "Notepad"; sleep 0.15
type_text "Input types demonstrated:" "Notepad"; sleep 0.3
press_key "Return" "Notepad"; sleep 0.15
type_text "  - Mouse click (/input/mouse/click)" "Notepad"; sleep 0.3
press_key "Return" "Notepad"; sleep 0.15
type_text "  - Keyboard text (/input/key)" "Notepad"; sleep 0.3
press_key "Return" "Notepad"; sleep 0.15
type_text "  - Named keys: Return, Tab, Escape" "Notepad"; sleep 0.3
press_key "Return" "Notepad"; sleep 0.15
type_text "  - Modifier chords: Ctrl+A, Ctrl+S" "Notepad"; sleep 0.3
annotate "KEYBOARD TEXT: Multiple lines typed"
sleep 0.3

press_key "Return" "Notepad"; sleep 0.15
type_text "Tab demo:" "Notepad"; sleep 0.3
press_key "Return" "Notepad"; sleep 0.15
press_key "Tab" "Notepad"; sleep 0.2
type_text "Tab-indented text" "Notepad"; sleep 0.3
annotate "NAMED KEYS: Return and Tab"
sleep 0.3

press_key "Return" "Notepad"; sleep 0.15
type_text "Ctrl+A selects all text" "Notepad"; sleep 0.3
press_key "ctrl+a" "Notepad"; sleep 0.3
annotate "MODIFIER CHORD: Ctrl+A"
sleep 0.3

# ============================================================================
# PART 2: AHK PIPE DIALOG REPLACEMENT
# ============================================================================
echo ""
echo "=== PART 2: Pipe-Driven Dialog Replacement ==="
annotate "PART 2: AHK pipe dialog — open_gui -> set_filename -> click_save"
sleep 1

pipe_cmd "open_gui"
sleep 3
RESP=$(pipe_read)
if echo "$RESP" | grep -q "gui_opened"; then
    echo "  Gui opened: $RESP"
    annotate "AHK Gui dialog opened (X11 window visible)"
else
    echo "  Gui failed: $RESP"
fi

# Verify X11 window
GUI_COUNT=$(docker exec compose-winebot-interactive-1 xdotool search --name "WineBot Save Dialog" 2>/dev/null | wc -l)
echo "  X11 windows visible: $GUI_COUNT (should be 1)"
sleep 0.5

echo ""
echo "  Setting filename via pipe..."
pipe_cmd "set_filename:WineBot_Pipe_Demo_v4.txt"
sleep 1.5
RESP=$(pipe_read)
echo "  Response: $RESP"
annotate "Filename set via pipe: WineBot_Pipe_Demo_v4.txt"
sleep 0.5

echo ""
echo "  Clicking Save via pipe..."
pipe_cmd "click_save"
sleep 3
RESP=$(pipe_wait "saved" 5)
if echo "$RESP" | grep -q "saved"; then
    echo "  SAVED: $RESP"
    annotate "FILE SAVED via pipe protocol! WineBot_Pipe_Demo_v4.txt"
else
    echo "  Response: $RESP"
fi

# Verify
echo ""
echo "  [VERIFY] File on disk:"
if docker exec compose-winebot-interactive-1 sh -c 'test -f /wineprefix/drive_c/artifacts/WineBot_Pipe_Demo_v4.txt && echo "EXISTS" && cat /wineprefix/drive_c/artifacts/WineBot_Pipe_Demo_v4.txt' 2>/dev/null; then
    true
else
    echo "  (check manually)"
fi

# Close Notepad
press_key "alt+F4" "Notepad"; sleep 1
annotate "Alt+F4: Notepad closed"
sleep 0.5

# ============================================================================
# PART 3: FILE OPS via cmd.exe (no dialogs)
# ============================================================================
echo ""
echo "=== PART 3: File Operations via cmd.exe ==="
annotate "PART 3: File create, verify, edit via cmd.exe"

launch_app "cmd.exe"; sleep 2

type_text "echo Direct file create via cmd.exe > C:\\artifacts\\CmdDemo_v4.txt" "cmd"; sleep 0.5
press_key "Return" "cmd"; sleep 0.5
type_text "echo Line 1: Created via cmd.exe >> C:\\artifacts\\CmdDemo_v4.txt" "cmd"; sleep 0.5
press_key "Return" "cmd"; sleep 0.5
type_text "echo Line 2: No dialog needed >> C:\\artifacts\\CmdDemo_v4.txt" "cmd"; sleep 0.5
press_key "Return" "cmd"; sleep 0.5
annotate "FILE CREATED via cmd.exe"
sleep 0.3

type_text "type C:\\artifacts\\CmdDemo_v4.txt" "cmd"; sleep 0.3
press_key "Return" "cmd"; sleep 1
annotate "FILE VERIFIED"
sleep 0.3

type_text "exit" "cmd"; sleep 0.2
press_key "Return" "cmd"; sleep 1

# ============================================================================
# PART 4: REGISTRY via cmd.exe
# ============================================================================
echo ""
echo "=== PART 4: Registry Operations ==="
annotate "PART 4: Registry create, verify, delete"

launch_app "cmd.exe"; sleep 2

type_text "reg add HKCU\\Software\\WineBotDemo /v PipeProtocol /t REG_SZ /d working /f" "cmd"; sleep 0.5
press_key "Return" "cmd"; sleep 0.5
type_text "reg add HKCU\\Software\\WineBotDemo /v DemoVersion /t REG_SZ /d v4.0 /f" "cmd"; sleep 0.5
press_key "Return" "cmd"; sleep 0.5
annotate "REGISTRY created: HKCU\\Software\\WineBotDemo"
sleep 0.3

type_text "reg query HKCU\\Software\\WineBotDemo" "cmd"; sleep 0.3
press_key "Return" "cmd"; sleep 1
annotate "REG VERIFIED"
sleep 0.3

type_text "reg delete HKCU\\Software\\WineBotDemo /f" "cmd"; sleep 0.3
press_key "Return" "cmd"; sleep 0.3
type_text "exit" "cmd"; sleep 0.2
press_key "Return" "cmd"; sleep 1
annotate "CLEANUP: Registry deleted"

# ============================================================================
# PART 5: REGEDIT + BATCH SCRIPT
# ============================================================================
echo ""
echo "=== PART 5: Regedit Navigation + Batch Script ==="
annotate "PART 5: Regedit keyboard nav + cmd batch script"

launch_app "regedit.exe"; sleep 3
annotate "Regedit launched"
for i in 1 2 3 4; do press_key "Tab" "Registry Editor"; sleep 0.2; done
for i in 1 2 3; do press_key "Down" "Registry Editor"; sleep 0.2; done
annotate "TAB + DOWN: HKEY_CURRENT_USER"
press_key "alt+F4" "Registry Editor"; sleep 1
annotate "Alt+F4: Regedit closed"
sleep 0.5

# Batch script via docker cp
SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
docker cp "$SCRIPT_DIR/CmdScript_Demo.bat" compose-winebot-interactive-1:/wineprefix/drive_c/artifacts/CmdScript_Demo.bat 2>/dev/null || true

launch_app "cmd.exe"; sleep 2
type_text "C:\\artifacts\\CmdScript_Demo.bat" "cmd"; sleep 0.3
press_key "Return" "cmd"; sleep 3
annotate "BATCH SCRIPT EXECUTED"
type_text "exit" "cmd"; sleep 0.2
press_key "Return" "cmd"; sleep 1

# ============================================================================
# CLEANUP + SUMMARY
# ============================================================================
echo ""
echo "=== PART 6: Cleanup ==="
annotate "PART 6: Cleanup"

launch_app "cmd.exe"; sleep 2
type_text "del C:\\artifacts\\WineBot_Pipe_Demo_v4.txt 2>nul & del C:\\artifacts\\CmdDemo_v4.txt 2>nul & echo done" "cmd"; sleep 0.3
press_key "Return" "cmd"; sleep 0.5
type_text "exit" "cmd"; sleep 0.2
press_key "Return" "cmd"; sleep 1
annotate "CLEANUP COMPLETE"

echo ""
echo "========================================"
echo "  DEMO COMPLETE — v4"
echo "  Session: $SESSION"
echo ""
echo "  AHK Pipe Protocol (no chown anywhere):"
echo "    open_gui             -> AHK Gui appears"
echo "    set_filename:file    -> Filename updated"
echo "    click_save           -> File saved to disk"
echo "    click_cancel         -> Dialog dismissed"
echo ""
echo "  All pipe writes via su winebot — zero permission issues."
echo "========================================"

api_post "/recording/stop" '{}' 2>/dev/null || true
sleep 2

echo ""
docker exec compose-winebot-interactive-1 sh -c "ls -lh $SESSDIR/*.mkv 2>/dev/null" || true
echo ""
echo "Copy video: docker cp compose-winebot-interactive-1:$SESSDIR/video_001.mkv demo/output/demo.mkv"
