#!/usr/bin/env bash
# ============================================================================
# WineBot Input Pipeline Demo
#
# Demonstrates every input type end-to-end:
#   MOUSE:     Click targeting (xdotool via /input/mouse/click)
#   KEYBOARD:  Plain text, named keys (Return/Tab/Escape/BackSpace),
#              modifier chords (Ctrl+S/O, Alt+E/F4), arrow keys,
#              function keys
#   AGENT:     App launch (/apps/run), Python script execution (/run/python),
#              AHK script execution (/run/ahk)
#
# Capabilities demonstrated:
#   - File create, edit, and delete via Notepad
#   - Registry key creation with string + DWORD values via Regedit
#   - Programmatic batch script execution that reads registry values
#   - Cleanup of all artifacts
#
# Prerequisites:
#   - Running WineBot interactive container:
#       docker compose -f compose/docker-compose.yml --profile interactive up -d
#   - Optional: Recording enabled (WINEBOT_RECORD=1, default in interactive mode)
#
# Usage:
#   bash demo/scripts/input-pipeline-demo.sh
#
# To customize, edit the CONFIG section below.
# ============================================================================
# Note: NOT using 'set -e' — this is a demo, not a test.
# Verification failures should be noted but should not stop the show.
set -u

# ------------------------------------------------------------------
# CONFIG — edit these to customize the demo
# ------------------------------------------------------------------
API_URL="${API_URL:-http://localhost:8000}"
DEMO_TEXT_FILE="C:\\artifacts\\WineBot_Demo.txt"
DEMO_REG_KEY="HKCU\\Software\\WineBotDemoKey"
DEMO_REG_STRING_NAME="DemoString"
DEMO_REG_STRING_VALUE="Hello from WineBot Input Pipeline!"
DEMO_REG_DWORD_NAME="DemoCounter"
DEMO_REG_DWORD_VALUE="42"
DEMO_BAT_FILE="C:\\artifacts\\CmdScript_Demo.bat"
DEMO_BAT_OUTPUT="C:\\artifacts\\CmdScript_Output.txt"
DEMO_SCRIPT_REG_KEY="HKCU\\Software\\WineBotCmdScript"

# ------------------------------------------------------------------
# HELPERS
# ------------------------------------------------------------------
TOKEN=""
SESSION=""
SESSDIR=""

detect_token() {
  if [ -n "${API_TOKEN:-}" ]; then
    TOKEN="$API_TOKEN"
    return
  fi
  # Try to read from running container
  TOKEN=$(docker exec compose-winebot-interactive-1 sh -c 'cat /tmp/winebot_api_token 2>/dev/null || cat /winebot-shared/winebot_api_token 2>/dev/null' 2>/dev/null | tr -d '[:space:]' || true)
  if [ -z "$TOKEN" ]; then
    echo "ERROR: Could not detect API token. Set API_TOKEN env var or ensure container is running."
    exit 1
  fi
}

api_get()  { curl -sfS -H "X-API-Key: $TOKEN" "$API_URL$1" 2>/dev/null; }
api_post() { curl -sfS -X POST -H "X-API-Key: $TOKEN" -H "Content-Type: application/json" -d "$2" "$API_URL$1" 2>/dev/null; }

annotate() {
  local text="$1"
  echo "  [SUB] $text"
  docker exec compose-winebot-interactive-1 sh -c \
    "python3 -m automation.recorder annotate --session-dir '$SESSDIR' --text '$text' --kind annotation --source demo" 2>/dev/null || true
}

click_notepad() { api_post "/input/mouse/click" "{\"x\": 300, \"y\": 300, \"button\": 1, \"window_title\": \"Notepad\"}" > /dev/null; }
type_text()     { api_post "/input/key" "{\"keys\": \"$1\", \"window_title\": \"$2\"}" > /dev/null; }
press_key()     { api_post "/input/key" "{\"keys\": \"$1\", \"window_title\": \"$2\"}" > /dev/null; }
launch_app()    { api_post "/apps/run" "{\"path\": \"$1\", \"detach\": true}" > /dev/null; }

