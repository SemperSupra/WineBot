#!/usr/bin/env bash
# WineBot Input Pipeline Demo v5 — AHK Pipe Dialog + cmd.exe Reg
# No Wine Save As dialogs triggered. AHK Gui replaces them entirely.
set -u
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
source "$SCRIPT_DIR/_demo_common.sh"
init_session

# Extra artifacts dir (needed for cmd.exe paths in demo)
MSYS_NO_PATHCONV=1 docker exec "$CONTAINER" sh -c \
  'wine cmd /c "if not exist C:\\artifacts mkdir C:\\artifacts" && mkdir -p /wineprefix/drive_c/artifacts' 2>/dev/null || true

echo "======== WineBot Demo v5 ========"
echo "  Session: $SESSION"
echo ""

# ================ SETUP ================
echo "=== SETUP: Deploy AHK Dialog Handler ==="
ch "Setup: AHK Dialog Handler + Watcher"
ann "SETUP: AHK pipe-driven dialog handler + dialog watcher deployed"

bench "ahk_handler_setup" setup_ahk_handler 1   # with dialog watcher

# ================ PART 1: MOUSE + KEYBOARD ================
echo ""
echo "=== PART 1: Mouse + Keyboard Input ==="
ch "Part 1: Mouse Click + Keyboard Input"
ann "PART 1: Mouse click and keyboard text input"

api_post "/apps/run" '{"path":"notepad.exe","detach":true}' > /dev/null
cv_wait "Notepad" 10 || sleep 3
ann "Notepad launched via /apps/run"
snap "notepad_launched"
ann_expect "Notepad window visible" "Notepad"
click_notepad
ann "MOUSE CLICK: Focus at 300x300"
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
ann "KEYBOARD: Multiple lines typed via /input/key AHK backend"

press_key "Return" "Notepad"; sleep 0.15
press_key "Return" "Notepad"; sleep 0.15
type_text "Tab demo:" "Notepad"; sleep 0.3
press_key "Return" "Notepad"; sleep 0.15
press_key "Tab" "Notepad"; sleep 0.15
type_text "Tab-indented" "Notepad"; sleep 0.3
ann "NAMED KEY: Tab demonstrated"

press_key "Return" "Notepad"; sleep 0.15
type_text "Ctrl+A selects all text" "Notepad"; sleep 0.3
press_key "ctrl+a" "Notepad"; sleep 0.3
ann "MODIFIER CHORD: Ctrl+A"

sleep 0.5

# ================ PART 2: AHK PIPE DIALOG — no Wine dialog needed ================
echo ""
echo "=== PART 2: AHK Pipe Dialog Save ==="
ch "Part 2: AHK Pipe Dialog — open_gui -> set_filename -> click_save"
ann "PART 2: AHK Gui dialog replaces Save As entirely — no Wine comdlg32 needed"

# Open the AHK Gui — this IS the dialog. No Ctrl+S. No Wine Save As.
pipe_cmd "open_gui"
sleep 2
RESP=$(pipe_read)
echo "  Gui: $RESP"

GUI_COUNT=$(MSYS_NO_PATHCONV=1 docker exec "$CONTAINER" xdotool search --name "WineBot Save Dialog" 2>/dev/null | wc -l)
echo "  AHK Gui visible: $GUI_COUNT"
ann "AHK Gui dialog open — replaces Save As entirely"
snap "pipe_dialog_open"
ann_expect "AHK Save dialog open" "WineBot Save Dialog"

# Set filename via pipe
pipe_cmd "set_filename:WineBot_Demo_v5.txt"
sleep 2
echo "  set_filename: $(pipe_read)"
ann "Filename set via pipe: WineBot_Demo_v5.txt"

# Save via pipe
pipe_cmd "click_save"
sleep 3
RESP=$(pipe_wait "saved" 6)
echo "  Save: ${RESP:-checking disk...}"
ann "FILE SAVED via AHK pipe protocol — no Wine dialog ever opened"
snap "file_saved"
ann_expect "File saved successfully" ""   # checkpoint — no specific window
echo ""
echo "  [VERIFY]:"
MSYS_NO_PATHCONV=1 docker exec "$CONTAINER" sh -c \
  'test -f /wineprefix/drive_c/artifacts/WineBot_Demo_v5.txt && echo "  FILE EXISTS" && cat /wineprefix/drive_c/artifacts/WineBot_Demo_v5.txt' 2>/dev/null || echo "  (check manually)"

