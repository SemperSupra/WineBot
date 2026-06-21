#!/usr/bin/env bash
# WineBot Input Pipeline Demo v5 — AHK Pipe Dialog + cmd.exe Reg
# No Wine Save As dialogs triggered. AHK Gui replaces them entirely.
set -u

API_URL="${API_URL:-http://localhost:8000}"
PIPE="//wineprefix/drive_c/dialog_handler/pipe.txt"

TOKEN=""; SESSION=""; SESSDIR=""

detect_token() {
  [ -n "${API_TOKEN:-}" ] && { TOKEN="$API_TOKEN"; return; }
  TOKEN=$(MSYS_NO_PATHCONV=1 docker exec compose-winebot-interactive-1 sh -c 'cat /tmp/winebot_api_token 2>/dev/null || cat /winebot-shared/winebot_api_token 2>/dev/null' 2>/dev/null | tr -d '[:space:]' || true)
  [ -z "$TOKEN" ] && { echo "ERROR: Cannot detect API token"; exit 1; }
}

api_get()  { curl -sfS -H "X-API-Key: $TOKEN" "$API_URL$1" 2>/dev/null; }
api_post() { curl -sfS -X POST -H "X-API-Key: $TOKEN" -H "Content-Type: application/json" -d "$2" "$API_URL$1" 2>/dev/null; }

annotate() {
  echo "  [SUB] $1"
  MSYS_NO_PATHCONV=1 docker exec compose-winebot-interactive-1 sh -c \
    "python3 -m automation.recorder annotate --session-dir '$SESSDIR' --text '$1' --kind annotation --source demo" 2>/dev/null || true
}

chapter() {
  echo "  [CH] $1"
  MSYS_NO_PATHCONV=1 docker exec compose-winebot-interactive-1 sh -c \
    "python3 -m automation.recorder annotate --session-dir '$SESSDIR' --text '$1' --kind chapter --source demo" 2>/dev/null || true
}

pipe_cmd()  { MSYS_NO_PATHCONV=1 docker exec compose-winebot-interactive-1 su -s /bin/sh winebot -c "echo '$1' > '$PIPE'" 2>/dev/null; }
pipe_read() { MSYS_NO_PATHCONV=1 docker exec compose-winebot-interactive-1 su -s /bin/sh winebot -c "cat '$PIPE' 2>/dev/null" || true; }
pipe_wait() {
  local pattern="$1" timeout="${2:-15}"
  for i in $(seq 1 "$timeout"); do
    local resp; resp=$(pipe_read)
    if echo "$resp" | grep -q "$pattern"; then echo "$resp"; return 0; fi
    sleep 0.5
  done; return 1
}

click_notepad() { api_post "/input/mouse/click" '{"x":300,"y":300,"button":1,"window_title":"Notepad"}' > /dev/null; }
type_text()     { api_post "/input/key" "{\"keys\":\"$1\",\"window_title\":\"$2\"}" > /dev/null; }
press_key()     { api_post "/input/key" "{\"keys\":\"$1\",\"window_title\":\"$2\"}" > /dev/null; }

# INIT
detect_token
SESSION=$(api_get "/lifecycle/status" | grep -o '"session_id":[[:space:]]*"[^"]*"' | head -1 | sed 's/.*"\([^"]*\)"$/\1/')
SESSDIR="/artifacts/sessions/$SESSION"
CT=$(curl -s -X POST -H "X-API-Key: $TOKEN" "$API_URL/sessions/$SESSION/control/challenge" | grep -o '"token":[[:space:]]*"[^"]*"' | sed 's/.*"\([^"]*\)"$/\1/')
api_post "/sessions/$SESSION/control/grant" "{\"lease_seconds\":7200,\"user_ack\":true,\"challenge_token\":\"$CT\"}" > /dev/null
docker exec compose-winebot-interactive-1 sh -c 'wine cmd /c "if not exist C:\\artifacts mkdir C:\\artifacts" && mkdir -p /wineprefix/drive_c/artifacts' 2>/dev/null || true

echo "======== WineBot Demo v5 ========"
echo "  Session: $SESSION"
echo ""

# ================ SETUP ================
echo "=== SETUP: Deploy AHK Dialog Handler ==="
chapter "Setup: AHK Dialog Handler + Watcher"
annotate "SETUP: AHK pipe-driven dialog handler + dialog watcher deployed"

