#!/usr/bin/env bash
set -euo pipefail

# diagnose-input-suite.sh
# Validates Mouse (via CV) and Keyboard inputs across Notepad, Regedit, Winefile.

export DISPLAY="${DISPLAY:-:99}"
LOG_DIR="/artifacts/diagnostics_suite"
mkdir -p "$LOG_DIR"
exec > >(tee -a "$LOG_DIR/suite.log") 2>&1
SUMMARY_JSON="$LOG_DIR/summary.json"

log() {
  echo "[$(date +'%H:%M:%S')] $*"
}

annotate() {
  local msg="$1"
  log "Annotation: $msg"
  if [ -x "/scripts/internal/annotate.sh" ]; then
    /scripts/internal/annotate.sh --text "$msg" --type "subtitle" || true
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

latest_hook_log() {
  ls -1t /artifacts/sessions/*/logs/diagnostics/wine_hook_observer_*.jsonl 2>/dev/null | head -n1 || true
}

count_hook_mouse_events() {
  local file="$1"
  if [ -z "$file" ] || [ ! -f "$file" ]; then
    echo 0
    return 0
  fi
  local pattern='"event":[[:space:]]*"mouse_(down|up|move)"'
  if command -v rg >/dev/null 2>&1; then
    rg -c "$pattern" "$file" 2>/dev/null || echo 0
  else
    grep -Ec "$pattern" "$file" 2>/dev/null || echo 0
  fi
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
  local click_count="${4:-1}"
  local button="${5:-1}"
  
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
  xdotool windowactivate "$win_id"
  sleep 1
  
  # Capture baseline before click
  local base_img="$LOG_DIR/${label}_base.png"
  import -window root "$base_img"
  local hook_log
  hook_log="$(latest_hook_log)"
  local hook_before=0
  hook_before="$(count_hook_mouse_events "$hook_log")"
  
  log "CV: Attempting visual find & click..."
  if python3 /automation/examples/find_and_click.py --template "$template" --retries 3 --threshold 0.7 --click-count "$click_count" --button "$button" --window-id "$win_id"; then
      log "CV SUCCESS: Found and clicked '$label'."
  else
      log "CV FAILURE: Could not find '$label'."
      return 1
  fi
  
  # Capture both immediate and delayed post-click frames to catch transient UI effects.
  sleep 0.15
  local click_img_fast="$LOG_DIR/${label}_clicked_fast.png"
  import -window root "$click_img_fast"
  sleep 0.85
  local click_img_slow="$LOG_DIR/${label}_clicked_slow.png"
  import -window root "$click_img_slow"
  
  local diff_fast
  local diff_slow
  local diff
  diff_fast=$(compare_shots "$base_img" "$click_img_fast")
  diff_slow=$(compare_shots "$base_img" "$click_img_slow")
  if [ "$diff_fast" -gt "$diff_slow" ]; then
      diff="$diff_fast"
  else
      diff="$diff_slow"
  fi
  log "CV Click Diff: $diff"
  
  if [ "$diff" -gt 0 ]; then
      log "CV VERIFIED: Click triggered visual change."
      return 0
  else
      local hook_after=0
      hook_after="$(count_hook_mouse_events "$hook_log")"
      if [ "$hook_after" -gt "$hook_before" ]; then
          log "CV VERIFIED: Visual unchanged, but hook mouse events increased (${hook_before} -> ${hook_after})."
          return 0
      fi
      log "CV FAILURE: Click had no effect."
      return 1
  fi
}

test_relative_click() {
  local win_id="$1"
  local rel_x="$2"
  local rel_y="$3"
  local label="$4"
  local click_count="${5:-1}"
  local button="${6:-1}"

  log "Relative click: '$label' at (${rel_x},${rel_y}) in window $win_id..."
  xdotool windowmove "$win_id" 200 200
  xdotool windowactivate "$win_id"
  sleep 1

  local base_img="$LOG_DIR/${label}_base.png"
  import -window root "$base_img"
  local hook_log
  hook_log="$(latest_hook_log)"
  local hook_before=0
  hook_before="$(count_hook_mouse_events "$hook_log")"

  xdotool mousemove --window "$win_id" "$rel_x" "$rel_y"
  for _ in $(seq 1 "$click_count"); do
    xdotool click --window "$win_id" "$button"
  done

  sleep 0.15
  local click_img_fast="$LOG_DIR/${label}_clicked_fast.png"
  import -window root "$click_img_fast"
  sleep 0.85
  local click_img_slow="$LOG_DIR/${label}_clicked_slow.png"
  import -window root "$click_img_slow"

  local diff_fast
  local diff_slow
  local diff
  diff_fast=$(compare_shots "$base_img" "$click_img_fast")
  diff_slow=$(compare_shots "$base_img" "$click_img_slow")
  if [ "$diff_fast" -gt "$diff_slow" ]; then
      diff="$diff_fast"
  else
      diff="$diff_slow"
  fi
  log "Relative Click Diff: $diff"

  if [ "$diff" -gt 0 ]; then
      log "Relative click VERIFIED: Click triggered visual change."
      return 0
  else
      local hook_after=0
      hook_after="$(count_hook_mouse_events "$hook_log")"
      if [ "$hook_after" -gt "$hook_before" ]; then
          log "Relative click VERIFIED: Visual unchanged, but hook mouse events increased (${hook_before} -> ${hook_after})."
          return 0
      fi
      log "Relative click FAILURE: Click had no effect."
      return 1
  fi
}

test_notepad() {
  local failed=0
  local mouse_result="pass"
  local keyboard_result="pass"
  log "=== Testing Notepad ==="
  annotate "Notepad: Mouse & Keyboard"
  
  nohup wine notepad >/dev/null 2>&1 &
  local win_id
  if ! win_id=$(wait_for_window "Notepad"); then
    log "ERROR: Notepad not found"
    return 1
  fi
  xdotool windowactivate "$win_id"
  sleep 1
  
  # 1. Mouse (CV)
  # File menu: approx 40x20 at 10,35 (below titlebar)
  if test_cv_click "$win_id" "40x20+10+35" "notepad_file" 1; then
      log "Notepad Mouse: PASS"
  else
      log "Notepad Mouse: FAIL"
      mouse_result="fail"
      failed=1
  fi
  xdotool key --window "$win_id" Escape
  sleep 0.5
  xdotool windowactivate "$win_id"
  sleep 0.2
  
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
      keyboard_result="fail"
      failed=1
  fi
  
  xdotool windowclose "$win_id"
  sleep 1
  NOTEPAD_MOUSE_RESULT="$mouse_result"
  NOTEPAD_KEYBOARD_RESULT="$keyboard_result"
  return "$failed"
}

test_regedit() {
  local failed=0
  local mouse_result="pass"
  local keyboard_result="pass"
  log "=== Testing Regedit ==="
  annotate "Regedit: Mouse & Keyboard"
  
  nohup wine regedit >/dev/null 2>&1 &
  local win_id
  if ! win_id=$(wait_for_window "Registry Editor"); then
    log "ERROR: Regedit not found"
    return 1
  fi
  xdotool windowactivate "$win_id"
  sleep 1
  
  # 1. Mouse (relative deterministic)
  # Click a known-interactive control in Regedit layout (validated in-container).
  if test_relative_click "$win_id" 30 60 "regedit_control_rel" 1 1; then
      log "Regedit Mouse: PASS"
  else
      log "Regedit Mouse: FAIL"
      mouse_result="fail"
      failed=1
  fi
  xdotool key --window "$win_id" Escape
  sleep 0.5
  xdotool windowactivate "$win_id"
  sleep 0.2
  
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
      keyboard_result="fail"
      failed=1
  fi
  
  xdotool windowclose "$win_id"
  sleep 1
  REGEDIT_MOUSE_RESULT="$mouse_result"
  REGEDIT_KEYBOARD_RESULT="$keyboard_result"
  return "$failed"
}

test_winefile() {
  local failed=0
  local mouse_result="pass"
  local keyboard_result="pass"
  log "=== Testing Winefile ==="
  annotate "Winefile: Mouse & Keyboard"
  
  nohup wine winefile >/dev/null 2>&1 &
  local win_id
  if ! win_id=$(wait_for_window "Wine File Manager"); then
    log "ERROR: Winefile not found"
    return 1
  fi
  xdotool windowactivate "$win_id"
  sleep 1
  
  # 1. Mouse (relative deterministic)
  # Click File menu area directly to avoid CV false positives on repeated tree/list textures.
  if test_relative_click "$win_id" 24 36 "winefile_file_rel" 1 1; then
      log "Winefile Mouse: PASS"
  else
      log "Winefile Mouse: FAIL"
      mouse_result="fail"
      failed=1
  fi
  xdotool key --window "$win_id" Escape
  sleep 0.5
  xdotool windowactivate "$win_id"
  sleep 0.2
  
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
      keyboard_result="fail"
      failed=1
  fi
  
  xdotool windowclose "$win_id"
  sleep 1
  WINEFILE_MOUSE_RESULT="$mouse_result"
  WINEFILE_KEYBOARD_RESULT="$keyboard_result"
  return "$failed"
}

# Run Suite
cleanup
if [ "${TRACE_BISECT:-1}" = "1" ] && [ -x "/scripts/diagnostics/diagnose-input-trace.sh" ]; then
  log "=== Trace Bisect ==="
  if /scripts/diagnostics/diagnose-input-trace.sh; then
    TRACE_BISECT_RESULT="pass"
  else
    log "Trace bisect failed"
    TRACE_BISECT_RESULT="fail"
  fi
else
  TRACE_BISECT_RESULT="skipped"
fi

NOTEPAD_MOUSE_RESULT="fail"
NOTEPAD_KEYBOARD_RESULT="fail"
REGEDIT_MOUSE_RESULT="fail"
REGEDIT_KEYBOARD_RESULT="fail"
WINEFILE_MOUSE_RESULT="fail"
WINEFILE_KEYBOARD_RESULT="fail"

FAIL_COUNT=0
if ! test_notepad; then FAIL_COUNT=$((FAIL_COUNT + 1)); fi
if ! test_regedit; then FAIL_COUNT=$((FAIL_COUNT + 1)); fi
if ! test_winefile; then FAIL_COUNT=$((FAIL_COUNT + 1)); fi
if [ "$TRACE_BISECT_RESULT" = "fail" ]; then FAIL_COUNT=$((FAIL_COUNT + 1)); fi

cat > "$SUMMARY_JSON" <<EOF
{
  "trace_bisect": "$TRACE_BISECT_RESULT",
  "notepad": {"mouse": "$NOTEPAD_MOUSE_RESULT", "keyboard": "$NOTEPAD_KEYBOARD_RESULT"},
  "regedit": {"mouse": "$REGEDIT_MOUSE_RESULT", "keyboard": "$REGEDIT_KEYBOARD_RESULT"},
  "winefile": {"mouse": "$WINEFILE_MOUSE_RESULT", "keyboard": "$WINEFILE_KEYBOARD_RESULT"},
  "fail_count": $FAIL_COUNT
}
EOF

log "Suite summary written to $SUMMARY_JSON"
log "Suite completed with fail_count=$FAIL_COUNT"
if [ "$FAIL_COUNT" -gt 0 ]; then
  exit 1
fi