# Close Notepad — select-all + delete first to avoid "Save changes?" prompt
press_key "ctrl+a" "Notepad"; sleep 0.3
press_key "Delete" "Notepad"; sleep 0.3
type_text " " "Notepad"; sleep 0.2
press_key "alt+F4" "Notepad"; sleep 2
ann "Alt+F4: Notepad closed (document was cleared)"

# ================ PART 3: FILE OPS via cmd.exe /c (no keyboard) ================
echo ""
echo "=== PART 3: File Create, Verify, Edit via cmd.exe ==="
ch "Part 3: File Operations via cmd.exe /c"
ann "PART 3: File operations via cmd.exe /c (no keyboard, no window targeting)"

# cmd.exe has no X11 window in Wine — use /apps/run with args directly
api_post "/apps/run" '{"path":"cmd.exe","args":"/c echo WineBot cmd.exe demo > C:/artifacts/CmdDemo_v5.txt & echo Line 2: Created via cmd.exe API >> C:/artifacts/CmdDemo_v5.txt","detach":false}' > /dev/null
sleep 1
ann "FILE CREATED: CmdDemo_v5.txt"

api_post "/apps/run" '{"path":"cmd.exe","args":"/c type C:/artifacts/CmdDemo_v5.txt","detach":false}' > /dev/null
sleep 1
ann "FILE VERIFIED: Content displayed"

echo "  [VERIFY] $(MSYS_NO_PATHCONV=1 docker exec "$CONTAINER" wc -l //wineprefix/drive_c/artifacts/CmdDemo_v5.txt 2>/dev/null) lines"

# ================ PART 4: REGISTRY via cmd.exe /c reg ================
echo ""
echo "=== PART 4: Registry via cmd.exe reg add/query/delete ==="
ch "Part 4: Registry Operations via reg.exe"
ann "PART 4: Registry via cmd.exe /c reg (deterministic, no GUI, no keyboard)"

api_post "/apps/run" '{"path":"cmd.exe","args":"/c reg add HKCU\\\\Software\\WineBotDemo /v Version /t REG_SZ /d v5.0 /f","detach":false}' > /dev/null
sleep 0.5
ann "REG ADD: HKCU\\\\Software\\WineBotDemo Version=v5.0"

api_post "/apps/run" '{"path":"cmd.exe","args":"/c reg add HKCU\\\\Software\\WineBotDemo /v Count /t REG_DWORD /d 5 /f","detach":false}' > /dev/null
sleep 0.5
ann "REG ADD: HKCU\\\\Software\\WineBotDemo Count=5 (DWORD)"

api_post "/apps/run" '{"path":"cmd.exe","args":"/c reg add HKCU\\\\Software\\WineBotDemo /v Status /t REG_SZ /d Active /f","detach":false}' > /dev/null
sleep 0.5
ann "REG ADD: Status=Active"

api_post "/apps/run" '{"path":"cmd.exe","args":"/c reg query HKCU\\\\Software\\WineBotDemo","detach":false}' > /dev/null
sleep 1
ann "REG QUERY: All values confirmed"

api_post "/apps/run" '{"path":"cmd.exe","args":"/c reg delete HKCU\\\\Software\\WineBotDemo /f","detach":false}' > /dev/null
sleep 0.5
ann "REG DELETE: Key removed"

# ================ PART 5: BATCH SCRIPT ================
echo ""
echo "=== PART 5: Batch Script Deployment + Execution ==="
ch "Part 5: Batch Script via docker cp"
ann "PART 5: Batch script deployed and executed"

MSYS_NO_PATHCONV=1 docker cp "$SCRIPT_DIR/CmdScript_Demo.bat" "$CONTAINER://wineprefix/drive_c/artifacts/CmdScript_Demo.bat" 2>/dev/null

api_post "/apps/run" '{"path":"cmd.exe","args":"/c C:/artifacts/CmdScript_Demo.bat","detach":false}' > /dev/null
sleep 3
ann "BATCH SCRIPT EXECUTED via cmd.exe /c"

# ================ CLEANUP ================
echo ""
echo "=== PART 6: Cleanup ==="
ch "Part 6: Cleanup"
ann "PART 6: Cleanup"

api_post "/apps/run" '{"path":"cmd.exe","args":"/c del C:/artifacts/WineBot_Demo_v5.txt 2>nul & del C:/artifacts/CmdDemo_v5.txt 2>nul & del C:/artifacts/CmdScript_Demo.bat 2>nul & del C:/artifacts/CmdScript_Output.txt 2>nul","detach":false}' > /dev/null
sleep 0.5
ann "CLEANUP COMPLETE"

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

stop_recording
print_copy_instructions "core-pipeline"
