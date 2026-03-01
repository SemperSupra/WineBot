#!/usr/bin/env bash
set -euo pipefail

session_dir=""
if [ -n "${WINEBOT_SESSION_DIR:-}" ]; then
  session_dir="$WINEBOT_SESSION_DIR"
elif [ -f /tmp/winebot_current_session ]; then
  session_dir="$(cat /tmp/winebot_current_session)"
fi

if [ -z "$session_dir" ]; then
  session_dir="/tmp/winebot_session_unknown"
fi

log_dir="${session_dir}/logs/openbox"
mkdir -p "$log_dir"

ts="$(date -u +%Y%m%dT%H%M%SZ)"
log_file="${log_dir}/${ts}_windows_explorer_focus.log"

{
  echo "[$(date -u +%Y-%m-%dT%H:%M:%SZ)] Openbox menu: Windows Explorer (focus existing shell)"
  echo "Command: /scripts/internal/openbox-focus-desktop.sh"
} >>"$log_file"

target_window=""
if command -v xdotool >/dev/null 2>&1; then
  target_window="$(xdotool search --name 'Desktop' 2>/dev/null | head -n1 || true)"
  if [ -z "$target_window" ]; then
    target_window="$(xdotool search --name 'explorer.exe' 2>/dev/null | head -n1 || true)"
  fi
fi

if [ -n "$target_window" ]; then
  {
    echo "Action: focus window id $target_window"
  } >>"$log_file"
  xdotool windowactivate --sync "$target_window" >>"$log_file" 2>&1 || true
  exit 0
fi

{
  echo "Action: no existing desktop/explorer window found; no new explorer process launched."
} >>"$log_file"
exit 0
