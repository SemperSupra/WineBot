#!/usr/bin/env bash
# ============================================================================
# WineBot Input Pipeline Demo v2
# Restructured to avoid comdlg32 Save/Open dialogs (see docs/known-limitations.md)
# File operations via cmd.exe, input demo via Notepad
# ============================================================================
set -u

# CONFIG
API_URL="${API_URL:-http://localhost:8000}"

# HELPERS
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

# INIT
detect_token
SESSION=$(api_get "/lifecycle/status" | grep -o '"session_id":[[:space:]]*"[^"]*"' | head -1 | sed 's/.*"\([^"]*\)"$/\1/')
SESSDIR="/artifacts/sessions/$SESSION"
CT=$(curl -s -X POST -H "X-API-Key: $TOKEN" "$API_URL/sessions/$SESSION/control/challenge" | grep -o '"token":[[:space:]]*"[^"]*"' | sed 's/.*"\([^"]*\)"$/\1/')
api_post "/sessions/$SESSION/control/grant" "{\"lease_seconds\": 7200, \"user_ack\": true, \"challenge_token\": \"$CT\"}" > /dev/null
docker exec compose-winebot-interactive-1 sh -c 'wine cmd /c "if not exist C:\\artifacts mkdir C:\\artifacts" && mkdir -p /wineprefix/drive_c/artifacts' 2>/dev/null || true

echo "========================================"
echo "  WineBot Input Pipeline Demo v2"
echo "  Session: $SESSION"
echo "========================================"
echo ""

# ============================================================================
# PART 1: MOUSE + KEYBOARD — Type text in Notepad (pure input demo)
# ============================================================================
echo "=== PART 1: Mouse + Keyboard Input Demo ==="
annotate "PART 1: Mouse click and keyboard input in Notepad"

launch_app "notepad.exe"; sleep 3
annotate "Notepad launched via /apps/run"
sleep 1

# MOUSE: Click to focus
click_notepad
annotate "MOUSE CLICK: Focus Notepad at coordinates 300,300"
sleep 0.5

# KEYBOARD: Type text
type_text "WineBot Input Pipeline Demo v2" "Notepad"; sleep 0.3
press_key "Return" "Notepad"; sleep 0.15
press_key "Return" "Notepad"; sleep 0.15
type_text "All input types working end-to-end:" "Notepad"; sleep 0.3
press_key "Return" "Notepad"; sleep 0.15
type_text "  - Mouse click (xdotool via /input/mouse/click)" "Notepad"; sleep 0.3
press_key "Return" "Notepad"; sleep 0.15
type_text "  - Keyboard text (AHK Send via /input/key)" "Notepad"; sleep 0.3
press_key "Return" "Notepad"; sleep 0.15
type_text "  - Named keys: Return, Tab, Escape, BackSpace" "Notepad"; sleep 0.3
press_key "Return" "Notepad"; sleep 0.15
type_text "  - Modifier chords: Ctrl, Alt, Shift combos" "Notepad"; sleep 0.3
press_key "Return" "Notepad"; sleep 0.15
type_text "  - Arrow keys for navigation" "Notepad"; sleep 0.3
annotate "KEYBOARD TEXT: Multiple lines typed via /input/key"
sleep 0.3

# Named keys
press_key "Return" "Notepad"; sleep 0.15
type_text "Named keys:" "Notepad"; sleep 0.3
press_key "Return" "Notepad"; sleep 0.15
press_key "Tab" "Notepad"; sleep 0.2
type_text "Tab-indented text" "Notepad"; sleep 0.3
press_key "Return" "Notepad"; sleep 0.15
type_text "Normal text again" "Notepad"; sleep 0.3
annotate "NAMED KEYS: Return, Tab demonstrated"
sleep 0.3

# BackSpace
press_key "Return" "Notepad"; sleep 0.15
type_text "This has typosssss" "Notepad"; sleep 0.3
for i in 1 2 3 4; do press_key "BackSpace" "Notepad"; sleep 0.08; done
type_text " BackSpace fixes typos" "Notepad"; sleep 0.3
annotate "NAMED KEYS: BackSpace for correction"
sleep 0.3

