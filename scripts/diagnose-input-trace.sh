#!/usr/bin/env bash
set -euo pipefail

if [ "$(id -u)" = "0" ] && command -v gosu >/dev/null 2>&1; then
  exec gosu winebot "$0" "$@"
fi

usage() {
  cat <<'EOF'
Usage: scripts/diagnose-input-trace.sh [options]

Run input tracing diagnostics to bisect the input stack.

Options:
  --api-url URL        API base URL (default: http://localhost:8000)
  --layers CSV         Layers to test: x11,x11_core,windows,client,network (default: x11,x11_core,windows,client,network)
  --log-dir DIR        Override diagnostics log directory
  --menu-offset N      Y offset from window top for menu click (default: 45)
  --menu-x N           X offset from window left for menu click (default: 40)
  --windows-debug-keys CSV  Windows debug keys (default: vk41,vk42,LButton)
  --windows-debug-ms N      Windows debug sample ms (default: 50)
  --x11-core-trace N        Enable core xinput test tracing (default: 1)
  --wine-debug N            Enable Wine debug logging (default: 1)
  --wine-debug-channels STR Wine debug channels (default: +event,+win)
  --wine-debug-reset N      Restart Notepad when wine debug enabled (default: 1)
  --wine-debug-include-server N  Include +server in Wine debug (default: 1)
  --wine-input-observer N   Enable Wine input observer (default: 1)
  --wine-input-keys CSV     Wine input observer keys (default: VK_LBUTTON,VK_A,VK_B,VK_MENU)
  --wine-input-duration N   Wine input observer duration seconds (default: 120)
  --wine-input-interval-ms N Wine input observer interval ms (default: 50)
  --wine-hook-observer N    Enable Wine hook observer (default: 1)
  --wine-hook-duration N    Wine hook observer duration seconds (default: 180)
  --wine-hook-sample-ms N   Wine hook observer sample ms (default: 200)
  --no-network         Skip network (VNC) probe
  --no-client          Skip client probe
  --no-windows         Skip Windows trace probe
  --no-x11             Skip X11 trace probe
  --no-x11-core        Skip X11 core trace layer
EOF
}

API_URL="${API_URL:-http://localhost:8000}"
TRACE_LAYERS="${TRACE_LAYERS:-x11,x11_core,windows,client,network}"
LOG_DIR="${LOG_DIR:-}"
SKIP_NETWORK=0
SKIP_CLIENT=0
SKIP_WINDOWS=0
SKIP_X11=0
SKIP_X11_CORE=0
MENU_OFFSET="${MENU_OFFSET:-45}"
MENU_X="${MENU_X:-40}"
WINDOWS_DEBUG_KEYS="${WINDOWS_DEBUG_KEYS:-vk41,vk42,LButton}"
WINDOWS_DEBUG_SAMPLE_MS="${WINDOWS_DEBUG_SAMPLE_MS:-50}"
X11_CORE_TRACE="${X11_CORE_TRACE:-1}"
WINEDEBUG_TRACE="${WINEDEBUG_TRACE:-1}"
WINEDEBUG_CHANNELS="${WINEDEBUG_CHANNELS:-+event,+win}"
WINEDEBUG_RESET="${WINEDEBUG_RESET:-1}"
WINEDEBUG_INCLUDE_SERVER="${WINEDEBUG_INCLUDE_SERVER:-1}"
WINE_INPUT_OBSERVER="${WINE_INPUT_OBSERVER:-1}"
WINE_INPUT_OBSERVER_KEYS="${WINE_INPUT_OBSERVER_KEYS:-VK_LBUTTON,VK_A,VK_B,VK_MENU}"
WINE_INPUT_OBSERVER_DURATION="${WINE_INPUT_OBSERVER_DURATION:-120}"
WINE_INPUT_OBSERVER_INTERVAL_MS="${WINE_INPUT_OBSERVER_INTERVAL_MS:-50}"
WINE_HOOK_OBSERVER="${WINE_HOOK_OBSERVER:-1}"
WINE_HOOK_OBSERVER_DURATION="${WINE_HOOK_OBSERVER_DURATION:-180}"
WINE_HOOK_OBSERVER_SAMPLE_MS="${WINE_HOOK_OBSERVER_SAMPLE_MS:-200}"
export DISPLAY="${DISPLAY:-:99}"

while [ $# -gt 0 ]; do
  case "$1" in
    --api-url)
      API_URL="${2:-}"
      shift 2
      ;;
    --layers)
      TRACE_LAYERS="${2:-}"
      shift 2
      ;;
    --log-dir)
      LOG_DIR="${2:-}"
      shift 2
      ;;
    --menu-offset)
      MENU_OFFSET="${2:-}"
      shift 2
      ;;
    --menu-x)
      MENU_X="${2:-}"
      shift 2
      ;;
    --windows-debug-keys)
      WINDOWS_DEBUG_KEYS="${2:-}"
      shift 2
      ;;
    --windows-debug-ms)
      WINDOWS_DEBUG_SAMPLE_MS="${2:-}"
      shift 2
      ;;
    --x11-core-trace)
      X11_CORE_TRACE="${2:-}"
      shift 2
      ;;
    --wine-debug)
      WINEDEBUG_TRACE="${2:-}"
      shift 2
      ;;
    --wine-debug-channels)
      WINEDEBUG_CHANNELS="${2:-}"
      shift 2
      ;;
    --wine-debug-reset)
      WINEDEBUG_RESET="${2:-}"
      shift 2
      ;;
    --wine-debug-include-server)
      WINEDEBUG_INCLUDE_SERVER="${2:-}"
      shift 2
      ;;
    --wine-input-observer)
      WINE_INPUT_OBSERVER="${2:-}"
      shift 2
      ;;
    --wine-input-keys)
      WINE_INPUT_OBSERVER_KEYS="${2:-}"
      shift 2
      ;;
    --wine-input-duration)
      WINE_INPUT_OBSERVER_DURATION="${2:-}"
      shift 2
      ;;
    --wine-input-interval-ms)
      WINE_INPUT_OBSERVER_INTERVAL_MS="${2:-}"
      shift 2
      ;;
    --wine-hook-observer)
      WINE_HOOK_OBSERVER="${2:-}"
      shift 2
      ;;
    --wine-hook-duration)
      WINE_HOOK_OBSERVER_DURATION="${2:-}"
      shift 2
      ;;
    --wine-hook-sample-ms)
      WINE_HOOK_OBSERVER_SAMPLE_MS="${2:-}"
      shift 2
      ;;
    --no-network)
      SKIP_NETWORK=1
      shift
      ;;
    --no-client)
      SKIP_CLIENT=1
      shift
      ;;
    --no-windows)
      SKIP_WINDOWS=1
      shift
      ;;
    --no-x11)
      SKIP_X11=1
      shift
      ;;
    --no-x11-core)
      SKIP_X11_CORE=1
      shift
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

