#!/usr/bin/env bash
set -euo pipefail

usage() {
  cat <<'EOF'
Usage: scripts/diagnose-mouse-input.sh [options]

Automate a mouse/keyboard input check against a Wine Notepad window.
Creates window-only screenshots and compares them to detect menu changes.

Options:
  --display DISPLAY     X11 display (default: :99)
  --menu-offset N       Y offset from window top for menu click (default: 45)
  --label TEXT          Label for output files (default: mouse_input)
EOF
}

display=":99"
menu_offset=45
label="mouse_input"

while [ $# -gt 0 ]; do
  case "$1" in
    --display)
      display="${2:-}"
      shift 2
      ;;
    --menu-offset)
      menu_offset="${2:-}"
      shift 2
      ;;
    --label)
      label="${2:-}"
      shift 2
      ;;
    -h|--help)
      usage
      exit 0
      ;;
    *)
      echo "Unknown option: $1" >&2
      usage
      exit 1
      ;;
  esac
done

export DISPLAY="$display"

session_dir=""
if [ -n "${WINEBOT_SESSION_DIR:-}" ]; then
  session_dir="$WINEBOT_SESSION_DIR"
elif [ -f /tmp/winebot_current_session ]; then
  session_dir="$(cat /tmp/winebot_current_session)"
fi
if [ -z "$session_dir" ]; then
  session_dir="/tmp/winebot_session_unknown"
fi

out_dir="${session_dir}/logs/diagnostics"
if ! mkdir -p "$out_dir" 2>/dev/null; then
  out_dir="/tmp/winebot_diagnostics"
  mkdir -p "$out_dir"
fi

ts="$(date -u +%Y%m%dT%H%M%SZ)"
base="${out_dir}/${ts}_${label}"
log_file="${base}.log"

log() {
  if [ -w "$(dirname "$log_file")" ]; then
    printf '%s\n' "$*" | tee -a "$log_file"
  else
    printf '%s\n' "$*"
  fi
}

log "[$(date -u +%Y-%m-%dT%H:%M:%SZ)] Starting mouse input diagnosis"

ensure_notepad() {
  if ! wmctrl -l | grep -qi "Notepad"; then
    log "Launching Wine Notepad..."
    nohup wine notepad >/dev/null 2>&1 </dev/null &
    sleep 2
  fi
}

ensure_notepad

win_id="$(xdotool search --onlyvisible --name "Notepad" | head -n 1 || true)"
if [ -z "$win_id" ]; then
  log "ERROR: Could not find Notepad window."
  exit 1
fi

xdotool windowactivate "$win_id"
sleep 0.5

read -r win_x win_y win_w win_h < <(
  xwininfo -id "$win_id" | awk '
    /Absolute upper-left X:/ {x=$4}
    /Absolute upper-left Y:/ {y=$4}
    /Width:/ {w=$2}
    /Height:/ {h=$2}
    END {printf "%s %s %s %s\n", x, y, w, h}
  '
)

capture_window() {
  local suffix="$1"
  import -window "$win_id" "${base}_${suffix}.png"
}

compare_images() {
  local a="$1"
  local b="$2"
  local diff
  diff="$(compare -metric AE "$a" "$b" null: 2>&1 || true)"
  echo "$diff"
}

log "Capturing baseline..."
capture_window "baseline"

log "Opening menu via keyboard (Alt+F)..."
xdotool key --window "$win_id" Alt+F
sleep 0.5
capture_window "keyboard_menu"
keyboard_diff="$(compare_images "${base}_baseline.png" "${base}_keyboard_menu.png")"
log "Keyboard diff pixels: ${keyboard_diff}"
xdotool key --window "$win_id" Escape
sleep 0.2

log "Opening menu via mouse click (relative coordinates)..."
mouse_diff="0"
mouse_offset_hit=""
for offset in "$menu_offset" 30 40 50 60 70 80; do
  menu_x=40
  menu_y="$offset"
  log " - trying relative click at (${menu_x}, ${menu_y})"
  xdotool mousemove --sync --window "$win_id" "$menu_x" "$menu_y"
  xdotool click 1
  xdotool click 1
  sleep 0.5
  capture_window "mouse_menu_${offset}"
  mouse_diff="$(compare_images "${base}_baseline.png" "${base}_mouse_menu_${offset}.png")"
  log "   diff pixels: ${mouse_diff}"
  if [ "${mouse_diff}" != "0" ]; then
    mouse_offset_hit="$offset"
    break
  fi
  xdotool key --window "$win_id" Escape
  sleep 0.2
done
if [ -n "$mouse_offset_hit" ]; then
  log "Mouse menu opened with offset ${mouse_offset_hit}."
else
  log "Mouse menu did not open at any tested offsets."
fi
xdotool key --window "$win_id" Escape
sleep 0.2

if [ "${keyboard_diff:-0}" = "0" ]; then
  log "WARNING: Keyboard menu diff is 0. Notepad menu may not be opening."
fi
if [ -z "$mouse_offset_hit" ]; then
  log "WARNING: Mouse menu diff is 0 across tested offsets. Mouse click did not open the menu."
fi

log "Saved screenshots in ${out_dir}"
log "Done."