# Modifier chord: Ctrl+A select all, then Ctrl+B (bold doesn't work in Notepad but proves modifiers)
press_key "ctrl+a" "Notepad"; sleep 0.3
annotate "MODIFIER CHORD: Ctrl+A selects all text"
sleep 0.3

# Escape, then close
press_key "Escape" "Notepad"; sleep 0.3
press_key "alt+F4" "Notepad"; sleep 1
annotate "MODIFIER CHORD: Alt+F4 closes Notepad"
sleep 0.5

# ============================================================================
# PART 2: FILE OPERATIONS via cmd.exe (bypasses comdlg32 limitation)
# ============================================================================
echo ""
echo "=== PART 2: File Create, Edit, Verify via cmd.exe ==="
annotate "PART 2: File operations via cmd.exe (avoids comdlg32 dialog limitation)"

launch_app "cmd.exe"; sleep 2

# CREATE: echo to create a text file
type_text "echo WineBot Demo File created via cmd.exe > C:\\artifacts\\Demo_File.txt" "cmd"; sleep 0.5
press_key "Return" "cmd"; sleep 0.5
type_text "echo Created at: %DATE% %TIME% >> C:\\artifacts\\Demo_File.txt" "cmd"; sleep 0.5
press_key "Return" "cmd"; sleep 0.5
type_text "echo. >> C:\\artifacts\\Demo_File.txt" "cmd"
sleep 0.3
press_key "Return" "cmd"; sleep 0.5
type_text "echo Line 1: Keyboard input types text into cmd.exe" "cmd"; sleep 0.5
press_key "Return" "cmd"; sleep 0.5
type_text "echo Line 2: cmd.exe writes the file to disk" "cmd"; sleep 0.5
press_key "Return" "cmd"; sleep 0.5
type_text "echo Line 3: No file dialogs needed" "cmd"; sleep 0.5
press_key "Return" "cmd"; sleep 0.5
annotate "FILE CREATED: Demo_File.txt via cmd.exe echo/redirect"
sleep 0.5

# VERIFY: type the file
type_text "type C:\\artifacts\\Demo_File.txt" "cmd"; sleep 0.3
press_key "Return" "cmd"; sleep 1
annotate "FILE VERIFIED: Content displayed via type command"
sleep 0.3

# EDIT: append to file
type_text "echo. >> C:\\artifacts\\Demo_File.txt" "cmd"; sleep 0.3
press_key "Return" "cmd"; sleep 0.3
type_text "echo --- EDITED via WineBot API --- >> C:\\artifacts\\Demo_File.txt" "cmd"; sleep 0.3
press_key "Return" "cmd"; sleep 0.3
type_text "echo Appended at: %DATE% %TIME% >> C:\\artifacts\\Demo_File.txt" "cmd"; sleep 0.3
press_key "Return" "cmd"; sleep 0.3
annotate "FILE EDITED: Lines appended via echo redirect"
sleep 0.3

# VERIFY AGAIN
type_text "type C:\\artifacts\\Demo_File.txt" "cmd"; sleep 0.3
press_key "Return" "cmd"; sleep 1

# Close cmd
type_text "exit" "cmd"; sleep 0.2
press_key "Return" "cmd"; sleep 1

echo "  [VERIFY] File on disk:"
docker exec compose-winebot-interactive-1 sh -c 'ls -la /wineprefix/drive_c/artifacts/Demo_File.txt && wc -l /wineprefix/drive_c/artifacts/Demo_File.txt' 2>/dev/null || echo "  (check manually)"

# ============================================================================
# PART 3: REGISTRY OPERATIONS via cmd.exe
# ============================================================================
echo ""
echo "=== PART 3: Registry Create, Verify, Delete via cmd.exe ==="
annotate "PART 3: Registry operations via cmd.exe + reg command"