session_dir=""
if [ -n "${WINEBOT_SESSION_DIR:-}" ]; then
  session_dir="$WINEBOT_SESSION_DIR"
elif [ -f /tmp/winebot_current_session ]; then
  session_dir="$(cat /tmp/winebot_current_session)"
fi
if [ -z "$LOG_DIR" ]; then
  if [ -n "$session_dir" ]; then
    LOG_DIR="${session_dir}/logs/diagnostics"
  else
    LOG_DIR="/tmp/winebot_diagnostics"
  fi
fi
mkdir -p "$LOG_DIR" 2>/dev/null || true
if [ ! -w "$LOG_DIR" ]; then
  LOG_DIR="/tmp/winebot_diagnostics"
  mkdir -p "$LOG_DIR" 2>/dev/null || true
fi
LOG_FILE="${LOG_DIR}/input_trace_bisect.log"

log() {
  if [ -w "$(dirname "$LOG_FILE")" ]; then
    printf '[%s] %s\n' "$(date -u +%Y-%m-%dT%H:%M:%SZ)" "$*" | tee -a "$LOG_FILE"
  else
    printf '[%s] %s\n' "$(date -u +%Y-%m-%dT%H:%M:%SZ)" "$*"
  fi
}

layer_enabled() {
  local layer="$1"
  echo ",${TRACE_LAYERS}," | grep -qi ",${layer}," && return 0
  return 1
}

if [ "$WINEDEBUG_TRACE" = "1" ] && [ "$WINEDEBUG_INCLUDE_SERVER" = "1" ]; then
  case ",${WINEDEBUG_CHANNELS}," in
    *,+server,*)
      ;;
    *)
      WINEDEBUG_CHANNELS="${WINEDEBUG_CHANNELS},+server"
      ;;
  esac
fi

api_headers=()
if [ -n "${API_TOKEN:-}" ]; then
  api_headers+=("-H" "X-API-Key: ${API_TOKEN}")
fi

api_get() {
  local path="$1"
  curl -sS "${api_headers[@]}" "${API_URL}${path}"
}

api_post() {
  local path="$1"
  curl -sS -X POST "${api_headers[@]}" "${API_URL}${path}"
}

api_post_json() {
  local path="$1"
  local json="$2"
  curl -sS -X POST "${api_headers[@]}" -H "Content-Type: application/json" -d "$json" "${API_URL}${path}"
}

now_ms() {
  python3 - <<'PY'
import time
print(int(time.time() * 1000))
PY
}

json_escape() {
  python3 - <<'PY'
import json
import sys
print(json.dumps(sys.stdin.read())[1:-1])
PY
}

trace_has_event() {
  local source="$1"
  local types_csv="$2"
  local since_ms="$3"
  python3 - <<PY
import json
import os
import urllib.parse
import urllib.request

api_url = os.environ.get("API_URL")
api_token = os.environ.get("API_TOKEN")
source = ${source@Q}
types_csv = ${types_csv@Q}
since_ms = int(${since_ms@Q})

params = {"limit": "200", "since_epoch_ms": str(since_ms)}
if source:
    params["source"] = source
url = api_url + "/input/events?" + urllib.parse.urlencode(params)
req = urllib.request.Request(url)
if api_token:
    req.add_header("X-API-Key", api_token)
try:
    with urllib.request.urlopen(req) as resp:
        data = json.loads(resp.read().decode("utf-8"))
except Exception:
    print("0")
    raise SystemExit(0)

want = set([t for t in types_csv.split(",") if t])
found = 0
for event in data.get("events", []):
    if event.get("event") in want:
        found = 1
        break
print("1" if found else "0")
PY
}

hook_has_event() {
  local types_csv="$1"
  local since_ms="$2"
  HOOK_TYPES="${types_csv}" HOOK_SINCE="${since_ms}" python3 - <<'PY'
import json
import os
import sys

types_csv = os.environ.get("HOOK_TYPES", "")
since_ms = int(os.environ.get("HOOK_SINCE", "0") or 0)
path = os.environ.get("WINE_HOOK_OBSERVER_LOG", "")

if not path or not os.path.exists(path):
    print("0")
    raise SystemExit(0)

want = {t for t in types_csv.split(",") if t}
found = 0
try:
    with open(path, "r") as f:
        for line in f:
            try:
                event = json.loads(line)
            except Exception:
                continue
            try:
                ts = int(event.get("timestamp_epoch_ms", 0))
            except Exception:
                continue
            if ts < since_ms:
                continue
            if event.get("event") in want:
                found = 1
                break
except Exception:
    pass
print("1" if found else "0")
PY
}

dump_hook_samples() {
  local since_ms="$1"
  local label="$2"
  if [ -z "${wine_hook_observer_log:-}" ] || [ ! -f "$wine_hook_observer_log" ]; then
    return
  fi
  HOOK_SINCE="${since_ms}" WINE_HOOK_OBSERVER_LOG="${wine_hook_observer_log}" python3 - <<'PY' | while read -r line; do
import json
import os

path = os.environ.get("WINE_HOOK_OBSERVER_LOG", "")
since_ms = int(os.environ.get("HOOK_SINCE", "0") or 0)
want = ("focus_state", "queue_state")
events = {w: [] for w in want}
if not path or not os.path.exists(path):
    raise SystemExit(0)
with open(path, "r") as f:
    for line in f:
        try:
            ev = json.loads(line)
        except Exception:
            continue
        if ev.get("event") not in want:
            continue
        try:
            ts = int(ev.get("timestamp_epoch_ms", 0))
        except Exception:
            continue
        if ts < since_ms:
            continue
        events[ev["event"]].append(ev)

def fmt_focus(ev):
    rect = ev.get("rect") or {}
    return (
        f"focus_state hwnd={ev.get('hwnd')} pid={ev.get('pid')} tid={ev.get('tid')} "
        f"title={ev.get('title')!r} class={ev.get('class')!r} "
        f"rect={rect.get('left')},{rect.get('top')},{rect.get('right')},{rect.get('bottom')}"
    )

def fmt_queue(ev):
    return (
        f"queue_state flags=0x{int(ev.get('queue_flags',0)):04x} "
        f"status=0x{int(ev.get('queue_status',0)):04x} "
        f"last_input_ms_ago={ev.get('last_input_ms_ago')}"
    )

for ev in events["focus_state"][-3:]:
    print(fmt_focus(ev))
for ev in events["queue_state"][-3:]:
    print(fmt_queue(ev))
PY
    log "  ${label}: ${line}"
  done
}