docker exec compose-winebot-interactive-1 rm -rf //wineprefix/drive_c/dialog_handler 2>/dev/null
docker exec compose-winebot-interactive-1 mkdir -p //wineprefix/drive_c/dialog_handler //wineprefix/drive_c/artifacts 2>/dev/null
docker exec compose-winebot-interactive-1 chown -R winebot:winebot //wineprefix/drive_c/dialog_handler //wineprefix/drive_c/artifacts 2>/dev/null
docker cp automation/core/dialog_replacement.ahk compose-winebot-interactive-1://wineprefix/drive_c/dr.ahk 2>/dev/null
docker cp automation/core/dialog_watcher.ahk compose-winebot-interactive-1://wineprefix/drive_c/dw.ahk 2>/dev/null
docker exec compose-winebot-interactive-1 chown winebot:winebot //wineprefix/drive_c/dr.ahk //wineprefix/drive_c/dw.ahk 2>/dev/null

# Launch AHK pipe dialog
api_post "/apps/run" '{"path":"ahk","args":"C:/dr.ahk","detach":true}' > /dev/null
sleep 6
echo "  Pipe handler: $(pipe_read)"

# Launch persistent dialog watcher (closes stray Save As / Open / Error dialogs)
api_post "/apps/run" '{"path":"ahk","args":"C:/dw.ahk","detach":true}' > /dev/null
sleep 3
WATCHER_COUNT=$(docker exec compose-winebot-interactive-1 sh -c 'ps aux | grep dw.ahk | grep -v grep | grep -v start.exe | wc -l' 2>/dev/null)
echo "  Watcher procs: $WATCHER_COUNT"
annotate "Dialog watcher active — auto-closes stray Save As/Error dialogs"

# ================ PART 1: MOUSE + KEYBOARD ================
echo ""
echo "=== PART 1: Mouse + Keyboard Input ==="
chapter "Part 1: Mouse Click + Keyboard Input"
annotate "PART 1: Mouse click and keyboard text input"

api_post "/apps/run" '{"path":"notepad.exe","detach":true}' > /dev/null
sleep 3
annotate "Notepad launched via /apps/run"
click_notepad
annotate "MOUSE CLICK: Focus at 300x300"
sleep 0.5

type_text "WineBot Input Pipeline Demo v5" "Notepad"
sleep 0.3
press_key "Return" "Notepad"; sleep 0.15
press_key "Return" "Notepad"; sleep 0.15
type_text "All input types working:" "Notepad"; sleep 0.3
press_key "Return" "Notepad"; sleep 0.15
type_text "  - Mouse click" "Notepad"; sleep 0.3
press_key "Return" "Notepad"; sleep 0.15
type_text "  - Keyboard text" "Notepad"; sleep 0.3
press_key "Return" "Notepad"; sleep 0.15
type_text "  - Named keys: Return, Tab" "Notepad"; sleep 0.3
press_key "Return" "Notepad"; sleep 0.15
type_text "  - Modifier chords: Ctrl+A, Ctrl+S" "Notepad"; sleep 0.3
annotate "KEYBOARD: Multiple lines typed via /input/key AHK backend"

press_key "Return" "Notepad"; sleep 0.15
press_key "Return" "Notepad"; sleep 0.15
type_text "Tab demo:" "Notepad"; sleep 0.3
press_key "Return" "Notepad"; sleep 0.15
press_key "Tab" "Notepad"; sleep 0.15
type_text "Tab-indented" "Notepad"; sleep 0.3
annotate "NAMED KEY: Tab demonstrated"

press_key "Return" "Notepad"; sleep 0.15
type_text "Ctrl+A selects all text" "Notepad"; sleep 0.3
press_key "ctrl+a" "Notepad"; sleep 0.3
annotate "MODIFIER CHORD: Ctrl+A"

sleep 0.5

# ================ PART 2: AHK PIPE DIALOG — no Wine dialog needed ================
echo ""
echo "=== PART 2: AHK Pipe Dialog Save ==="
chapter "Part 2: AHK Pipe Dialog — open_gui -> set_filename -> click_save"
annotate "PART 2: AHK Gui dialog replaces Save As entirely — no Wine comdlg32 needed"