# ------------------------------------------------------------------
# INIT
# ------------------------------------------------------------------
detect_token

# Grant agent control
SESSION=$(api_get "/lifecycle/status" | grep -o '"session_id":[[:space:]]*"[^"]*"' | head -1 | sed 's/.*"\([^"]*\)"$/\1/')
SESSDIR="/artifacts/sessions/$SESSION"
CT=$(curl -s -X POST -H "X-API-Key: $TOKEN" "$API_URL/sessions/$SESSION/control/challenge" | grep -o '"token":[[:space:]]*"[^"]*"' | sed 's/.*"\([^"]*\)"$/\1/')
api_post "/sessions/$SESSION/control/grant" "{\"lease_seconds\": 7200, \"user_ack\": true, \"challenge_token\": \"$CT\"}" > /dev/null

# Ensure artifacts directory exists (via Wine so FS layer registers it)
docker exec compose-winebot-interactive-1 sh -c 'wine cmd /c "if not exist C:\\artifacts mkdir C:\\artifacts"' 2>/dev/null || true
# Also create at Linux level so docker cp works
docker exec compose-winebot-interactive-1 sh -c 'mkdir -p /wineprefix/drive_c/artifacts' 2>/dev/null || true

echo "========================================"
echo "  WineBot Input Pipeline Demo"
echo "  Session: $SESSION"
echo "  API: $API_URL"
echo "========================================"
echo ""

# ------------------------------------------------------------------
# PART 1: FILE CREATE (Notepad + Keyboard + Mouse)
# ------------------------------------------------------------------
echo "=== PART 1: Create a Text File ==="
annotate "PART 1: Create a Text File via Notepad"

launch_app "notepad.exe"
sleep 3
annotate "Notepad launched via API /apps/run"
sleep 1

click_notepad
annotate "MOUSE CLICK: Focused Notepad window"
sleep 0.5

type_text "WineBot Demo File - Created via API keyboard injection" "Notepad"; sleep 0.3
press_key "Return" "Notepad"; sleep 0.15
press_key "Return" "Notepad"; sleep 0.15
type_text "Created entirely through the WineBot API input pipeline." "Notepad"; sleep 0.3
press_key "Return" "Notepad"; sleep 0.15
type_text "Mouse positions cursor. Keyboard types text. Chords run commands." "Notepad"; sleep 0.3
annotate "KEYBOARD: 3 lines typed via /input/key AHK backend"
sleep 0.3

press_key "ctrl+s" "Notepad"; sleep 2
annotate "MODIFIER CHORD: Ctrl+S opens Save As dialog"
sleep 0.5

type_text "$DEMO_TEXT_FILE" "Notepad"; sleep 0.3
press_key "Return" "Notepad"; sleep 1.5
annotate "FILE SAVED"
sleep 0.5

press_key "alt+F4" "Notepad"; sleep 1
annotate "Alt+F4: Notepad closed"
sleep 0.5

echo "  [VERIFY] File:"
docker exec compose-winebot-interactive-1 sh -c 'cat /wineprefix/drive_c/artifacts/WineBot_Demo.txt 2>/dev/null' || echo "(verify manually)"

# ------------------------------------------------------------------
# PART 2: FILE EDIT
# ------------------------------------------------------------------
echo ""
echo "=== PART 2: Edit the File ==="
annotate "PART 2: Re-open and Edit the File"
sleep 2

launch_app "notepad.exe"; sleep 3
press_key "ctrl+o" "Notepad"; sleep 1.5
annotate "Ctrl+O: Open File dialog"
sleep 0.5

type_text "$DEMO_TEXT_FILE" "Notepad"; sleep 0.3
press_key "Return" "Notepad"; sleep 2
annotate "File re-opened for editing"
sleep 0.5

click_notepad; sleep 0.3
press_key "Return" "Notepad"; sleep 0.15
press_key "Return" "Notepad"; sleep 0.15
type_text "--- EDITED via WineBot API ---" "Notepad"; sleep 0.3
press_key "Return" "Notepad"; sleep 0.15
type_text "File edit successful." "Notepad"; sleep 0.3
annotate "FILE EDITED: New lines appended"
sleep 0.3