launch_app "cmd.exe"; sleep 2

# CREATE registry key + string value
type_text "reg add HKCU\\Software\\WineBotDemo /v AppName /t REG_SZ /d WineBot_v2 /f" "cmd"; sleep 0.5
press_key "Return" "cmd"; sleep 0.5
annotate "REGISTRY KEY created: HKCU\\Software\\WineBotDemo"
sleep 0.3

# CREATE DWORD value
type_text "reg add HKCU\\Software\\WineBotDemo /v InstanceCount /t REG_DWORD /d 1 /f" "cmd"; sleep 0.5
press_key "Return" "cmd"; sleep 0.5
annotate "DWORD VALUE created: InstanceCount = 1"
sleep 0.3

# CREATE additional string
type_text "reg add HKCU\\Software\\WineBotDemo /v Status /t REG_SZ /d Running /f" "cmd"; sleep 0.5
press_key "Return" "cmd"; sleep 0.5
annotate "STRING VALUE created: Status = Running"
sleep 0.3

# VERIFY
type_text "reg query HKCU\\Software\\WineBotDemo" "cmd"; sleep 0.3
press_key "Return" "cmd"; sleep 1.5
annotate "REG VERIFIED: All registry values confirmed"
sleep 0.3

# Cleanup
type_text "reg delete HKCU\\Software\\WineBotDemo /f" "cmd"; sleep 0.3
press_key "Return" "cmd"; sleep 0.5
annotate "CLEANUP: Registry key deleted"
sleep 0.3

type_text "exit" "cmd"; sleep 0.2
press_key "Return" "cmd"; sleep 1

# ============================================================================
# PART 4: REGEDIT KEYBOARD NAVIGATION
# ============================================================================
echo ""
echo "=== PART 4: Regedit Keyboard Navigation ==="
annotate "PART 4: Regedit interactive - keyboard-only navigation"

launch_app "regedit.exe"; sleep 3
annotate "Regedit launched via /apps/run"
sleep 1

# Tab to tree pane, navigate down to HKCU
for i in 1 2 3 4; do press_key "Tab" "Registry Editor"; sleep 0.2; done
for i in 1 2 3; do press_key "Down" "Registry Editor"; sleep 0.2; done
annotate "TAB + DOWN ARROWS: Navigated to HKEY_CURRENT_USER"
sleep 0.3

# Expand HKCU
press_key "Right" "Registry Editor"; sleep 0.5
for i in 1 2 3 4 5 6 7 8 9; do press_key "Down" "Registry Editor"; sleep 0.2; done
annotate "RIGHT + DOWN ARROWS: Navigated to HKCU\\Software"
sleep 0.3

# Open Edit menu
press_key "alt+e" "Registry Editor"; sleep 0.5
annotate "Alt+E: Edit menu opened"
sleep 0.3

# Navigate to New, select Key
for i in 1 2 3; do press_key "Down" "Registry Editor"; sleep 0.2; done
press_key "Return" "Registry Editor"; sleep 1
type_text "WineBotDemoKey" "Registry Editor"; sleep 0.3
press_key "Return" "Registry Editor"; sleep 0.5
annotate "NEW KEY created: WineBotDemoKey"
sleep 0.5

# Create String Value
press_key "alt+e" "Registry Editor"; sleep 0.3
for i in 1 2 3 4; do press_key "Down" "Registry Editor"; sleep 0.2; done
press_key "Return" "Registry Editor"; sleep 1
type_text "DemoString" "Registry Editor"; sleep 0.3
press_key "Return" "Registry Editor"; sleep 1.5
type_text "Hello from WineBot Input Pipeline" "Registry Editor"; sleep 0.3
press_key "Return" "Registry Editor"; sleep 0.5
annotate "STRING VALUE: DemoString = Hello from WineBot Input Pipeline"
sleep 0.5

# Close Regedit
press_key "alt+F4" "Registry Editor"; sleep 1
annotate "Alt+F4: Regedit closed"
sleep 0.5