trace_has_field_value() {
  local source="$1"
  local event_type="$2"
  local field_name="$3"
  local field_value="$4"
  local since_ms="$5"
  python3 - <<PY
import json
import os
import urllib.parse
import urllib.request

api_url = os.environ.get("API_URL")
api_token = os.environ.get("API_TOKEN")
source = ${source@Q}
event_type = ${event_type@Q}
field_name = ${field_name@Q}
field_value = ${field_value@Q}
since_ms = int(${since_ms@Q})

params = {"limit": "400", "since_epoch_ms": str(since_ms)}
if source:
    params["source"] = source
url = api_url + "/input/events?" + urllib.parse.urlencode(params)
req = urllib.request.Request(url)
if api_token:
    req.add_header("X-API-Key", api_token)
try:
    with urllib.request.urlopen(req) as resp:
        data = json.loads(resp.read().decode("utf-8"))
except Exception:
    print("0")
    raise SystemExit(0)

found = 0
for event in data.get("events", []):
    if event_type and event.get("event") != event_type:
        continue
    value = event.get(field_name)
    if value is None:
        continue
    if str(value) == str(field_value):
        found = 1
        break
print("1" if found else "0")
PY
}

trace_has_field_pair() {
  local source="$1"
  local event_type="$2"
  local field_name="$3"
  local field_value="$4"
  local field_name2="$5"
  local field_value2="$6"
  local since_ms="$7"
  python3 - <<PY
import json
import os
import urllib.parse
import urllib.request

api_url = os.environ.get("API_URL")
api_token = os.environ.get("API_TOKEN")
source = ${source@Q}
event_type = ${event_type@Q}
field_name = ${field_name@Q}
field_value = ${field_value@Q}
field_name2 = ${field_name2@Q}
field_value2 = ${field_value2@Q}
since_ms = int(${since_ms@Q})

params = {"limit": "400", "since_epoch_ms": str(since_ms)}
if source:
    params["source"] = source
url = api_url + "/input/events?" + urllib.parse.urlencode(params)
req = urllib.request.Request(url)
if api_token:
    req.add_header("X-API-Key", api_token)
try:
    with urllib.request.urlopen(req) as resp:
        data = json.loads(resp.read().decode("utf-8"))
except Exception:
    print("0")
    raise SystemExit(0)

found = 0
for event in data.get("events", []):
    if event_type and event.get("event") != event_type:
        continue
    value = event.get(field_name)
    value2 = event.get(field_name2)
    if value is None or value2 is None:
        continue
    if str(value) == str(field_value) and str(value2) == str(field_value2):
        found = 1
        break
print("1" if found else "0")
PY
}

wait_for_window() {
  local title="$1"
  local win_id=""
  for _ in {1..60}; do
    win_id="$(xdotool search --onlyvisible --name "$title" | head -n 1 || true)"
    if [ -z "$win_id" ]; then
      win_id="$(xdotool search --name "$title" | head -n 1 || true)"
    fi
    if [ -n "$win_id" ]; then
      echo "$win_id"
      return 0
    fi
    sleep 0.5
  done
  return 1
}

ensure_notepad() {
  NOTEPAD_ID=""
  wineboot -u >/dev/null 2>&1 || true
  if [ "$WINEDEBUG_TRACE" = "1" ] && [ "$WINEDEBUG_RESET" = "1" ]; then
    if pgrep -f "notepad.exe" >/dev/null 2>&1; then
      log "Stopping existing Notepad to enable Wine debug capture..."
      pkill -f "notepad.exe" >/dev/null 2>&1 || true
      sleep 1
    fi
  fi
  if ! wmctrl -l | grep -qi "Notepad"; then
    log "Launching Wine Notepad..."
    if [ "$WINEDEBUG_TRACE" = "1" ]; then
      WINEDEBUG_LOG_PATH="${LOG_DIR}/wine_debug_${diag_ts}.log"
      log "Wine debug log: ${WINEDEBUG_LOG_PATH}"
      WINEDEBUG="${WINEDEBUG_CHANNELS}" nohup wine notepad >"${WINEDEBUG_LOG_PATH}" 2>&1 </dev/null &
    else
      nohup wine notepad >/dev/null 2>&1 </dev/null &
    fi
  fi
  NOTEPAD_ID="$(wait_for_window "Notepad" || true)"
  if [ -z "$NOTEPAD_ID" ]; then
    if pgrep -f "notepad.exe" >/dev/null 2>&1; then
      log "Notepad process running, but no window detected."
    else
      log "Notepad process not detected."
    fi
  fi
}

summarize_winedebug() {
  if [ "$WINEDEBUG_TRACE" != "1" ]; then
    return
  fi
  if [ -z "$WINEDEBUG_LOG_PATH" ] || [ ! -f "$WINEDEBUG_LOG_PATH" ]; then
    log "Wine debug summary: log missing"
    return
  fi
  local keypresses buttonpresses motion
  keypresses="$(grep -c "KeyPress" "$WINEDEBUG_LOG_PATH" 2>/dev/null || echo "0")"
  buttonpresses="$(grep -c "ButtonPress" "$WINEDEBUG_LOG_PATH" 2>/dev/null || echo "0")"
  motion="$(grep -c "MotionNotify" "$WINEDEBUG_LOG_PATH" 2>/dev/null || echo "0")"
  log "Wine debug summary: KeyPress=${keypresses} ButtonPress=${buttonpresses} Motion=${motion}"
}

start_wine_input_observer() {
  if [ "$WINE_INPUT_OBSERVER" != "1" ]; then
    return
  fi
  if ! command -v winpy >/dev/null 2>&1; then
    log "Wine input observer: winpy not found"
    return
  fi
  if [ ! -f "/scripts/diagnose-wine-input.py" ]; then
    log "Wine input observer: /scripts/diagnose-wine-input.py missing"
    return
  fi
  wine_input_observer_log="${LOG_DIR}/wine_input_observer_${diag_ts}.jsonl"
  log "Wine input observer log: ${wine_input_observer_log}"
  winpy /scripts/diagnose-wine-input.py \
    --out "${wine_input_observer_log}" \
    --duration "${WINE_INPUT_OBSERVER_DURATION}" \
    --interval-ms "${WINE_INPUT_OBSERVER_INTERVAL_MS}" \
    --keys "${WINE_INPUT_OBSERVER_KEYS}" >/dev/null 2>&1 &
  wine_input_observer_pid="$!"
}

stop_wine_input_observer() {
  if [ -n "$wine_input_observer_pid" ]; then
    kill "$wine_input_observer_pid" >/dev/null 2>&1 || true
  fi
}

summarize_wine_input_observer() {
  if [ "$WINE_INPUT_OBSERVER" != "1" ]; then
    return
  fi
  if [ -z "$wine_input_observer_log" ] || [ ! -f "$wine_input_observer_log" ]; then
    log "Wine input observer summary: log missing"
    return
  fi
  python3 - <<'PY' || true
import json
import os

path = os.environ.get("WINE_INPUT_OBSERVER_LOG")
if not path or not os.path.exists(path):
    raise SystemExit(0)
counts = {}
down_counts = {}
with open(path, "r", encoding="utf-8") as f:
    for line in f:
        line = line.strip()
        if not line:
            continue
        try:
            data = json.loads(line)
        except json.JSONDecodeError:
            continue
        key = data.get("key")
        down = data.get("down")
        if key is None:
            continue
        counts[key] = counts.get(key, 0) + 1
        if down:
            down_counts[key] = down_counts.get(key, 0) + 1
if not counts:
    print("Wine input observer summary: no samples")
    raise SystemExit(0)
parts = []
for key in sorted(counts.keys()):
    parts.append(f"{key}:down={down_counts.get(key,0)}/{counts[key]}")
print("Wine input observer summary: " + " ".join(parts))
PY
}