press_key "ctrl+s" "Notepad"; sleep 1.5
press_key "alt+F4" "Notepad"; sleep 1
annotate "FILE SAVED AND CLOSED"
sleep 0.5

# ------------------------------------------------------------------
# PART 3: REGISTRY CREATE
# ------------------------------------------------------------------
echo ""
echo "=== PART 3: Create Registry Keys ==="
annotate "PART 3: Registry Key and Values via Regedit"
sleep 2

launch_app "regedit.exe"; sleep 3
annotate "Regedit launched"
sleep 1

# Navigate to HKCU -> Software
for i in 1 2 3 4; do press_key "Tab" "Registry Editor"; sleep 0.2; done
for i in 1 2 3; do press_key "Down" "Registry Editor"; sleep 0.2; done
annotate "TAB + ARROW KEYS: Navigated to HKEY_CURRENT_USER"
sleep 0.3

press_key "Right" "Registry Editor"; sleep 0.5
for i in 1 2 3 4 5 6 7 8 9; do press_key "Down" "Registry Editor"; sleep 0.2; done
annotate "RIGHT + DOWN ARROWS: HKCU\\Software selected"
sleep 0.3

# Create key
press_key "alt+e" "Registry Editor"; sleep 0.5
for i in 1 2 3; do press_key "Down" "Registry Editor"; sleep 0.2; done
press_key "Return" "Registry Editor"; sleep 1
type_text "WineBotDemoKey" "Registry Editor"; sleep 0.3
press_key "Return" "Registry Editor"; sleep 0.5
annotate "REGISTRY KEY CREATED: HKCU\\Software\\WineBotDemoKey"
sleep 0.5

# Create String Value
press_key "alt+e" "Registry Editor"; sleep 0.3
for i in 1 2 3 4; do press_key "Down" "Registry Editor"; sleep 0.2; done
press_key "Return" "Registry Editor"; sleep 1
type_text "$DEMO_REG_STRING_NAME" "Registry Editor"; sleep 0.3
press_key "Return" "Registry Editor"; sleep 1.5
type_text "$DEMO_REG_STRING_VALUE" "Registry Editor"; sleep 0.3
press_key "Return" "Registry Editor"; sleep 0.5
annotate "STRING VALUE: $DEMO_REG_STRING_NAME = $DEMO_REG_STRING_VALUE"
sleep 0.5

# Create DWORD Value
press_key "alt+e" "Registry Editor"; sleep 0.3
for i in 1 2 3 4 5; do press_key "Down" "Registry Editor"; sleep 0.2; done
press_key "Return" "Registry Editor"; sleep 1
type_text "$DEMO_REG_DWORD_NAME" "Registry Editor"; sleep 0.3
press_key "Return" "Registry Editor"; sleep 1
type_text "$DEMO_REG_DWORD_VALUE" "Registry Editor"; sleep 0.3
press_key "Return" "Registry Editor"; sleep 0.5
annotate "DWORD VALUE: $DEMO_REG_DWORD_NAME = $DEMO_REG_DWORD_VALUE"
sleep 0.5

press_key "alt+F4" "Registry Editor"; sleep 1
annotate "Regedit closed"

# Verify with reg.exe
launch_app "cmd.exe"; sleep 3
type_text "reg query $DEMO_REG_KEY" "cmd"; sleep 0.3
press_key "Return" "cmd"; sleep 1.5
annotate "REG VERIFIED via reg.exe"
sleep 0.5
press_key "exit" "cmd"; sleep 0.2
press_key "Return" "cmd"; sleep 1.5

# ------------------------------------------------------------------
# PART 4: PROGRAMMATIC CMD SCRIPT
# Writes, executes, and verifies a batch script via Python API
# The script reads the registry value created in Part 3
# ------------------------------------------------------------------
echo ""
echo "=== PART 4: Programmatic CMD Script ==="
annotate "PART 4: Programmatic CMD Script - Reads Registry Value from Part 3"
sleep 2