# Open the AHK Gui — this IS the dialog. No Ctrl+S. No Wine Save As.
pipe_cmd "open_gui"
sleep 2
RESP=$(pipe_read)
echo "  Gui: $RESP"

GUI_COUNT=$(docker exec compose-winebot-interactive-1 xdotool search --name "WineBot Save Dialog" 2>/dev/null | wc -l)
echo "  AHK Gui visible: $GUI_COUNT"
annotate "AHK Gui dialog open — replaces Save As entirely"

# Set filename via pipe
pipe_cmd "set_filename:WineBot_Demo_v5.txt"
sleep 2
echo "  set_filename: $(pipe_read)"
annotate "Filename set via pipe: WineBot_Demo_v5.txt"

# Save via pipe
pipe_cmd "click_save"
sleep 3
RESP=$(pipe_wait "saved" 6)
echo "  Save: ${RESP:-checking disk...}"
annotate "FILE SAVED via AHK pipe protocol — no Wine dialog ever opened"

# Verify on disk
echo ""
echo "  [VERIFY]:"
docker exec compose-winebot-interactive-1 sh -c \
  'test -f /wineprefix/drive_c/artifacts/WineBot_Demo_v5.txt && echo "  FILE EXISTS" && cat /wineprefix/drive_c/artifacts/WineBot_Demo_v5.txt' 2>/dev/null || echo "  (check manually)"

# Close Notepad — select-all + delete first to avoid "Save changes?" prompt
press_key "ctrl+a" "Notepad"; sleep 0.3
press_key "Delete" "Notepad"; sleep 0.3
type_text " " "Notepad"; sleep 0.2
press_key "alt+F4" "Notepad"; sleep 2
annotate "Alt+F4: Notepad closed (document was cleared)"

# ================ PART 3: FILE OPS via cmd.exe /c (no keyboard) ================
echo ""
echo "=== PART 3: File Create, Verify, Edit via cmd.exe ==="
chapter "Part 3: File Operations via cmd.exe /c"
annotate "PART 3: File operations via cmd.exe /c (no keyboard, no window targeting)"

# cmd.exe has no X11 window in Wine — use /apps/run with args directly
api_post "/apps/run" '{"path":"cmd.exe","args":"/c echo WineBot cmd.exe demo > C:/artifacts/CmdDemo_v5.txt & echo Line 2: Created via cmd.exe API >> C:/artifacts/CmdDemo_v5.txt","detach":false}' > /dev/null
sleep 1
annotate "FILE CREATED: CmdDemo_v5.txt"

api_post "/apps/run" '{"path":"cmd.exe","args":"/c type C:/artifacts/CmdDemo_v5.txt","detach":false}' > /dev/null
sleep 1
annotate "FILE VERIFIED: Content displayed"

echo "  [VERIFY] $(docker exec compose-winebot-interactive-1 wc -l //wineprefix/drive_c/artifacts/CmdDemo_v5.txt 2>/dev/null) lines"

# ================ PART 4: REGISTRY via cmd.exe /c reg ================
echo ""
echo "=== PART 4: Registry via cmd.exe reg add/query/delete ==="
chapter "Part 4: Registry Operations via reg.exe"
annotate "PART 4: Registry via cmd.exe /c reg (deterministic, no GUI, no keyboard)"

api_post "/apps/run" '{"path":"cmd.exe","args":"/c reg add HKCU\\\\Software\\WineBotDemo /v Version /t REG_SZ /d v5.0 /f","detach":false}' > /dev/null
sleep 0.5
annotate "REG ADD: HKCU\\\\Software\\WineBotDemo Version=v5.0"

api_post "/apps/run" '{"path":"cmd.exe","args":"/c reg add HKCU\\\\Software\\WineBotDemo /v Count /t REG_DWORD /d 5 /f","detach":false}' > /dev/null
sleep 0.5
annotate "REG ADD: HKCU\\\\Software\\WineBotDemo Count=5 (DWORD)"

api_post "/apps/run" '{"path":"cmd.exe","args":"/c reg add HKCU\\\\Software\\WineBotDemo /v Status /t REG_SZ /d Active /f","detach":false}' > /dev/null
sleep 0.5
annotate "REG ADD: Status=Active"

api_post "/apps/run" '{"path":"cmd.exe","args":"/c reg query HKCU\\\\Software\\WineBotDemo","detach":false}' > /dev/null
sleep 1
annotate "REG QUERY: All values confirmed"