start_wine_hook_observer() {
  if [ "$WINE_HOOK_OBSERVER" != "1" ]; then
    return
  fi
  if ! command -v winpy >/dev/null 2>&1; then
    log "Wine hook observer: winpy not found"
    return
  fi
  if [ ! -f "/scripts/diagnose-wine-hook.py" ]; then
    log "Wine hook observer: /scripts/diagnose-wine-hook.py missing"
    return
  fi
  wine_hook_observer_log="${LOG_DIR}/wine_hook_observer_${diag_ts}.jsonl"
  export WINE_HOOK_OBSERVER_LOG="${wine_hook_observer_log}"
  log "Wine hook observer log: ${wine_hook_observer_log}"
  winpy /scripts/diagnose-wine-hook.py \
    --out "${wine_hook_observer_log}" \
    --duration "${WINE_HOOK_OBSERVER_DURATION}" \
    --sample-ms "${WINE_HOOK_OBSERVER_SAMPLE_MS}" \
    --sample-focus 1 \
    --sample-queue 1 >/dev/null 2>&1 &
  wine_hook_observer_pid="$!"
}

stop_wine_hook_observer() {
  if [ -n "$wine_hook_observer_pid" ]; then
    kill "$wine_hook_observer_pid" >/dev/null 2>&1 || true
  fi
}

summarize_wine_hook_observer() {
  if [ "$WINE_HOOK_OBSERVER" != "1" ]; then
    return
  fi
  if [ -z "$wine_hook_observer_log" ] || [ ! -f "$wine_hook_observer_log" ]; then
    log "Wine hook observer summary: log missing"
    return
  fi
  python3 - <<'PY' || true
import json
import os
from collections import Counter

path = os.environ.get("WINE_HOOK_OBSERVER_LOG")
if not path or not os.path.exists(path):
    raise SystemExit(0)

counts = Counter()
with open(path, "r", encoding="utf-8") as f:
    for line in f:
        line = line.strip()
        if not line:
            continue
        try:
            data = json.loads(line)
        except json.JSONDecodeError:
            continue
        event = data.get("event")
        if event:
            counts[event] += 1

if not counts:
    print("Wine hook observer summary: no events")
    raise SystemExit(0)

parts = ["%s=%s" % (k, v) for k, v in sorted(counts.items())]
print("Wine hook observer summary: " + " ".join(parts))
PY
}

focus_window() {
  local win_id="$1"
  if [ -n "$win_id" ]; then
    xdotool windowactivate "$win_id" || true
    xdotool windowraise "$win_id" || true
    sleep 0.3
  fi
}

capture_window() {
  local win_id="$1"
  local path="$2"
  import -window "$win_id" "$path"
}

compare_images() {
  local a="$1"
  local b="$2"
  compare -metric AE "$a" "$b" null: 2>&1 || true
}

run_mouse_variant() {
  local label="$1"
  local mode="$2"
  log "Test 1${label}: X11 mouse click (${mode})"
  local t0
  t0=$(now_ms)
  local core_master_before="0"
  local core_master_after="0"
  local core_xtest_before="0"
  local core_xtest_after="0"
  if [ -n "$core_pointer_master_log" ]; then
    core_master_before="$(core_line_count "$core_pointer_master_log")"
  fi
  if [ -n "$core_pointer_xtest_log" ]; then
    core_xtest_before="$(core_line_count "$core_pointer_xtest_log")"
  fi
  if [ -n "$notepad_id" ]; then
    base_img="${LOG_DIR}/${diag_ts}_notepad_mouse_${label}_base.png"
    after_img="${LOG_DIR}/${diag_ts}_notepad_mouse_${label}_after.png"
    capture_window "$notepad_id" "$base_img" || true
    xdotool mousemove --window "$notepad_id" "$MENU_X" "$MENU_OFFSET" || true
    case "$mode" in
      move_click)
        xdotool click 1 || true
        ;;
      window_click)
        xdotool click --window "$notepad_id" 1 || true
        ;;
      down_up)
        xdotool mousedown --window "$notepad_id" 1 || true
        sleep 0.05
        xdotool mouseup --window "$notepad_id" 1 || true
        ;;
      *)
        xdotool click 1 || true
        ;;
    esac
    sleep 0.4
    capture_window "$notepad_id" "$after_img" || true
    mouse_diff="$(compare_images "$base_img" "$after_img")"
    log "  app diff pixels (mouse ${mode}): ${mouse_diff}"
    xdotool key --window "$notepad_id" Escape || true
  else
    xdotool mousemove_relative -- 12 8 || true
    xdotool click 1 || true
  fi
  sleep 0.3
  x11_ok="$(trace_has_event "" "button_press,button_release" "$t0")"
  x11_core_ok="0"
  if [ "$SKIP_X11_CORE" -eq 0 ] && layer_enabled "x11_core"; then
    x11_core_ok="$(trace_has_event "x11_core" "button_press,button_release,motion" "$t0")"
  fi
  win_ok="0"
  if [ "$SKIP_WINDOWS" -eq 0 ] && layer_enabled "windows"; then
    win_ok="$(trace_has_event "windows" "mouse_down,mouse_up" "$t0")"
  fi
  hook_ok="0"
  if [ "$WINE_HOOK_OBSERVER" = "1" ] && [ -n "${wine_hook_observer_log:-}" ] && [ -f "$wine_hook_observer_log" ]; then
    hook_ok="$(hook_has_event "mouse_down,mouse_up,mouse_move" "$t0")"
  fi
  if [ -n "$core_pointer_master_log" ]; then
    core_master_after="$(core_line_count "$core_pointer_master_log")"
    core_master_delta=$((core_master_after - core_master_before))
    log "  core pointer master delta=${core_master_delta}"
  fi
  if [ -n "$core_pointer_xtest_log" ]; then
    core_xtest_after="$(core_line_count "$core_pointer_xtest_log")"
    core_xtest_delta=$((core_xtest_after - core_xtest_before))
    log "  core pointer xtest delta=${core_xtest_delta}"
  fi
  log "  trace x11=$x11_ok x11_core=$x11_core_ok windows=$win_ok hook=$hook_ok"
  if [ -n "$WINDOWS_DEBUG_KEYS" ] && [ "$SKIP_WINDOWS" -eq 0 ] && layer_enabled "windows"; then
    debug_button_down="$(trace_has_field_pair "windows" "button_state" "button" "left" "down" "1" "$t0")"
    log "  debug button_state left_down=$debug_button_down"
  fi
  if [ "$x11_ok" = "0" ]; then
    if [ "$x11_core_ok" = "1" ]; then
      log "  DIAG: XI2 missing, X11 core saw events (XI2 trace gap)."
    else
      log "  DIAG: missing at X11 (xdotool -> X11). Check focus/DISPLAY/xdotool."
    fi
  elif [ "$x11_core_ok" = "0" ] && [ "$SKIP_X11_CORE" -eq 0 ] && layer_enabled "x11_core"; then
    log "  DIAG: XI2 ok, X11 core missing (core trace gap)."
  elif [ "$win_ok" = "0" ] && [ "$SKIP_WINDOWS" -eq 0 ] && layer_enabled "windows"; then
    if [ "$hook_ok" = "1" ]; then
      log "  DIAG: Windows trace missing; hook observer saw events (AHK trace issue)."
    else
      log "  DIAG: X11 ok, Windows missing (X11 -> Wine). Check focus/Wine hooks."
    fi
  else
    log "  DIAG: X11 click observed across enabled layers."
  fi
  if [ "$x11_ok" = "1" ]; then
    if [ "${core_master_delta:-0}" -eq 0 ] && [ "${core_xtest_delta:-0}" -eq 0 ]; then
      log "  OBS: XI2 saw events but core xinput test saw none."
    fi
  fi
}

