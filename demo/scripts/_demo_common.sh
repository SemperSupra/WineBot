#!/usr/bin/env bash
# _demo_common.sh — Shared functions for all WineBot demo scripts
# Source ONCE at the top of each demo after `set -u`:
#   SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
#   source "$SCRIPT_DIR/_demo_common.sh"
#   init_session

# ── Guard against double-sourcing ──────────────────────────────────────────────
[ -z "${_DEMO_COMMON_LOADED:-}" ] || return 0
_DEMO_COMMON_LOADED=1

# ── Constants ──────────────────────────────────────────────────────────────────
readonly API_URL="${API_URL:-http://localhost:8000}"
readonly CONTAINER="${WB_CONTAINER:-compose-winebot-interactive-1}"
readonly CV_SIDECAR_URL="${CV_SIDECAR_URL:-http://localhost:8001}"
readonly PREFIX="/wineprefix/drive_c"
readonly PIPE="//wineprefix/drive_c/dialog_handler/pipe.txt"
readonly BAT_PATH="${PREFIX}/__cmd.bat"

# ── Session globals (set by init_session) ──────────────────────────────────────
TOKEN=""
SESSION=""
SESSDIR=""
CT=""
SNAP_INDEX=0
CV_WATCHER_PID=""
CV_WATCHER_SOURCE=""   # "sidecar" | "container" | ""
ANALYSIS_DIR=""
EXPECTED_STATES=""

# ═══════════════════════════════════════════════════════════════════════════════
#  Core — Session & API
# ═══════════════════════════════════════════════════════════════════════════════