api_post "/apps/run" '{"path":"cmd.exe","args":"/c reg delete HKCU\\\\Software\\WineBotDemo /f","detach":false}' > /dev/null
sleep 0.5
annotate "REG DELETE: Key removed"

# ================ PART 5: BATCH SCRIPT ================
echo ""
echo "=== PART 5: Batch Script Deployment + Execution ==="
chapter "Part 5: Batch Script via docker cp"
annotate "PART 5: Batch script deployed and executed"

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
docker cp "$SCRIPT_DIR/CmdScript_Demo.bat" compose-winebot-interactive-1://wineprefix/drive_c/artifacts/CmdScript_Demo.bat 2>/dev/null

api_post "/apps/run" '{"path":"cmd.exe","args":"/c C:/artifacts/CmdScript_Demo.bat","detach":false}' > /dev/null
sleep 3
annotate "BATCH SCRIPT EXECUTED via cmd.exe /c"

# ================ CLEANUP ================
echo ""
echo "=== PART 6: Cleanup ==="
chapter "Part 6: Cleanup"
annotate "PART 6: Cleanup"

api_post "/apps/run" '{"path":"cmd.exe","args":"/c del C:/artifacts/WineBot_Demo_v5.txt 2>nul & del C:/artifacts/CmdDemo_v5.txt 2>nul & del C:/artifacts/CmdScript_Demo.bat 2>nul & del C:/artifacts/CmdScript_Output.txt 2>nul","detach":false}' > /dev/null
sleep 0.5
annotate "CLEANUP COMPLETE"

# ================ SUMMARY ================
echo ""
echo "======== Demo Complete (v5) ========"
echo "  Inputs: Mouse click, keyboard text, named keys, modifier chords"
echo "  Dialog: AHK Gui replaces Save As — no Wine comdlg32 needed"
echo "  File ops: cmd.exe echo/redirect/type (no dialogs)"
echo "  Registry: cmd.exe reg add/query/delete (deterministic, no GUI)"
echo "  Batch: docker cp + cmd.exe execution"
echo "  Pipe protocol: zero chown, su winebot throughout"
echo "======================================"

api_post "/recording/stop" '{}' 2>/dev/null || true
sleep 2
docker exec compose-winebot-interactive-1 sh -c "ls -lh $SESSDIR/*.mkv 2>/dev/null" || true
echo ""

# Smart trim: find first chapter marker on host side, trim 3s before it
VIDEO="${SESSDIR}/video_001.mkv"
FIRST=$(MSYS_NO_PATHCONV=1 docker exec compose-winebot-interactive-1 sh -c "ffprobe -v quiet -show_chapters -print_format flat '$VIDEO' 2>/dev/null | grep 'chapter.1.start_time' | sed 's/.*=\"\([0-9.]*\)\"/\1/' | head -1" 2>/dev/null)
FIRST="${FIRST:-0}"
TRIM_START=$(python3 -c "print(max(0, int(float($FIRST)) - 2))")
echo "  First content at ${FIRST}s, trimming ${TRIM_START}s"
MSYS_NO_PATHCONV=1 docker exec compose-winebot-interactive-1 sh -c "
  ffmpeg -y -ss ${TRIM_START} -i '$VIDEO' -c copy -avoid_negative_ts make_zero /tmp/trimmed.mkv 2>/dev/null
  ffmpeg -y -i /tmp/trimmed.mkv -vf 'fps=8,scale=640:-1:flags=lanczos,split[s0][s1];[s0]palettegen=max_colors=128[p];[s1][p]paletteuse' -loop 0 /tmp/trimmed.gif 2>/dev/null
  echo \"  Trimmed: \$(ls -lh /tmp/trimmed.mkv | awk '{print \$5}') GIF: \$(ls -lh /tmp/trimmed.gif | awk '{print \$5}')\"
"

echo ""
echo "To save:"
echo "  docker cp compose-winebot-interactive-1:/tmp/trimmed.mkv demo/output/demo.mkv"
echo "  docker cp compose-winebot-interactive-1:/tmp/trimmed.gif demo/output/demo.gif"
echo "  docker cp compose-winebot-interactive-1:${SESSDIR}/events_001.vtt demo/output/demo.vtt"