log_active_window() {
  local active_id
  active_id="$(xdotool getactivewindow 2>/dev/null || true)"
  if [ -n "$active_id" ]; then
    local title
    title="$(xdotool getwindowname "$active_id" 2>/dev/null || true)"
    log "Active window: ${active_id} ${title}"
  else
    log "Active window: unknown"
  fi
}

log_window_info() {
  local win_id="$1"
  if [ -z "$win_id" ]; then
    return
  fi
  local title
  title="$(xdotool getwindowname "$win_id" 2>/dev/null || true)"
  local klass
  klass="$(xprop -id "$win_id" WM_CLASS 2>/dev/null || true)"
  log "Window title: ${title}"
  log "Window class: ${klass}"
  xwininfo -id "$win_id" 2>/dev/null | awk '
    /Absolute upper-left X:/ {x=$4}
    /Absolute upper-left Y:/ {y=$4}
    /Width:/ {w=$2}
    /Height:/ {h=$2}
    END {printf "Window geometry: x=%s y=%s w=%s h=%s\n", x, y, w, h}
  ' | while read -r line; do log "$line"; done
}

core_pointer_master_pid=""
core_pointer_xtest_pid=""
core_keyboard_master_pid=""
core_keyboard_xtest_pid=""
core_pointer_master_log=""
core_pointer_master_err=""
core_pointer_xtest_log=""
core_pointer_xtest_err=""
core_keyboard_master_log=""
core_keyboard_master_err=""
core_keyboard_xtest_log=""
core_keyboard_xtest_err=""
WINEDEBUG_LOG_PATH=""
wine_input_observer_pid=""
wine_input_observer_log=""
wine_hook_observer_pid=""
wine_hook_observer_log=""

core_line_count() {
  local path="$1"
  if [ -z "$path" ] || [ ! -f "$path" ]; then
    echo "0"
    return
  fi
  wc -l < "$path" 2>/dev/null || echo "0"
}

start_x11_core_trace() {
  if [ "$X11_CORE_TRACE" = "0" ]; then
    log "X11 core trace: disabled"
    return
  fi
  if ! command -v xinput >/dev/null 2>&1; then
    log "X11 core trace: xinput not found"
    return
  fi
  local pointer_id keyboard_id pointer_xtest_id keyboard_xtest_id
  local xlist
  xlist="$(xinput --list --short 2>/dev/null || true)"
  pointer_id="$(printf '%s\n' "$xlist" | awk '/Virtual core XTEST pointer/ {for (i=1;i<=NF;i++) if ($i ~ /^id=/) {sub("id=","",$i); print $i; exit}}')"
  keyboard_id="$(printf '%s\n' "$xlist" | awk '/Virtual core XTEST keyboard/ {for (i=1;i<=NF;i++) if ($i ~ /^id=/) {sub("id=","",$i); print $i; exit}}')"
  # (Backup to master if XTEST not found)
  [ -z "$pointer_id" ] && pointer_id="$(printf '%s\n' "$xlist" | awk '/Virtual core pointer/ {for (i=1;i<=NF;i++) if ($i ~ /^id=/) {sub("id=","",$i); print $i; exit}}')"
  [ -z "$keyboard_id" ] && keyboard_id="$(printf '%s\n' "$xlist" | awk '/Virtual core keyboard/ {for (i=1;i<=NF;i++) if ($i ~ /^id=/) {sub("id=","",$i); print $i; exit}}')"

  start_core_trace_device() {
    local label="$1"
    local id="$2"
    if [ -z "$id" ]; then
      log "X11 core trace: ${label} id not found"
      return
    fi
    local path="${LOG_DIR}/xinput_${label}.log"
    local err_path="${LOG_DIR}/xinput_${label}.err"
    : > "$path" || true
    : > "$err_path" || true
    xinput test "$id" > "$path" 2> "$err_path" &
    local pid="$!"
    log "X11 core trace ${label} id=${id} pid=${pid}"
    case "$label" in
      pointer_master) core_pointer_master_log="$path"; core_pointer_master_err="$err_path"; core_pointer_master_pid="$pid" ;;
      pointer_xtest) core_pointer_xtest_log="$path"; core_pointer_xtest_err="$err_path"; core_pointer_xtest_pid="$pid" ;;
      keyboard_master) core_keyboard_master_log="$path"; core_keyboard_master_err="$err_path"; core_keyboard_master_pid="$pid" ;;
      keyboard_xtest) core_keyboard_xtest_log="$path"; core_keyboard_xtest_err="$err_path"; core_keyboard_xtest_pid="$pid" ;;
    esac
  }

  start_core_trace_device "pointer_master" "$pointer_id"
  start_core_trace_device "keyboard_master" "$keyboard_id"
}

stop_x11_core_trace() {
  for pid in "$core_pointer_master_pid" "$core_pointer_xtest_pid" "$core_keyboard_master_pid" "$core_keyboard_xtest_pid"; do
    if [ -n "$pid" ]; then
      kill "$pid" >/dev/null 2>&1 || true
    fi
  done
}

log_x11_core_stderr() {
  local label="$1"
  local path="$2"
  if [ -z "$path" ] || [ ! -f "$path" ]; then
    return
  fi
  if [ ! -s "$path" ]; then
    return
  fi
  log "X11 core trace stderr (${label}):"
  tail -n 5 "$path" 2>/dev/null | while read -r line; do log "  ${line}"; done
}