detect_token() {
  if [ -n "${API_TOKEN:-}" ]; then
    TOKEN="$API_TOKEN"
    return
  fi
  # 1. Try container token files (most common)
  TOKEN=$(MSYS_NO_PATHCONV=1 docker exec "$CONTAINER" sh -c \
    'cat /tmp/winebot_api_token 2>/dev/null || cat /winebot-shared/winebot_api_token 2>/dev/null' \
    2>/dev/null | tr -d '[:space:]' || true)
  if [ -n "$TOKEN" ]; then
    return
  fi
  # 2. Try OS credential store (Windows Credential Manager / macOS Keychain / Linux libsecret)
  TOKEN=$(python3 -c "
import sys
try:
    import keyring
    token = keyring.get_password('winebot', 'api-token')
    if token:
        print(token)
except Exception:
    pass
" 2>/dev/null || echo "")
  if [ -n "$TOKEN" ]; then
    echo "  Using API token from OS credential store" >&2
    return
  fi
  echo "ERROR: Cannot detect API token" >&2
  echo "  Set API_TOKEN env var, or run: winebot-credential.py import-token" >&2
  exit 1
}

api_get() {
  curl -sfS -H "X-API-Key: $TOKEN" "$API_URL$1" 2>/dev/null
}

api_post() {
  curl -sfS -X POST -H "X-API-Key: $TOKEN" -H "Content-Type: application/json" \
    -d "$2" "$API_URL$1" 2>/dev/null
}

init_session() {
  detect_token

  SESSION=$(api_get "/lifecycle/status" | grep -o '"session_id":[[:space:]]*"[^"]*"' | head -1 | sed 's/.*"\([^"]*\)"$/\1/')
  if [ -z "$SESSION" ]; then
    echo "ERROR: Could not detect session ID — is WineBot running?" >&2
    exit 1
  fi
  SESSDIR="/artifacts/sessions/$SESSION"
  ANALYSIS_DIR="${SESSDIR}/analysis"
  EXPECTED_STATES="${ANALYSIS_DIR}/expected_states.jsonl"

  # Create analysis directory for diagnostic artifacts
  MSYS_NO_PATHCONV=1 docker exec "$CONTAINER" mkdir -p "${ANALYSIS_DIR}" 2>/dev/null
  MSYS_NO_PATHCONV=1 docker exec "$CONTAINER" chown -R winebot:winebot "${ANALYSIS_DIR}" 2>/dev/null
  # Init expected_states.jsonl with a header entry
  MSYS_NO_PATHCONV=1 docker exec "$CONTAINER" sh -c \
    "echo '{\"kind\":\"expected_states_init\",\"session\":\"${SESSION}\",\"t_ms\":$(python3 -c 'import time; print(int(time.time()*1000))' 2>/dev/null || echo 0)}' > '${EXPECTED_STATES}'" 2>/dev/null

  CT=$(curl -s -X POST -H "X-API-Key: $TOKEN" "$API_URL/sessions/$SESSION/control/challenge" \
    | grep -o '"token":[[:space:]]*"[^"]*"' | sed 's/.*"\([^"]*\)"$/\1/')
  api_post "/sessions/$SESSION/control/grant" \
    "{\"lease_seconds\":7200,\"user_ack\":true,\"challenge_token\":\"$CT\"}" > /dev/null

  # Auto-start CV watcher — try sidecar first, fall back to in-container
  CV_WATCHER_SOURCE=""
  CV_WATCHER_PID=""

  if curl -sf "$CV_SIDECAR_URL/health" > /dev/null 2>&1; then
    # Sidecar is available — start live CV watcher
    echo "  Starting CV watcher via sidecar ($CV_SIDECAR_URL)..."
    CV_WATCHER_SOURCE="sidecar"
    # The sidecar needs to reach the WineBot API on the Docker bridge gateway.
    # host.docker.internal resolves to Docker Desktop's VM proxy (unreliable for
    # container-to-container routing). 172.17.0.1 is the default Linux bridge gateway.
    local sidecar_api_url
    if [ "$API_URL" = "http://localhost:8000" ] || [ "$API_URL" = "http://127.0.0.1:8000" ]; then
      sidecar_api_url="http://172.17.0.1:8000"
    else
      sidecar_api_url="$API_URL"
    fi
    curl -s -X POST "$CV_SIDECAR_URL/watch/start" \
      -H "Content-Type: application/json" \
      -d "{\"api_url\":\"$sidecar_api_url\",\"api_token\":\"$TOKEN\",\"session_dir\":\"$SESSDIR\",\"interval\":1.0}" \
      > /dev/null 2>&1 || true
    echo "  CV watcher: sidecar watching desktop @ 1fps (via $sidecar_api_url)"
  else
    # Fall back to in-container cv-watcher.py
    local watcher_script="/scripts/diagnostics/cv-watcher.py"
    if MSYS_NO_PATHCONV=1 docker exec "$CONTAINER" test -f "$watcher_script" 2>/dev/null; then
      echo "  Starting CV watcher in container (sidecar not available)..."
      CV_WATCHER_SOURCE="container"
      MSYS_NO_PATHCONV=1 docker exec "$CONTAINER" sh -c "
        nohup python3 '${watcher_script}' --watch --duration 600 \
          --output-dir '${ANALYSIS_DIR}/cv' \
          --api-url '${API_URL}' \
          > '${ANALYSIS_DIR}/cv-watcher.log' 2>&1 &
        echo \$! > /tmp/cv_watcher.pid
      " 2>/dev/null
      CV_WATCHER_PID=$(MSYS_NO_PATHCONV=1 docker exec "$CONTAINER" cat /tmp/cv_watcher.pid 2>/dev/null || echo "")
      if [ -n "$CV_WATCHER_PID" ]; then
        echo "  CV watcher: container (pid: $CV_WATCHER_PID)"
      fi
    else
      echo "  CV watcher: not available (no sidecar, no cv-watcher.py in container)"
    fi
  fi
}

ensure_dirs() {
  MSYS_NO_PATHCONV=1 docker exec "$CONTAINER" mkdir -p "$PREFIX" 2>/dev/null
  MSYS_NO_PATHCONV=1 docker exec "$CONTAINER" chown -R winebot:winebot "$PREFIX" 2>/dev/null
}

# ═══════════════════════════════════════════════════════════════════════════════
#  Recording — Annotations & Chapters
# ═══════════════════════════════════════════════════════════════════════════════

ann() {
  MSYS_NO_PATHCONV=1 docker exec "$CONTAINER" sh -c \
    "python3 -m automation.recorder annotate --session-dir '$SESSDIR' --text '$1' --kind annotation --source demo" \
    2>/dev/null || true
}

ch() {
  MSYS_NO_PATHCONV=1 docker exec "$CONTAINER" sh -c \
    "python3 -m automation.recorder annotate --session-dir '$SESSDIR' --text '$1' --kind chapter --source demo" \
    2>/dev/null || true
}

# ═══════════════════════════════════════════════════════════════════════════════
#  Diagnostics — Screenshot, Window Inventory, Timing, Expected State
# ═══════════════════════════════════════════════════════════════════════════════

snap() {
  local label="${1:-snapshot}"
  local idx pad_idx
  idx=$((SNAP_INDEX + 1))
  SNAP_INDEX=$idx
  pad_idx=$(printf "%03d" "$idx")
  local snap_file="snap_${pad_idx}_$(echo "$label" | tr ' /' '__').png"

  # Capture screenshot
  curl -s -H "X-API-Key: $TOKEN" "$API_URL/automation/screenshot" \
    -o "${ANALYSIS_DIR}/${snap_file}" 2>/dev/null || true

  # Get window inventory
  local windows
  windows=$(api_get "/automation/windows" 2>/dev/null | \
    python3 -c "import sys,json; d=json.load(sys.stdin); [print(w['title']) for w in d.get('windows',[])]" 2>/dev/null || echo "")

  # Write snapshot manifest entry via docker exec (path is inside container)
  local ts_ms
  ts_ms=$(python3 -c "import time; print(int(time.time()*1000))" 2>/dev/null || echo "0")
  local windows_json
  windows_json=$(echo "$windows" | python3 -c "import sys,json; print(json.dumps([l.strip() for l in sys.stdin if l.strip()]))" 2>/dev/null || echo "[]")

  MSYS_NO_PATHCONV=1 docker exec "$CONTAINER" sh -c \
    "echo '{\"t_ms\": $ts_ms, \"kind\": \"snapshot\", \"label\": \"$label\", \"file\": \"$snap_file\", \"windows\": $windows_json}' >> '${ANALYSIS_DIR}/snapshots.jsonl'" 2>/dev/null

  echo "  [SNAP] $label: $(echo "$windows" | head -3 | paste -sd ',' -)"

  # Also enrich with CV element data if sidecar available
  annotate_elements "$label"
}

annotate_elements() {
  local label="${1:-snapshot}"
  local sidecar_healthy
  sidecar_healthy=$(curl -sf "$CV_SIDECAR_URL/health" 2>/dev/null || echo "")

  if [ -z "$sidecar_healthy" ]; then
    return 0  # Sidecar not available, skip enrichment
  fi

  # The enrichment happens in stop_recording() via cv-omni-analyze.py --enrich
  # This function marks the event so it can be enriched later
  local ts_ms
  ts_ms=$(python3 -c "import time; print(int(time.time()*1000))" 2>/dev/null || echo "0")

  # Write a ui_element_expected marker that cv-omni-analyze will fill in
  MSYS_NO_PATHCONV=1 docker exec "$CONTAINER" sh -c "
    python3 -c \"
import json, os
event = {
    't_rel_ms': ${ts_ms},
    'kind': 'ui_element_expected',
    'label': '${label}',
    'source': 'demo',
    'schema_version': '1.0'
}
path = '${ANALYSIS_DIR}/expected_elements.jsonl'
with open(path, 'a') as f:
    f.write(json.dumps(event) + '\n')
\" 2>/dev/null || true
  " 2>/dev/null || true
}

# ═══════════════════════════════════════════════════════════════════════════════
#  CV-Driven Control — use sidecar OCR/YOLO to drive automation
# ═══════════════════════════════════════════════════════════════════════════════

cv_analyze_frame() {
  # Save screenshot inside WineBot container (shared volume with sidecar)
  local snap_container="/artifacts/sessions/${SESSION}/analysis/cv_frame_$$.png"
  MSYS_NO_PATHCONV=1 docker exec "$CONTAINER" sh -c \
    "curl -s -H 'X-API-Key: ${TOKEN}' http://localhost:8000/screenshot -o '${snap_container}'" 2>/dev/null || true

  # Sidecar reads from same path via shared /artifacts volume
  local result
  result=$(curl -s -X POST "$CV_SIDECAR_URL/analyze" \
    -H "Content-Type: application/json" \
    -d "{\"image_path\":\"$snap_container\"}" 2>/dev/null || echo "{}")

  # Cleanup
  MSYS_NO_PATHCONV=1 docker exec "$CONTAINER" rm -f "$snap_container" 2>/dev/null || true
  echo "$result"
}

cv_find() {
  # Find a UI element by text label. Returns "x,y" coordinates or "".
  local target="$1"
  local frame_json
  frame_json=$(cv_analyze_frame)

  if [ -z "$frame_json" ] || [ "$frame_json" = "{}" ]; then
    return 1
  fi

  # Search OCR text and element detail for the target
  local coords
  coords=$(echo "$frame_json" | python3 -c "
import sys, json
try:
    d = json.loads(sys.stdin.read())
except:
    sys.exit(1)

target = '${target}'.lower()

# Search key_text for matches
for t in d.get('key_text', []):
    if target in t.lower():
        # Found in text — look for nearby interactive element
        for e in d.get('element_detail', []):
            if e.get('interactive'):
                b = e['bbox']
                print(f'{b[0]+b[2]//2},{b[1]+b[3]//2}')
                sys.exit(0)
        # No interactive element found — use first element's center
        for e in d.get('element_detail', []):
            b = e['bbox']
            print(f'{b[0]+b[2]//2},{b[1]+b[3]//2}')
            sys.exit(0)

# Search click targets
for name, pos in d.get('click_targets', {}).items():
    if target in name.lower():
        print(f'{pos[0]},{pos[1]}')
        sys.exit(0)

sys.exit(1)
" 2>/dev/null || echo "")

  if [ -n "$coords" ]; then
    echo "$coords"
    return 0
  fi
  return 1
}

cv_click() {
  # Click a UI element by text label. Uses CV to find it, then clicks.
  local label="$1"
  local window_title="${2:-}"
  local max_retries="${3:-5}"

  echo "  [CV-CLICK] Looking for '$label'..."
  local coords found i
  found=""
  for i in $(seq 1 "$max_retries"); do
    coords=$(cv_find "$label")
    if [ -n "$coords" ]; then
      found="$coords"
      break
    fi
    echo "    Retry $i/$max_retries — '$label' not found yet..."
    sleep 0.5
  done

  if [ -z "$found" ]; then
    echo "  [CV-CLICK] FAILED: '$label' not found after $max_retries retries"
    return 1
  fi

  local x="${found%,*}"
  local y="${found#*,}"
  echo "  [CV-CLICK] '$label' at ($x, $y)"

  local payload="{\"x\":$x,\"y\":$y,\"button\":1"
  if [ -n "$window_title" ]; then
    payload="$payload,\"window_title\":\"$window_title\""
  fi
  payload="$payload}"

  api_post "/input/mouse/click" "$payload" > /dev/null
  sleep 0.3
  return 0
}

cv_wait() {
  # Wait until a window matching the title substring appears.
  # Uses xdotool for reliable title matching (API /windows returns N/A for many windows).
  local window_substr="$1"
  local timeout="${2:-30}"

  echo "  [CV-WAIT] Waiting for '$window_substr' (timeout=${timeout}s)..."
  local i found
  for i in $(seq 1 "$timeout"); do
    found=$(MSYS_NO_PATHCONV=1 docker exec "$CONTAINER" sh -c \
      "xdotool search --name '${window_substr}' 2>/dev/null | head -1" 2>/dev/null || echo "")
    if [ -n "$found" ]; then
      local title
      title=$(MSYS_NO_PATHCONV=1 docker exec "$CONTAINER" xdotool getwindowname "$found" 2>/dev/null || echo "$window_substr")
      echo "  [CV-WAIT] Found: '$title' after ${i}s"
      return 0
    fi
    sleep 1
  done
  echo "  [CV-WAIT] TIMEOUT: '$window_substr' not found after ${timeout}s"
  return 1
}

cv_verify_text() {
  # Check if specific text is visible on screen via OCR. Returns 0 if found.
  local expected_text="$1"
  local frame_json
  frame_json=$(cv_analyze_frame)

  local found
  found=$(echo "$frame_json" | python3 -c "
import sys, json
try:
    d = json.loads(sys.stdin.read())
except:
    d = {}
for t in d.get('key_text', []):
    if '${expected_text}'.lower() in t.lower():
        print('FOUND')
        sys.exit(0)
print('')
" 2>/dev/null || echo "")
  [ -n "$found" ] && return 0 || return 1
}

cv_verify_element() {
  # Check if a UI element (button, text_field, etc.) is visible. Returns 0 if found.
  local element_type="$1"  # button, text_field, dialog, text_area, etc.
  local frame_json
  frame_json=$(cv_analyze_frame)

  local count
  count=$(echo "$frame_json" | python3 -c "
import sys, json
try:
    d = json.loads(sys.stdin.read())
except:
    d = {}
matches = [e for e in d.get('element_detail', []) if e.get('type') == '${element_type}']
print(len(matches))
" 2>/dev/null || echo "0")
  [ "$count" -gt 0 ] && return 0 || return 1
}

bench() {
  local label="$1"
  shift
  local t_start t_end duration
  t_start=$(python3 -c "import time; print(int(time.time()*1000))" 2>/dev/null || echo "0")

  if [ $# -gt 0 ]; then
    "$@"
    local rc=$?
  else
    local rc=0
  fi

  t_end=$(python3 -c "import time; print(int(time.time()*1000))" 2>/dev/null || echo "0")
  duration=$((t_end - t_start))
  echo "  [BENCH] $label: ${duration}ms"
  MSYS_NO_PATHCONV=1 docker exec "$CONTAINER" sh -c \
    "echo '{\"kind\": \"bench\", \"label\": \"$label\", \"t_start_ms\": $t_start, \"t_end_ms\": $t_end, \"duration_ms\": $duration, \"exit_code\": $rc}' >> '${ANALYSIS_DIR}/bench.jsonl'" 2>/dev/null
  return $rc
}

ann_expect() {
  local label="$1"
  local expected_window="${2:-}"

  # Write regular annotation too
  ann "$label"

  # Write expected-state assertion via docker exec (path is inside container)
  local ts_ms
  ts_ms=$(python3 -c "import time; print(int(time.time()*1000))" 2>/dev/null || echo "0")
  MSYS_NO_PATHCONV=1 docker exec "$CONTAINER" sh -c \
    "echo '{\"t_ms\": $ts_ms, \"kind\": \"expected_state\", \"label\": \"$label\", \"expected_window\": \"$expected_window\"}' >> '${EXPECTED_STATES}'" 2>/dev/null
}

# ═══════════════════════════════════════════════════════════════════════════════
#  File Operations
# ═══════════════════════════════════════════════════════════════════════════════

verify_file() {
  MSYS_NO_PATHCONV=1 docker exec "$CONTAINER" sh -c \
    "test -f $1 && echo EXISTS \$(wc -c < $1)bytes || echo MISSING" 2>/dev/null
}

vf() { verify_file "$@"; }

check() {
  MSYS_NO_PATHCONV=1 docker exec "$CONTAINER" sh -c \
    "test -f $1 && echo 'PASS' || echo 'FAIL'" 2>/dev/null
}

write_file() {
  local path="$1" content="$2"
  MSYS_NO_PATHCONV=1 docker exec "$CONTAINER" sh -c \
    "echo '$content' > '$path' && chown winebot:winebot '$path'" 2>/dev/null
}

# ═══════════════════════════════════════════════════════════════════════════════
#  Download & Install
# ═══════════════════════════════════════════════════════════════════════════════

linux_dl() {
  local url="$1" dest="$2"
  MSYS_NO_PATHCONV=1 docker exec "$CONTAINER" python3 -c "
import urllib.request, shutil, os

url = '${url}'
dest = '${dest}'
fname = url.rsplit('/', 1)[-1].split('?')[0]
cache_dir = '/wineprefix/drive_c/.winebot_cache'
cache_path = f'{cache_dir}/{fname}'

os.makedirs(cache_dir, exist_ok=True)
try: shutil.chown(cache_dir, 'winebot', 'winebot')
except: pass

if os.path.exists(cache_path) and os.path.getsize(cache_path) > 1000:
    shutil.copy(cache_path, dest)
    try: shutil.chown(dest, 'winebot', 'winebot')
    except: pass
    print(f'  Cached: {os.path.getsize(dest)} bytes (from .winebot_cache)')
else:
    urllib.request.urlretrieve(url, dest)
    shutil.copy(dest, cache_path)
    try:
        shutil.chown(dest, 'winebot', 'winebot')
        shutil.chown(cache_path, 'winebot', 'winebot')
    except: pass
    print(f'  Downloaded: {os.path.getsize(dest)} bytes (cached for reuse)')
" 2>/dev/null
}

wine_install() {
  local exe="$1" flags="${2:-/S}"
  MSYS_NO_PATHCONV=1 docker exec "$CONTAINER" sh -c "
    gosu winebot env DISPLAY=:99 WINEPREFIX=/wineprefix WINEDEBUG=-all \
    wine '$exe' '$flags' 2>/dev/null &
    PID=\$!
    for i in \$(seq 1 30); do
      if ps -p \$PID > /dev/null 2>&1; then sleep 1; else echo '  Installer exited'; break; fi
    done
  "
}

wine_msi_install() {
  local msi="$1"
  MSYS_NO_PATHCONV=1 docker exec "$CONTAINER" sh -c "
    gosu winebot env DISPLAY=:99 WINEPREFIX=/wineprefix WINEDEBUG=-all \
    wine msiexec /i '$msi' /quiet /qn 2>/dev/null &
    PID=\$!
    for i in \$(seq 1 30); do
      if ps -p \$PID > /dev/null 2>&1; then sleep 1; else echo '  msiexec exited'; break; fi
    done
  "
}

wine_msi_uninstall() {
  local msi="$1"
  MSYS_NO_PATHCONV=1 docker exec "$CONTAINER" sh -c "
    gosu winebot env DISPLAY=:99 WINEPREFIX=/wineprefix WINEDEBUG=-all \
    wine msiexec /x '$msi' /quiet /qn 2>/dev/null &
    sleep 5
  "
}

wine_cmd() {
  local cmd="$1"
  MSYS_NO_PATHCONV=1 docker exec "$CONTAINER" sh -c "
    gosu winebot env DISPLAY=:99 WINEPREFIX=/wineprefix WINEDEBUG=-all \
    wine cmd.exe /c '$cmd' 2>/dev/null
  "
}

# ═══════════════════════════════════════════════════════════════════════════════
#  Pipe Protocol (AHK Dialog Replacement)
# ═══════════════════════════════════════════════════════════════════════════════

pipe_cmd() {
  MSYS_NO_PATHCONV=1 docker exec "$CONTAINER" su -s /bin/sh winebot -c \
    "echo '$1' > '$PIPE'" 2>/dev/null
}

pipe_read() {
  MSYS_NO_PATHCONV=1 docker exec "$CONTAINER" su -s /bin/sh winebot -c \
    "cat '$PIPE' 2>/dev/null" || true
}

pipe_wait() {
  local pattern="$1" timeout="${2:-15}"
  local i resp
  for i in $(seq 1 "$timeout"); do
    resp=$(pipe_read)
    if echo "$resp" | grep -q "$pattern"; then
      echo "$resp"
      return 0
    fi
    sleep 0.5
  done
  return 1
}

# ═══════════════════════════════════════════════════════════════════════════════
#  Batch Script & Input Wrappers
# ═══════════════════════════════════════════════════════════════════════════════

bat() {
  local content="$1"
  MSYS_NO_PATHCONV=1 docker exec "$CONTAINER" sh -c "cat > ${BAT_PATH} << 'BATEOF'
${content}
BATEOF
chown winebot:winebot ${BAT_PATH}"
  MSYS_NO_PATHCONV=1 docker exec "$CONTAINER" sh -c \
    "gosu winebot env DISPLAY=:99 WINEPREFIX=/wineprefix WINEDEBUG=-all wine cmd.exe /c 'C:\\\\__cmd.bat' 2>/dev/null"
}

click_notepad() {
  api_post "/input/mouse/click" '{"x":300,"y":300,"button":1,"window_title":"Notepad"}' > /dev/null
}

type_text() {
  api_post "/input/key" "{\"keys\":\"$1\",\"window_title\":\"$2\"}" > /dev/null
}

press_key() {
  api_post "/input/key" "{\"keys\":\"$1\",\"window_title\":\"$2\"}" > /dev/null
}

# ═══════════════════════════════════════════════════════════════════════════════
#  AHK Handler Setup
# ═══════════════════════════════════════════════════════════════════════════════

setup_ahk_handler() {
  local with_watcher="${1:-0}"

  MSYS_NO_PATHCONV=1 docker exec "$CONTAINER" rm -rf //wineprefix/drive_c/dialog_handler 2>/dev/null
  MSYS_NO_PATHCONV=1 docker exec "$CONTAINER" mkdir -p //wineprefix/drive_c/dialog_handler //wineprefix/drive_c/artifacts 2>/dev/null
  MSYS_NO_PATHCONV=1 docker exec "$CONTAINER" chown -R winebot:winebot //wineprefix/drive_c/dialog_handler //wineprefix/drive_c/artifacts 2>/dev/null
  MSYS_NO_PATHCONV=1 docker cp automation/core/dialog_replacement.ahk "$CONTAINER://wineprefix/drive_c/dr.ahk" 2>/dev/null
  MSYS_NO_PATHCONV=1 docker exec "$CONTAINER" chown winebot:winebot //wineprefix/drive_c/dr.ahk 2>/dev/null

  # Launch AHK pipe dialog handler
  MSYS_NO_PATHCONV=1 docker exec "$CONTAINER" sh -c '
    gosu winebot env DISPLAY=:99 WINEPREFIX=/wineprefix WINEDEBUG=-all nohup ahk C:/dr.ahk > /wineprefix/drive_c/dh.log 2>&1 &' 2>/dev/null
  sleep 5
  echo "  Pipe handler: $(pipe_read)"

  if [ "$with_watcher" = "1" ]; then
    MSYS_NO_PATHCONV=1 docker cp automation/core/dialog_watcher.ahk "$CONTAINER://wineprefix/drive_c/dw.ahk" 2>/dev/null
    MSYS_NO_PATHCONV=1 docker exec "$CONTAINER" chown winebot:winebot //wineprefix/drive_c/dw.ahk 2>/dev/null
    api_post "/apps/run" '{"path":"ahk","args":"C:/dw.ahk","detach":true}' > /dev/null
    sleep 3
    local watcher_count
    watcher_count=$(MSYS_NO_PATHCONV=1 docker exec "$CONTAINER" sh -c \
      'ps aux | grep dw.ahk | grep -v grep | grep -v start.exe | wc -l' 2>/dev/null)
    echo "  Watcher procs: $watcher_count"
    ann "Dialog watcher active — auto-closes stray Save As/Error dialogs"
  fi
}

# ═══════════════════════════════════════════════════════════════════════════════
#  QA Counters
# ═══════════════════════════════════════════════════════════════════════════════

PASS=0
FAIL=0

pass() {
  PASS=$((PASS + 1))
  echo "  ✅ PASS: $1"
}

fail() {
  FAIL=$((FAIL + 1))
  echo "  ❌ FAIL: $1"
}

# ═══════════════════════════════════════════════════════════════════════════════
#  Footer — Stop Recording + Smart Trim
# ═══════════════════════════════════════════════════════════════════════════════

stop_recording() {
  # Stop CV watcher if running
  if [ -n "$CV_WATCHER_SOURCE" ]; then
    echo ""
    echo "--- Post-Run CV Analysis ---"

    if [ "$CV_WATCHER_SOURCE" = "container" ] && [ -n "$CV_WATCHER_PID" ]; then
      MSYS_NO_PATHCONV=1 docker exec "$CONTAINER" sh -c "kill '$CV_WATCHER_PID' 2>/dev/null; rm -f /tmp/cv_watcher.pid" 2>/dev/null || true
      sleep 1

      # Run cv-analyze.py on the watcher output
      local watcher_log="${ANALYSIS_DIR}/cv/watcher.jsonl"
      if MSYS_NO_PATHCONV=1 docker exec "$CONTAINER" test -f "$watcher_log" 2>/dev/null; then
        MSYS_NO_PATHCONV=1 docker exec "$CONTAINER" sh -c "
          if [ -f /scripts/diagnostics/cv-analyze.py ]; then
            python3 /scripts/diagnostics/cv-analyze.py '${watcher_log}'
          fi
        " 2>/dev/null || true
      fi
    elif [ "$CV_WATCHER_SOURCE" = "sidecar" ]; then
      # Stop sidecar watcher
      local watch_result
      watch_result=$(curl -s -X POST "$CV_SIDECAR_URL/watch/stop" 2>/dev/null || echo "")
      local watch_frames
      watch_frames=$(echo "$watch_result" | python3 -c "import sys,json; print(json.load(sys.stdin).get('total_frames',0))" 2>/dev/null || echo "0")
      echo "  CV sidecar: watcher stopped ($watch_frames frames captured)"
      echo "  Watcher data: ${ANALYSIS_DIR}/cv/watcher.jsonl"
    fi
  fi

  # ── Annotation Enrichment — merge CV element data into event stream ─────
  echo ""
  echo "--- Annotation Enrichment ---"

  # Try enrichment via sidecar (preferred — full OCR/detection pipeline)
  if curl -sf "$CV_SIDECAR_URL/health" > /dev/null 2>&1; then
    echo "  Sidecar available — submitting enrichment batch..."
    local video_path="${SESSDIR}/video_001.mkv"
    if MSYS_NO_PATHCONV=1 docker exec "$CONTAINER" test -f "$video_path" 2>/dev/null; then
      local enrich_job
      enrich_job=$(curl -s -X POST "$CV_SIDECAR_URL/batch" \
        -H "Content-Type: application/json" \
        -d "{\"video_path\":\"$video_path\",\"frame_interval\":1.0,\"enrich\":true,\"session_dir\":\"$SESSDIR\"}" \
        2>/dev/null || echo "")
      local job_id
      job_id=$(echo "$enrich_job" | python3 -c "import sys,json; print(json.load(sys.stdin).get('job_id',''))" 2>/dev/null || echo "")
      if [ -n "$job_id" ]; then
        echo "  Enrichment job submitted: $job_id (polling up to 30s)..."
        _poll_count=0
        _poll_status=""
        while [ $_poll_count -lt 30 ]; do
          _poll_count=$((_poll_count + 1))
          _poll_status=$(curl -s "$CV_SIDECAR_URL/batch/$job_id" 2>/dev/null | python3 -c "import sys,json; print(json.load(sys.stdin).get('status',''))" 2>/dev/null || echo "")
          if [ "$_poll_status" = "complete" ] || [ "$_poll_status" = "failed" ]; then
            echo "  Enrichment: $_poll_status"
            break
          fi
          sleep 1
        done
      fi
    fi
  elif MSYS_NO_PATHCONV=1 docker exec "$CONTAINER" test -f /scripts/diagnostics/cv-omni-analyze.py 2>/dev/null; then
    # Fall back to in-container enrichment
    echo "  Running in-container enrichment..."
    MSYS_NO_PATHCONV=1 docker exec "$CONTAINER" sh -c "
      python3 /scripts/diagnostics/cv-omni-analyze.py --session-dir '${SESSDIR}' --enrich 2>&1
    " 2>/dev/null || true
  else
    echo "  Enrichment skipped (no sidecar, no cv-omni-analyze.py in container)"
    echo "  Expected elements recorded in: ${ANALYSIS_DIR}/expected_elements.jsonl"
    echo "  Run offline: python3 scripts/diagnostics/cv-omni-analyze.py --session-dir ${SESSDIR} --enrich"
  fi

  # Run expected-state assertions if any were declared
  local expect_lines
  expect_lines=$(MSYS_NO_PATHCONV=1 docker exec "$CONTAINER" sh -c \
    "test -f '${EXPECTED_STATES}' && wc -l < '${EXPECTED_STATES}' || echo 0" 2>/dev/null)
  expect_lines="${expect_lines:-0}"
  if [ "$expect_lines" -gt 1 ] 2>/dev/null; then
    echo ""
    echo "--- Expected-State Assertions ---"
    echo "  ${expect_lines} state assertions recorded"

    # Check if we have watcher data for verification
    local watcher_jsonl="${ANALYSIS_DIR}/cv/watcher.jsonl"
    local has_watcher
    has_watcher=$(MSYS_NO_PATHCONV=1 docker exec "$CONTAINER" sh -c \
      "test -f '${watcher_jsonl}' && echo 1 || echo 0" 2>/dev/null)
    has_watcher="${has_watcher:-0}"

    if [ "$has_watcher" = "1" ]; then
      echo "  CV watcher data available — verifying assertions..."
      # demo-expect.py is in scripts/diagnostics/ relative to the project root
      # _demo_common.sh is in demo/scripts/ — project root is two dirs up
      local project_root
      project_root="$(cd "$SCRIPT_DIR/../.." && pwd)"
      local session_host_path="${project_root}/artifacts/sessions/${SESSION}"
      local expect_script="${project_root}/scripts/diagnostics/demo-expect.py"
      if [ -f "$expect_script" ]; then
        python3 "$expect_script" \
          --session-dir "${session_host_path}" --tolerance 10.0 2>/dev/null || true
      else
        echo "  (demo-expect.py not available on host — run manually)"
      fi
    else
      echo "  (no CV watcher data — assertions saved for later verification)"
      echo "  Expected states: ${EXPECTED_STATES}"
    fi
  fi

  # Print benchmark summary
  local bench_log="${ANALYSIS_DIR}/bench.jsonl"
  local bench_count
  bench_count=$(MSYS_NO_PATHCONV=1 docker exec "$CONTAINER" sh -c \
    "test -f '${bench_log}' && wc -l < '${bench_log}' || echo 0" 2>/dev/null)
  bench_count="${bench_count:-0}"
  if [ "$bench_count" -gt 0 ] 2>/dev/null; then
    echo ""
    echo "--- Performance Benchmarks ---"
    MSYS_NO_PATHCONV=1 docker exec "$CONTAINER" sh -c \
      "python3 -c \"
import json
with open('${bench_log}') as f:
    benchmarks = [json.loads(l) for l in f if l.strip()]
for b in benchmarks:
    print(f\\\"  {b['label']:40s} {b['duration_ms']:>6}ms  (exit={b.get('exit_code','?')})\\\")
\"" 2>/dev/null || true
  fi

  # Print snapshot summary
  local snap_log="${ANALYSIS_DIR}/snapshots.jsonl"
  local snap_count
  snap_count=$(MSYS_NO_PATHCONV=1 docker exec "$CONTAINER" sh -c \
    "test -f '${snap_log}' && wc -l < '${snap_log}' || echo 0" 2>/dev/null)
  snap_count="${snap_count:-0}"
  if [ "$snap_count" -gt 0 ] 2>/dev/null; then
    echo ""
    echo "--- Screenshot Snapshots ---"
    echo "  ${snap_count} diagnostic screenshots saved → ${ANALYSIS_DIR}/"
  fi

  # Stop recording
  api_post "/recording/stop" '{}' 2>/dev/null || true
  sleep 2

  # Smart trim the video
  local trim_script
  trim_script="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)/_trim.sh"
  if [ -f "$trim_script" ]; then
    source "$trim_script"
    smart_trim "$SESSDIR"
  else
    echo "  (_trim.sh not found — skipping smart trim)" >&2
  fi

  # Copy trimmed output to host
  # Use BASH_SOURCE to find the calling demo script name
  local demo_name
  demo_name="demo"
  # Walk up the BASH_SOURCE stack to find the actual demo script
  local _src
  for _src in "${BASH_SOURCE[@]:1}"; do
    case "$(basename "$_src")" in
      _demo_common.sh|_trim.sh|run-cv-analysis.sh) continue ;;
      *) demo_name="$(basename "$_src" .sh)"; break ;;
    esac
  done
  # Fallback: use $0 if it's a demo script
  if [ "$demo_name" = "demo" ] && [ -n "${0:-}" ]; then
    case "$(basename "${0:-}" .sh)" in bash|sh|_*) ;; *) demo_name="$(basename "${0}" .sh)" ;; esac
  fi

  echo ""
  echo "--- Copying Output (${demo_name}) ---"
  local container="${WB_CONTAINER:-compose-winebot-interactive-1}"
  # Use Windows-style path — MSYS2 mangles /c/Users/... to C:\c\Users\...
  # Use pwd -W to get C:/Users/... format, then add ../output/<name>.mkv
  local out_dir
  out_dir="$(cd "$SCRIPT_DIR/../output" 2>/dev/null && pwd -W 2>/dev/null)"
  out_dir="${out_dir:-${SCRIPT_DIR}/../output}"
  if [ ! -d "$out_dir" ]; then
    echo "  WARNING: Output directory not found: $out_dir"
    return
  fi

  local mkv_path="${out_dir}/${demo_name}.mkv"
  local gif_path="${out_dir}/${demo_name}.gif"
  local vtt_path="${out_dir}/${demo_name}.vtt"

  # Copy trimmed video — use MSYS_NO_PATHCONV to prevent double-conversion
  if MSYS_NO_PATHCONV=1 docker cp "$container:/tmp/trimmed.mkv" "$mkv_path" 2>/dev/null; then
    echo "  Saved: ${demo_name}.mkv ($(wc -c < "$mkv_path" 2>/dev/null | tr -d ' ') bytes)"
  else
    echo "  WARNING: Could not copy /tmp/trimmed.mkv → $mkv_path"
    MSYS_NO_PATHCONV=1 docker exec "$container" test -f /tmp/trimmed.mkv 2>/dev/null || \
      echo "  (source /tmp/trimmed.mkv not found in container)"
  fi

  MSYS_NO_PATHCONV=1 docker cp "$container:/tmp/trimmed.gif" "$gif_path" 2>/dev/null && \
    echo "  Saved: ${demo_name}.gif"

  local vtt_file
  vtt_file=$(MSYS_NO_PATHCONV=1 docker exec "$container" sh -c \
    "ls -t '${SESSDIR}/events_'*.vtt 2>/dev/null | head -1" 2>/dev/null)
  if [ -n "$vtt_file" ]; then
    MSYS_NO_PATHCONV=1 docker cp "$container:$vtt_file" "$vtt_path" 2>/dev/null && \
      echo "  Saved: ${demo_name}.vtt"
  fi
}

# Ensure a clean desktop before running a demo.
# Kills application windows from prior demos that would pollute the recording.
# Stops and restarts recording for a clean video segment.
fresh_session() {
  # Need token first since init_session hasn't run yet
  if [ -z "$TOKEN" ]; then
    if [ -n "${API_TOKEN:-}" ]; then
      TOKEN="$API_TOKEN"
    else
      TOKEN=$(MSYS_NO_PATHCONV=1 docker exec "$CONTAINER" sh -c \
        'cat /tmp/winebot_api_token 2>/dev/null || cat /winebot-shared/winebot_api_token 2>/dev/null' \
        2>/dev/null | tr -d '[:space:]' || true)
    fi
  fi

  echo "  Cleaning desktop for fresh demo..."

  # Kill all application windows from prior demos (preserve system windows)
  MSYS_NO_PATHCONV=1 docker exec "$CONTAINER" sh -c "
    # Kill known app processes
    for p in notepad.exe vlc.exe notepad++.exe supertux2.exe; do
      wineserver -k \$p 2>/dev/null || true
    done
    # Close application windows via xdotool (skip system windows)
    for title in 'Notepad' 'VLC' 'SuperTux' 'Save As' 'Error' 'Warning' \
                'WineBot Save Dialog' 'Registry' 'cmd' '7-Zip' 'WinSpy' \
                'Winefile' 'Regedit' 'Open' 'Browse' 'Confirm' 'Help' 'About'; do
      xdotool search --name \"\$title\" 2>/dev/null | while read wid; do
        xdotool windowclose \"\$wid\" 2>/dev/null || xdotool windowkill \"\$wid\" 2>/dev/null || true
      done
    done
    # Kill all but system processes
    pkill -f 'notepad.exe' 2>/dev/null || true
    pkill -f 'vlc.exe' 2>/dev/null || true
    pkill -f 'notepad++.exe' 2>/dev/null || true
    pkill -f 'supertux2.exe' 2>/dev/null || true
    pkill -f '7zFM.exe' 2>/dev/null || true

    # Wait for windows to actually close
    sleep 3
  " 2>/dev/null || true

  # Restart recording for a clean video segment
  local current
  current=$(curl -sfS -H "X-API-Key: $TOKEN" "$API_URL/lifecycle/status" 2>/dev/null | \
    python3 -c "import sys,json; print(json.load(sys.stdin).get('session_id',''))" 2>/dev/null || echo "")
  if [ -n "$current" ]; then
    curl -sfS -X POST -H "X-API-Key: $TOKEN" -H "Content-Type: application/json" \
      -d '{}' "$API_URL/recording/stop" > /dev/null 2>&1 || true
    sleep 2
    curl -sfS -X POST -H "X-API-Key: $TOKEN" -H "Content-Type: application/json" \
      -d '{}' "$API_URL/recording/start" > /dev/null 2>&1 || true
    sleep 3
  fi
  echo "  Desktop cleaned, recording restarted"
}

print_copy_instructions() {
  local name="${1:-demo}"
  echo ""
  echo "To save:"
  echo "  docker cp ${CONTAINER}:/tmp/trimmed.mkv demo/output/${name}.mkv"
  echo "  docker cp ${CONTAINER}:/tmp/trimmed.gif demo/output/${name}.gif"
  echo "  docker cp ${CONTAINER}:${SESSDIR}/events_001.vtt demo/output/${name}.vtt"
}