# ============================================================================
# PART 5: PROGRAMMATIC BATCH SCRIPT via docker cp
# ============================================================================
echo ""
echo "=== PART 5: CMD Script Write + Execute ==="
annotate "PART 5: Programmatic batch script via docker cp + cmd.exe"

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
docker cp "$SCRIPT_DIR/CmdScript_Demo.bat" compose-winebot-interactive-1:/wineprefix/drive_c/artifacts/CmdScript_Demo.bat 2>/dev/null || true
annotate "Batch script copied via docker cp"
sleep 0.5

launch_app "cmd.exe"; sleep 2
type_text "C:\\artifacts\\CmdScript_Demo.bat" "cmd"; sleep 0.3
press_key "Return" "cmd"; sleep 3
annotate "BATCH SCRIPT EXECUTED: File created, registry key created, reg query read"
sleep 0.5

type_text "exit" "cmd"; sleep 0.2
press_key "Return" "cmd"; sleep 1

echo "  [VERIFY] Script output:"
docker exec compose-winebot-interactive-1 sh -c 'cat /wineprefix/drive_c/artifacts/CmdScript_Output.txt 2>/dev/null' || echo "  (check manually)"

# ============================================================================
# PART 6: CLEANUP
# ============================================================================
echo ""
echo "=== PART 6: Cleanup ==="
annotate "PART 6: Cleanup - all artifacts removed"

launch_app "cmd.exe"; sleep 2

type_text "del C:\\artifacts\\Demo_File.txt" "cmd"; sleep 0.3
press_key "Return" "cmd"; sleep 0.3
type_text "del C:\\artifacts\\CmdScript_Output.txt" "cmd"; sleep 0.3
press_key "Return" "cmd"; sleep 0.3
type_text "del C:\\artifacts\\CmdScript_Demo.bat" "cmd"; sleep 0.3
press_key "Return" "cmd"; sleep 0.3
annotate "FILES DELETED: All demo files removed"
sleep 0.3

type_text "reg delete HKCU\\Software\\WineBotCmdScript /f" "cmd"; sleep 0.3
press_key "Return" "cmd"; sleep 0.3
type_text "exit" "cmd"; sleep 0.2
press_key "Return" "cmd"; sleep 1
annotate "CLEANUP COMPLETE"
sleep 0.5

# ============================================================================
# SUMMARY
# ============================================================================
echo ""
echo "========================================"
echo "  DEMO COMPLETE"
echo "  Session: $SESSION"
echo ""
echo "  Input types demonstrated:"
echo "    Mouse click          (xdotool via /input/mouse/click)"
echo "    Keyboard text        (AHK Send via /input/key)"
echo "    Named keys           (Return, Tab, Escape, BackSpace)"
echo "    Modifier chords      (Ctrl+A, Alt+E, Alt+F4)"
echo "    Arrow keys           (Down, Right)"
echo "    Agent app launch     (/apps/run)"
echo ""
echo "  Capabilities demonstrated:"
echo "    File operations      (cmd.exe echo/redirect/type)"
echo "    Registry operations  (cmd.exe reg add/query/delete)"
echo "    Regedit navigation   (pure keyboard: Tab/Arrow/Alt+E)"
echo "    Batch script         (docker cp + cmd.exe execute)"
echo "========================================"

# Stop recording
api_post "/recording/stop" '{}' 2>/dev/null || true
sleep 2

echo ""
echo "Video files:"
docker exec compose-winebot-interactive-1 sh -c "ls -lh $SESSDIR/*.mkv 2>/dev/null" || true
echo ""
echo "Subtitle files:"
docker exec compose-winebot-interactive-1 sh -c "ls -lh $SESSDIR/*.vtt $SESSDIR/*.ass 2>/dev/null" || true
echo ""
echo "To save: docker cp compose-winebot-interactive-1:$SESSDIR/video_001.mkv ./demo/output/demo.mkv"