log_x11_core_api_stderr() {
  if [ "$SKIP_X11_CORE" -ne 0 ] || ! layer_enabled "x11_core"; then
    return
  fi
  local stderr_path
  stderr_path=$(python3 - <<'PY' || true
import json
import os
import urllib.parse
import urllib.request

api_url = os.environ.get("API_URL")
api_token = os.environ.get("API_TOKEN")
if not api_url:
    raise SystemExit(0)

url = api_url + "/input/trace/x11core/status"
req = urllib.request.Request(url)
if api_token:
    req.add_header("X-API-Key", api_token)
try:
    with urllib.request.urlopen(req) as resp:
        data = json.loads(resp.read().decode("utf-8"))
except Exception:
    raise SystemExit(0)

log_path = data.get("log_path")
if not log_path:
    raise SystemExit(0)
stderr_path = os.path.join(os.path.dirname(log_path), "input_trace_x11_core.stderr")
print(stderr_path)
PY
  )
  if [ -z "$stderr_path" ] || [ ! -s "$stderr_path" ]; then
    return
  fi
  log "X11 core API stderr:"
  tail -n 5 "$stderr_path" 2>/dev/null | while read -r line; do log "  ${line}"; done
}

start_layers=()
start_trace_layer() {
  local layer="$1"
  case "$layer" in
    x11)
      api_post "/input/trace/start" >/dev/null || true
      start_layers+=("x11")
      ;;
    x11_core)
      api_post "/input/trace/x11core/start" >/dev/null || true
      start_layers+=("x11_core")
      ;;
    windows)
      if [ -n "$WINDOWS_DEBUG_KEYS" ]; then
        debug_json=$(printf '{"debug_keys_csv": "%s", "debug_sample_ms": %s}' \
          "$(printf '%s' "$WINDOWS_DEBUG_KEYS" | json_escape)" \
          "${WINDOWS_DEBUG_SAMPLE_MS}")
        api_post_json "/input/trace/windows/start" "$debug_json" >/dev/null || true
      else
        api_post "/input/trace/windows/start" >/dev/null || true
      fi
      start_layers+=("windows")
      ;;
    client)
      api_post "/input/trace/client/start" >/dev/null || true
      start_layers+=("client")
      ;;
    network)
      api_post "/input/trace/network/start" >/dev/null || true
      start_layers+=("network")
      ;;
  esac
}

stop_trace_layer() {
  local layer="$1"
  case "$layer" in
    x11)
      api_post "/input/trace/stop" >/dev/null || true
      ;;
    x11_core)
      api_post "/input/trace/x11core/stop" >/dev/null || true
      ;;
    windows)
      api_post "/input/trace/windows/stop" >/dev/null || true
      ;;
    client)
      api_post "/input/trace/client/stop" >/dev/null || true
      ;;
    network)
      api_post "/input/trace/network/stop" >/dev/null || true
      ;;
  esac
}

cleanup() {
  for layer in "${start_layers[@]}"; do
    stop_trace_layer "$layer"
  done
  stop_x11_core_trace
  stop_wine_input_observer
  stop_wine_hook_observer
}
trap cleanup EXIT

export API_URL API_TOKEN

log "Starting input trace bisect diagnostics"
if [ -n "$WINDOWS_DEBUG_KEYS" ]; then
  log "Windows debug keys: ${WINDOWS_DEBUG_KEYS} (sample ${WINDOWS_DEBUG_SAMPLE_MS}ms)"
fi
if [ "$WINEDEBUG_TRACE" = "1" ]; then
  log "Wine debug enabled: ${WINEDEBUG_CHANNELS}"
fi
if [ "$WINE_HOOK_OBSERVER" = "1" ]; then
  log "Wine hook sample: ${WINE_HOOK_OBSERVER_SAMPLE_MS}ms"
fi
if command -v xinput >/dev/null 2>&1; then
  log "X11 devices:"
  xinput --list --short 2>/dev/null | while read -r line; do log "$line"; done
fi
if pgrep -af x11vnc >/dev/null 2>&1; then
  log "x11vnc: running"
else
  log "x11vnc: not running"
fi
start_x11_core_trace

if ! api_get "/health" >/dev/null 2>&1; then
  log "ERROR: API not reachable at ${API_URL}"
  exit 1
fi

diag_ts="$(date -u +%Y%m%dT%H%M%SZ)"
notepad_id=""
if [ "$SKIP_X11" -eq 0 ] || [ "$SKIP_WINDOWS" -eq 0 ]; then
  ensure_notepad
  notepad_id="$NOTEPAD_ID"
  if [ -n "$notepad_id" ]; then
    focus_window "$notepad_id"
    log "Notepad window id: ${notepad_id}"
    log_active_window
    log_window_info "$notepad_id"
    start_wine_input_observer
    start_wine_hook_observer
  else
    log "WARNING: Notepad window not found; app-level validation skipped."
    log "Window list:"
    wmctrl -l || true
  fi
fi

if [ "$SKIP_X11" -eq 0 ] && layer_enabled "x11"; then
  start_trace_layer "x11"
else
  log "Skipping X11 trace layer"
fi

if [ "$SKIP_X11_CORE" -eq 0 ] && layer_enabled "x11_core"; then
  start_trace_layer "x11_core"
else
  log "Skipping X11 core trace layer"
fi

if [ "$SKIP_WINDOWS" -eq 0 ] && layer_enabled "windows"; then
  start_trace_layer "windows"
else
  log "Skipping Windows trace layer"
fi

if [ "$SKIP_CLIENT" -eq 0 ] && layer_enabled "client"; then
  start_trace_layer "client"
else
  log "Skipping client trace layer"
fi

if [ "$SKIP_NETWORK" -eq 0 ] && layer_enabled "network"; then
  start_trace_layer "network"
else
  log "Skipping network trace layer"
fi

run_mouse_variant "a" "move_click"
run_mouse_variant "b" "window_click"
run_mouse_variant "c" "down_up"

log "Test 2: X11 key press via xdotool"
t0=$(now_ms)
core_master_before="0"
core_master_after="0"
core_xtest_before="0"
core_xtest_after="0"
if [ -n "$core_keyboard_master_log" ]; then
  core_master_before="$(core_line_count "$core_keyboard_master_log")"
fi
if [ -n "$core_keyboard_xtest_log" ]; then
  core_xtest_before="$(core_line_count "$core_keyboard_xtest_log")"
fi
if [ -n "$notepad_id" ]; then
  base_img="${LOG_DIR}/${diag_ts}_notepad_key_base.png"
  after_img="${LOG_DIR}/${diag_ts}_notepad_key_after.png"
  capture_window "$notepad_id" "$base_img" || true
  xdotool keydown --window "$notepad_id" Alt || true
  xdotool key --window "$notepad_id" f || true
  xdotool keyup --window "$notepad_id" Alt || true
  sleep 0.4
  capture_window "$notepad_id" "$after_img" || true
  key_diff="$(compare_images "$base_img" "$after_img")"
  log "  app diff pixels (keyboard): ${key_diff}"
  xdotool key --window "$notepad_id" Escape || true
