#!/usr/bin/env bash
set -euo pipefail

# diagnose-input-suite.sh
# Validates Mouse (via CV) and Keyboard inputs across Notepad, Regedit, Winefile.

export DISPLAY="${DISPLAY:-:99}"
LOG_DIR="/artifacts/diagnostics_suite"
mkdir -p "$LOG_DIR"
exec > >(tee -a "$LOG_DIR/suite.log") 2>&1

log() {
  echo "[$(date +'%H:%M:%S')] $*"
}

annotate() {
  local msg="$1"
  log "Annotation: $msg"
  if [ -x "/scripts/annotate.sh" ]; then
    /scripts/annotate.sh --text "$msg" --type "subtitle" || true
  fi
}

cleanup() {
  log "Cleaning up..."
  pkill -f "notepad.exe" || true
  pkill -f "regedit.exe" || true
  pkill -f "winefile.exe" || true
  sleep 1
}
trap cleanup EXIT

take_screenshot() {
  local name="$1"
  import -window root "$LOG_DIR/${name}.png"
}

compare_shots() {
  local base="$1"
  local current="$2"
  compare -metric AE "$base" "$current" null: 2>&1 || echo "0"
}

wait_for_window() {
  local title_pat="$1"
  local win_id=""
  for _ in {1..60}; do
    win_id=$(xdotool search --onlyvisible --name "$title_pat" | head -n1 || true)
    if [ -n "$win_id" ]; then
      echo "$win_id"
      return 0
    fi
    sleep 0.5
  done
  return 1
}

# CV Helper: Captures template, moves window, finds/clicks, verifies change.
test_cv_click() {
  local win_id="$1"
  local region="$2" # WxH+X+Y relative to window
  local label="$3"
  
  log "CV: Creating template for '$label' from window $win_id region $region..."
  local temp_shot="$LOG_DIR/${label}_source.png"
  local template="$LOG_DIR/${label}_template.png"
  
  # Capture window
  import -window "$win_id" "$temp_shot"
  # Crop
  convert "$temp_shot" -crop "$region" "$template"
  
  # Move window to ensure we aren't just clicking the same spot
  log "CV: Moving window to test robustness..."
  xdotool windowmove "$win_id" 200 200
  sleep 1
  
  # Capture baseline before click
  local base_img="$LOG_DIR/${label}_base.png"
  import -window root "$base_img"
  
  log "CV: Attempting visual find & click..."
  if python3 /automation/find_and_click.py --template "$template" --retries 3 --threshold 0.7; then
      log "CV SUCCESS: Found and clicked '$label'."
  else
      log "CV FAILURE: Could not find '$label'."
      return 1
  fi
  
  sleep 1
  local click_img="$LOG_DIR/${label}_clicked.png"
  import -window root "$click_img"
  
  local diff
  diff=$(compare_shots "$base_img" "$click_img")
  log "CV Click Diff: $diff"
  
  if [ "$diff" -gt 0 ]; then
      log "CV VERIFIED: Click triggered visual change."
      return 0
  else
      log "CV FAILURE: Click had no effect."
      return 1
  fi
}

test_notepad() {
  log "=== Testing Notepad ==="
  annotate "Notepad: Mouse & Keyboard"
  
  nohup wine notepad >/dev/null 2>&1 &
  local win_id
  if ! win_id=$(wait_for_window "Notepad"); then
    log "ERROR: Notepad not found"
    return
  fi
  xdotool windowactivate "$win_id"
  sleep 1
  
  # 1. Mouse (CV)
  # File menu: approx 40x20 at 10,35 (below titlebar)
  if test_cv_click "$win_id" "40x20+10+35" "notepad_file"; then
      log "Notepad Mouse: PASS"
  else
      log "Notepad Mouse: FAIL"
      # Don't exit, try keyboard
  fi
  xdotool key --window "$win_id" Escape
  sleep 0.5
  
  # 2. Keyboard
  local kb_base="$LOG_DIR/notepad_kb_base.png"
  import -window "$win_id" "$kb_base"
  xdotool type --window "$win_id" "Test"
  sleep 0.5
  local kb_after="$LOG_DIR/notepad_kb_after.png"
  import -window "$win_id" "$kb_after"
  local diff
  diff=$(compare_shots "$kb_base" "$kb_after")
  if [ "$diff" -gt 0 ]; then
      log "Notepad Keyboard: PASS"
  else
      log "Notepad Keyboard: FAIL"
  fi
  
  xdotool windowclose "$win_id"
  sleep 1
}