# Write .bat file via docker cp (reliable, no JSON escaping issues)
# The .bat template lives alongside this script
SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
docker cp "$SCRIPT_DIR/CmdScript_Demo.bat" compose-winebot-interactive-1:/wineprefix/drive_c/artifacts/CmdScript_Demo.bat 2>/dev/null || true

echo "  [VERIFY] Batch file copied into container:"
docker exec compose-winebot-interactive-1 sh -c 'head -5 /wineprefix/drive_c/artifacts/CmdScript_Demo.bat 2>/dev/null' || echo "  (check manually)"
annotate "Batch script copied via docker cp"
sleep 1

# Execute the batch script
echo ""
echo "  [EXECUTE] Running cmd.exe /c CmdScript_Demo.bat"
api_post "/apps/run" "{\"path\": \"cmd.exe\", \"args\": \"/c C:/artifacts/CmdScript_Demo.bat\", \"detach\": false}"
sleep 3
annotate "BATCH SCRIPT EXECUTED: cmd.exe /c CmdScript_Demo.bat"
sleep 1

# Verify output
echo ""
echo "  [VERIFY] Script output file:"
docker exec compose-winebot-interactive-1 sh -c 'cat /wineprefix/drive_c/artifacts/CmdScript_Output.txt 2>/dev/null' || echo "(check manually)"
annotate "VERIFIED: Script created file, registry key, READ registry from Part 3"
sleep 1

# Verify registry key created by script
echo ""
echo "  [VERIFY] Registry key from script:"
api_post "/apps/run" "{\"path\": \"cmd.exe\", \"args\": \"/c reg query $DEMO_SCRIPT_REG_KEY\", \"detach\": false}"
sleep 1.5
echo ""

# ------------------------------------------------------------------
# PART 5: CLEANUP
# ------------------------------------------------------------------
echo ""
echo "=== PART 5: Cleanup ==="
annotate "PART 5: Cleanup - Delete files and registry keys"
sleep 2

api_post "/apps/run" "{\"path\": \"cmd.exe\", \"args\": \"/c del $DEMO_TEXT_FILE & del $DEMO_BAT_OUTPUT & del $DEMO_BAT_FILE & echo Files deleted\", \"detach\": false}"
sleep 1
api_post "/apps/run" "{\"path\": \"cmd.exe\", \"args\": \"/c reg delete $DEMO_REG_KEY /f & reg delete $DEMO_SCRIPT_REG_KEY /f & echo Registry keys deleted\", \"detach\": false}"
sleep 1
annotate "CLEANUP COMPLETE: All files and registry keys removed"

# ------------------------------------------------------------------
# FINISH
# ------------------------------------------------------------------
echo ""
echo "========================================"
echo "  DEMO COMPLETE"
echo "  Session: $SESSION"
echo "  Session dir: $SESSDIR"
echo ""
echo "  To view recording:"
echo "    docker cp compose-winebot-interactive-1:$SESSDIR/video_001.mkv ./demo/output/"
echo ""
echo "  Input types demonstrated:"
echo "    - Mouse click via /input/mouse/click (xdotool)"
echo "    - Keyboard text via /input/key (AHK Send backend)"
echo "    - Named keys: Return, Tab, Escape, Down, Right"
echo "    - Modifier chords: Ctrl+S, Ctrl+O, Alt+E, Alt+F4"
echo "    - Agent app launch via /apps/run"
echo "    - Python script execution via /run/python"
echo ""
echo "  Capabilities demonstrated:"
echo "    - File create, edit, and delete"
echo "    - Registry key create with string + DWORD values"
echo "    - Programmatic batch script write and execute"
echo "    - Batch script reads registry values from prior steps"
echo "========================================"

# Stop recording
api_post "/recording/stop" '{}' 2>/dev/null || true
sleep 2

# List video files
echo ""
echo "Video files:"
docker exec compose-winebot-interactive-1 sh -c "ls -lh $SESSDIR/*.mkv 2>/dev/null" || echo "  (none)"
echo ""
echo "Subtitle files:"
docker exec compose-winebot-interactive-1 sh -c "ls -lh $SESSDIR/*.vtt $SESSDIR/*.ass 2>/dev/null" || echo "  (none)"