else
  xdotool keydown a || true
  sleep 0.2
  xdotool keyup a || true
fi
sleep 0.3
x11_ok="$(trace_has_event "" "key_press,key_release" "$t0")"
x11_core_ok="0"
if [ "$SKIP_X11_CORE" -eq 0 ] && layer_enabled "x11_core"; then
  x11_core_ok="$(trace_has_event "x11_core" "key_press,key_release" "$t0")"
fi
win_ok="0"
if [ "$SKIP_WINDOWS" -eq 0 ] && layer_enabled "windows"; then
  win_ok="$(trace_has_event "windows" "key_down,key_up" "$t0")"
fi
hook_ok="0"
if [ "$WINE_HOOK_OBSERVER" = "1" ] && [ -n "${wine_hook_observer_log:-}" ] && [ -f "$wine_hook_observer_log" ]; then
  hook_ok="$(hook_has_event "key_down,key_up" "$t0")"
fi
if [ -n "$core_keyboard_master_log" ]; then
  core_master_after="$(core_line_count "$core_keyboard_master_log")"
  core_master_delta=$((core_master_after - core_master_before))
  log "  core keyboard master delta=${core_master_delta}"
fi
if [ -n "$core_keyboard_xtest_log" ]; then
  core_xtest_after="$(core_line_count "$core_keyboard_xtest_log")"
  core_xtest_delta=$((core_xtest_after - core_xtest_before))
  log "  core keyboard xtest delta=${core_xtest_delta}"
fi
log "  trace x11=$x11_ok x11_core=$x11_core_ok windows=$win_ok hook=$hook_ok"
if [ "$x11_ok" = "0" ]; then
  if [ "$x11_core_ok" = "1" ]; then
    log "  DIAG: XI2 missing, X11 core saw key events (XI2 trace gap)."
  else
    log "  DIAG: missing at X11 (xdotool -> X11). Check focus/DISPLAY/xdotool."
  fi
elif [ "$x11_core_ok" = "0" ] && [ "$SKIP_X11_CORE" -eq 0 ] && layer_enabled "x11_core"; then
  log "  DIAG: XI2 ok, X11 core missing (core trace gap)."
elif [ "$win_ok" = "0" ] && [ "$SKIP_WINDOWS" -eq 0 ] && layer_enabled "windows"; then
  if [ "$hook_ok" = "1" ]; then
    log "  DIAG: Windows trace missing; hook observer saw key events (AHK trace issue)."
  else
    log "  DIAG: X11 ok, Windows missing (X11 -> Wine). Check focus/Wine hooks."
  fi
else
  log "  DIAG: X11 key observed across enabled layers."
fi
if [ "$x11_ok" = "1" ]; then
  if [ "${core_master_delta:-0}" -eq 0 ] && [ "${core_xtest_delta:-0}" -eq 0 ]; then
    log "  OBS: XI2 saw key events but core xinput test saw none."
  fi
fi

if [ "$SKIP_WINDOWS" -eq 0 ] && layer_enabled "windows"; then
  log "Test 3: Windows input via AHK"
  t0=$(now_ms)
  if [ -n "$notepad_id" ]; then
    focus_window "$notepad_id"
  fi
  if [ -n "$notepad_id" ]; then
    base_img="${LOG_DIR}/${diag_ts}_notepad_ahk_base.png"
    after_img="${LOG_DIR}/${diag_ts}_notepad_ahk_after.png"
    capture_window "$notepad_id" "$base_img" || true
  fi
  ahk_script=$'MouseMove, 220, 220, 0\nClick\nSleep, 200\nSendInput, b\nSleep, 200\nMouseMove, 240, 240, 0\nClick, down\nSleep, 200\nClick, up\n'
  ahk_json=$(printf '{"script": "%s"}' "$(printf '%s' "$ahk_script" | json_escape)")
  api_post_json "/run/ahk" "$ahk_json" >/dev/null || true
  sleep 0.6
  if [ -n "$notepad_id" ] && [ -n "${base_img:-}" ] && [ -n "${after_img:-}" ]; then
    capture_window "$notepad_id" "$after_img" || true
    ahk_diff="$(compare_images "$base_img" "$after_img")"
    log "  app diff pixels (ahk): ${ahk_diff}"
  fi
  win_key_ok="$(trace_has_event "windows" "key_down,key_up" "$t0")"
  win_mouse_ok="$(trace_has_event "windows" "mouse_down,mouse_up" "$t0")"
  hook_key_ok="0"
  hook_mouse_ok="0"
  if [ "$WINE_HOOK_OBSERVER" = "1" ] && [ -n "${wine_hook_observer_log:-}" ] && [ -f "$wine_hook_observer_log" ]; then
    hook_key_ok="$(hook_has_event "key_down,key_up" "$t0")"
    hook_mouse_ok="$(hook_has_event "mouse_down,mouse_up" "$t0")"
  fi
  log "  trace windows key=$win_key_ok mouse=$win_mouse_ok hook_key=$hook_key_ok hook_mouse=$hook_mouse_ok"
  if [ -n "$WINDOWS_DEBUG_KEYS" ]; then
    debug_key_down="$(trace_has_field_pair "windows" "key_state" "vk" "vk42" "down" "1" "$t0")"
    log "  debug key_state vk42_down=$debug_key_down"
  fi
  if [ "$win_key_ok" = "0" ] || [ "$win_mouse_ok" = "0" ]; then
    if [ "$hook_key_ok" = "1" ] || [ "$hook_mouse_ok" = "1" ]; then
      log "  DIAG: Windows trace missing AHK events, but hook observer saw them (AHK trace issue)."
    else
      log "  DIAG: Windows hook missing AHK events. Check AHK hook or Wine input."
    fi
  else
    log "  DIAG: Windows hook captured AHK input."
  fi
  dump_hook_samples "$t0" "hook sample"
fi

if [ "$SKIP_CLIENT" -eq 0 ] && layer_enabled "client"; then
  log "Test 4: Client trace event (noVNC UI)"
  t0=$(now_ms)
  api_post_json "/input/client/event" '{"event":"client_click","origin":"user","tool":"novnc","x":120,"y":140,"button":1}' >/dev/null || true
  sleep 0.2
  client_ok="$(trace_has_event "client" "client_click" "$t0")"
  log "  trace client=$client_ok"
  if [ "$client_ok" = "0" ]; then
    log "  DIAG: client trace missing. Check client trace toggle/UI wiring."
  else
    log "  DIAG: client trace event recorded (does not validate injection)."
  fi
fi

if [ "$SKIP_NETWORK" -eq 0 ] && layer_enabled "network"; then
  log "Test 5: Network trace via VNC proxy"
  t0=$(now_ms)
  VNC_HOST="${VNC_HOST:-127.0.0.1}" VNC_PORT="${VNC_PORT:-5900}" VNC_PASSWORD="${VNC_PASSWORD:-winebot}" python3 - <<'PY' || true