test_regedit() {
  log "=== Testing Regedit ==="
  annotate "Regedit: Mouse & Keyboard"
  
  nohup wine regedit >/dev/null 2>&1 &
  local win_id
  if ! win_id=$(wait_for_window "Registry Editor"); then
    log "ERROR: Regedit not found"
    return
  fi
  xdotool windowactivate "$win_id"
  sleep 1
  
  # 1. Mouse (CV)
  # Edit menu: approx 40x20 at 50,35 (next to File)
  if test_cv_click "$win_id" "40x20+50+35" "regedit_edit"; then
      log "Regedit Mouse: PASS"
  else
      log "Regedit Mouse: FAIL"
  fi
  xdotool key --window "$win_id" Escape
  sleep 0.5
  
  # 2. Keyboard (Nav)
  local kb_base="$LOG_DIR/regedit_kb_base.png"
  import -window "$win_id" "$kb_base"
  xdotool key --window "$win_id" Down Right
  sleep 0.5
  local kb_after="$LOG_DIR/regedit_kb_after.png"
  import -window "$win_id" "$kb_after"
  local diff
  diff=$(compare_shots "$kb_base" "$kb_after")
  if [ "$diff" -gt 0 ]; then
      log "Regedit Keyboard: PASS"
  else
      log "Regedit Keyboard: FAIL"
  fi
  
  xdotool windowclose "$win_id"
  sleep 1
}

test_winefile() {
  log "=== Testing Winefile ==="
  annotate "Winefile: Mouse & Keyboard"
  
  nohup wine winefile >/dev/null 2>&1 &
  local win_id
  if ! win_id=$(wait_for_window "Wine File Manager"); then
    log "ERROR: Winefile not found"
    return
  fi
  xdotool windowactivate "$win_id"
  sleep 1
  
  # 1. Mouse (CV)
  # View menu: approx 40x20 at 90,35 (File, Disk, View?)
  # Let's guess or crop blindly. File=0, Disk=40, View=80?
  # Let's target "Disk" menu ~50,35
  if test_cv_click "$win_id" "40x20+50+35" "winefile_disk"; then
      log "Winefile Mouse: PASS"
  else
      log "Winefile Mouse: FAIL"
  fi
  xdotool key --window "$win_id" Escape
  sleep 0.5
  
  # 2. Keyboard (F5 Refresh)
  local kb_base="$LOG_DIR/winefile_kb_base.png"
  import -window "$win_id" "$kb_base"
  xdotool key --window "$win_id" F5
  sleep 0.5
  local kb_after="$LOG_DIR/winefile_kb_after.png"
  import -window "$win_id" "$kb_after"
  local diff
  diff=$(compare_shots "$kb_base" "$kb_after")
  # Refresh might not change pixels if idle. Use Alt+V (View menu) instead.
  if [ "$diff" -eq 0 ]; then
      xdotool key --window "$win_id" Alt+v
      sleep 0.5
      import -window "$win_id" "$kb_after"
      diff=$(compare_shots "$kb_base" "$kb_after")
  fi
  
  if [ "$diff" -gt 0 ]; then
      log "Winefile Keyboard: PASS"
  else
      log "Winefile Keyboard: FAIL"
  fi
  
  xdotool windowclose "$win_id"
  sleep 1
}

# Run Suite
cleanup
test_notepad
test_regedit
test_winefile
log "Suite completed."