import socket
import struct
import time
import os
import sys
from hashlib import md5

# Robust VNC Probe with Authentication Support
def d3des_encrypt(challenge, password):
    try:
        from cryptography.hazmat.primitives.ciphers import Cipher, algorithms, modes
        from cryptography.hazmat.backends import default_backend
    except ImportError:
        return None # Fallback or fail

    key = bytearray(8)
    pw_bytes = password.encode('latin-1')
    if len(pw_bytes) > 8: pw_bytes = pw_bytes[:8]
    else: pw_bytes = pw_bytes + b'\0' * (8 - len(pw_bytes))
    for i in range(8):
        b = pw_bytes[i]
        b = ((b * 0x0802 & 0x22110) | (b * 0x8020 & 0x88440)) * 0x10101 >> 16
        key[i] = b & 0xFF
    try:
        # Suppress deprecation warnings for TripleDES
        import warnings
        with warnings.catch_warnings():
            warnings.simplefilter("ignore")
            # Try main module first
            if hasattr(algorithms, 'DES'): 
                algo = algorithms.DES(bytes(key))
            else:
                # Try decrepit module or fallback to TripleDES hack
                try:
                    from cryptography.hazmat.decrepit.ciphers.algorithms import TripleDES
                    algo = TripleDES(bytes(key) * 3)
                except ImportError:
                    # Last resort: use deprecated TripleDES from main module if allowed
                    algo = algorithms.TripleDES(bytes(key) * 3)
    except Exception: return None
    cipher = Cipher(algo, modes.ECB(), backend=default_backend())
    return cipher.encryptor().update(challenge)

def vnc_probe(host, port, password):
    sock = socket.create_connection((host, port), timeout=5)
    try:
        ver = sock.recv(12)
        sock.sendall(ver)
        ntypes = sock.recv(1)[0]
        if ntypes == 0: return False
        types = list(sock.recv(ntypes))
        if 2 in types and password:
            sock.sendall(b"\x02")
            challenge = sock.recv(16)
            resp = d3des_encrypt(challenge, password)
            if resp: sock.sendall(resp)
            else: return False
            if struct.unpack(">I", sock.recv(4))[0] != 0: return False
        elif 1 in types:
            sock.sendall(b"\x01")
            if b'3.8' in ver: sock.recv(4)
        else: return False
        sock.sendall(b"\x01") # ClientInit
        init = sock.recv(24)
        name_len = struct.unpack(">I", init[20:24])[0]
        sock.recv(name_len)
        # Mouse Move to 300,300
        sock.sendall(struct.pack(">BBHH", 5, 0, 300, 300))
        time.sleep(0.1)
        # Click
        sock.sendall(struct.pack(">BBHH", 5, 1, 300, 300))
        time.sleep(0.1)
        sock.sendall(struct.pack(">BBHH", 5, 0, 300, 300))
        time.sleep(0.1)
        # Key 'a'
        sock.sendall(struct.pack(">BBHI", 4, 1, 0, 97))
        sock.sendall(struct.pack(">BBHI", 4, 0, 0, 97))
        return True
    finally: sock.close()

host = os.environ.get("VNC_HOST", "127.0.0.1")
ports = [int(os.environ.get("VNC_PORT", "5900")), 5901]
pw = os.environ.get("VNC_PASSWORD", "")
success = False
for port in ports:
    try:
        if vnc_probe(host, port, pw):
            print(f"VNC probe success on port {port}")
            success = True
            break
    except Exception as e:
        print(f"VNC probe failed on port {port}: {e}")

if not success:
    print("VNC probe failed on all ports")
PY
  sleep 0.4
  net_ok="$(trace_has_event "network" "vnc_pointer,vnc_key" "$t0")"
  x11_ok="$(trace_has_event "" "button_press,button_release,key_press,key_release,motion" "$t0")"
  x11_core_ok="0"
  if [ "$SKIP_X11_CORE" -eq 0 ] && layer_enabled "x11_core"; then
    x11_core_ok="$(trace_has_event "x11_core" "button_press,button_release,key_press,key_release,motion" "$t0")"
  fi
  win_ok="0"
  if [ "$SKIP_WINDOWS" -eq 0 ] && layer_enabled "windows"; then
    win_ok="$(trace_has_event "windows" "mouse_down,mouse_up,key_down,key_up" "$t0")"
  fi
  hook_ok="0"
  if [ "$WINE_HOOK_OBSERVER" = "1" ] && [ -n "${wine_hook_observer_log:-}" ] && [ -f "$wine_hook_observer_log" ]; then
    hook_ok="$(hook_has_event "mouse_down,mouse_up,key_down,key_up" "$t0")"
  fi
  log "  trace network=$net_ok x11=$x11_ok x11_core=$x11_core_ok windows=$win_ok hook=$hook_ok"
  if [ "$net_ok" = "0" ]; then
    log "  DIAG: network trace missing. Check ENABLE_VNC and WINEBOT_INPUT_TRACE_NETWORK."
  elif [ "$x11_ok" = "0" ]; then
    if [ "$x11_core_ok" = "1" ]; then
      log "  DIAG: network ok, XI2 missing but X11 core saw events (XI2 trace gap)."
    else
      log "  DIAG: network ok, X11 missing (VNC -> X11). Check x11vnc injection."
    fi
  elif [ "$x11_core_ok" = "0" ] && [ "$SKIP_X11_CORE" -eq 0 ] && layer_enabled "x11_core"; then
    log "  DIAG: network ok, XI2 ok, X11 core missing (core trace gap)."
  elif [ "$win_ok" = "0" ] && [ "$SKIP_WINDOWS" -eq 0 ] && layer_enabled "windows"; then
    if [ "$hook_ok" = "1" ]; then
      log "  DIAG: network+X11 ok, Windows trace missing; hook observer saw events (AHK trace issue)."
    else
      log "  DIAG: network+X11 ok, Windows missing (X11 -> Wine)."
    fi
  else
    log "  DIAG: network input observed across enabled layers."
  fi
fi

summarize_winedebug
if [ -n "$wine_input_observer_log" ]; then
  export WINE_INPUT_OBSERVER_LOG="$wine_input_observer_log"
fi
summarize_wine_input_observer
if [ -n "$wine_hook_observer_log" ]; then
  export WINE_HOOK_OBSERVER_LOG="$wine_hook_observer_log"
fi
summarize_wine_hook_observer
log "Input trace bisect complete. Log saved to ${LOG_FILE}"

log_x11_core_stderr "pointer_master" "$core_pointer_master_err"
log_x11_core_stderr "pointer_xtest" "$core_pointer_xtest_err"
log_x11_core_stderr "keyboard_master" "$core_keyboard_master_err"
log_x11_core_stderr "keyboard_xtest" "$core_keyboard_xtest_err"
log_x11_core_api_stderr
