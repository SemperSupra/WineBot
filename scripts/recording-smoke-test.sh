#!/usr/bin/env bash
set -euo pipefail

BASE_URL="${BASE_URL:-${1:-http://localhost:8000}}"
API_TOKEN="${API_TOKEN:-}"
SESSION_ROOT="${SESSION_ROOT:-/artifacts/sessions}"

PERF_START_MS="${PERF_START_MS:-2000}"
PERF_PAUSE_MS="${PERF_PAUSE_MS:-1500}"
PERF_RESUME_MS="${PERF_RESUME_MS:-1500}"
PERF_STOP_MS="${PERF_STOP_MS:-8000}"

auth_args=()
if [ -n "$API_TOKEN" ]; then
  auth_args=(-H "X-API-Key: $API_TOKEN")
fi

now_ms() {
  python3 - <<'PY'
import time
print(int(time.time() * 1000))
PY
}

json_field_into() {
  local __var="$1"
  local key="$2"
  local raw="$3"
  local value
  if ! value="$(RAW="$raw" python3 - "$key" <<'PY'
import json
import os
import sys

raw = os.environ.get("RAW", "")
if not raw.strip():
    sys.stderr.write("json_field: empty input\n")
    sys.exit(1)

try:
    data = json.loads(raw)
except json.JSONDecodeError as exc:
    sys.stderr.write(f"json_field: invalid JSON: {exc}\n")
    sys.exit(1)

key = sys.argv[1]
value = data
for part in key.split("."):
    if isinstance(value, dict):
        value = value.get(part)
    else:
        value = None
        break
if isinstance(value, bool):
    print("true" if value else "false")
elif value is None:
    print("")
else:
    print(value)
PY
  )"; then
    echo "Failed to read JSON field '$key'." >&2
    exit 1
  fi
  printf -v "$__var" '%s' "$value"
}

api_get_into() {
  local __var="$1"
  local path="$2"
  local resp
  if ! resp="$(curl -s --fail "${auth_args[@]}" "${BASE_URL}${path}")"; then
    echo "API GET failed: ${BASE_URL}${path}" >&2
    exit 1
  fi
  if [ -z "$resp" ]; then
    echo "API GET empty response: ${BASE_URL}${path}" >&2
    exit 1
  fi
  printf -v "$__var" '%s' "$resp"
}

api_post_into() {
  local __var="$1"
  local path="$2"
  local resp
  if ! resp="$(curl -s --fail -X POST "${auth_args[@]}" "${BASE_URL}${path}")"; then
    echo "API POST failed: ${BASE_URL}${path}" >&2
    exit 1
  fi
  if [ -z "$resp" ]; then
    echo "API POST empty response: ${BASE_URL}${path}" >&2
    exit 1
  fi
  printf -v "$__var" '%s' "$resp"
}

api_post_json_into() {
  local __var="$1"
  local endpoint="$2"
  local body="$3"
  local resp
  if ! resp="$(curl -s --fail -X POST "${auth_args[@]}" -H 'Content-Type: application/json' \
    -d "$body" "${BASE_URL}${endpoint}")"; then
    echo "API POST failed: ${BASE_URL}${endpoint}" >&2
    exit 1
  fi
  if [ -z "$resp" ]; then
    echo "API POST empty response: ${BASE_URL}${endpoint}" >&2
    exit 1
  fi
  printf -v "$__var" '%s' "$resp"
}

await_state() {
  local expected="$1"
  local timeout="${2:-10}"
  local attempt
  for attempt in $(seq 1 "$((timeout * 10))"); do
    local health
    local state
    api_get_into health "/health/recording"
    json_field_into state "state" "$health"
    if [ "$state" = "$expected" ]; then
      return 0
    fi
    sleep 0.1
  done
  echo "Expected state '$expected' but last state was '$state'." >&2
  return 1
}

assert_perf() {
  local action="$1"
  local elapsed="$2"
  local threshold="$3"
  if [ "$elapsed" -gt "$threshold" ]; then
    echo "Recording ${action} too slow: ${elapsed}ms > ${threshold}ms" >&2
    return 1
  fi
}

wait_for_file() {
  local path="$1"
  local timeout="${2:-10}"
  local attempt
  for attempt in $(seq 1 "$((timeout * 10))"); do
    if [ -s "$path" ]; then
      return 0
    fi
    sleep 0.1
  done
  echo "Expected file not found: $path" >&2
  return 1
}

mkdir -p "$SESSION_ROOT"

echo "Recording API smoke test (base: ${BASE_URL})..."

api_get_into health "/health/recording"
json_field_into enabled "enabled" "$health"
if [ "$enabled" != "true" ]; then
  echo "Recording API disabled in /health/recording." >&2
  exit 1
fi

# Ensure clean state
api_post_into _stop_resp "/recording/stop" >/dev/null 2>&1 || true
await_state "idle" 10

start_body="{\"session_root\":\"$SESSION_ROOT\",\"new_session\":true}"
start_ms="$(now_ms)"
api_post_json_into start_resp "/recording/start" "$start_body"
start_elapsed="$(( $(now_ms) - start_ms ))"
assert_perf "start" "$start_elapsed" "$PERF_START_MS"

json_field_into start_status "status" "$start_resp"
json_field_into session_dir "session_dir" "$start_resp"
json_field_into segment "segment" "$start_resp"
if [ "$start_status" != "started" ] || [ -z "$session_dir" ] || [ -z "$segment" ]; then
  echo "Start response invalid: $start_resp" >&2
  exit 1
fi

await_state "recording" 10

pause_ms="$(now_ms)"
api_post_into pause_resp "/recording/pause"
pause_elapsed="$(( $(now_ms) - pause_ms ))"
assert_perf "pause" "$pause_elapsed" "$PERF_PAUSE_MS"
json_field_into pause_status "status" "$pause_resp"
if [ "$pause_status" != "paused" ]; then
  echo "Pause response invalid: $pause_resp" >&2
  exit 1
fi
await_state "paused" 10

api_post_into id_pause_resp "/recording/pause"
json_field_into id_pause_status "status" "$id_pause_resp"
if [ "$id_pause_status" != "already_paused" ]; then
  echo "Expected already_paused, got: $id_pause_resp" >&2
  exit 1
fi

resume_ms="$(now_ms)"
api_post_into resume_resp "/recording/resume"
resume_elapsed="$(( $(now_ms) - resume_ms ))"
assert_perf "resume" "$resume_elapsed" "$PERF_RESUME_MS"
json_field_into resume_status "status" "$resume_resp"
if [ "$resume_status" != "resumed" ]; then
  echo "Resume response invalid: $resume_resp" >&2
  exit 1
fi
await_state "recording" 10

api_post_into id_resume_resp "/recording/resume"
json_field_into id_resume_status "status" "$id_resume_resp"
if [ "$id_resume_status" != "already_recording" ]; then
  echo "Expected already_recording, got: $id_resume_resp" >&2
  exit 1
fi

stop_ms="$(now_ms)"
api_post_into stop_resp "/recording/stop"
stop_elapsed="$(( $(now_ms) - stop_ms ))"
assert_perf "stop" "$stop_elapsed" "$PERF_STOP_MS"
json_field_into stop_status "status" "$stop_resp"
if [ "$stop_status" != "stopped" ]; then
  echo "Stop response invalid: $stop_resp" >&2
  exit 1
fi
await_state "idle" 10

segment_suffix="$(printf '%03d' "$segment")"
final_video="${session_dir}/video_${segment_suffix}.mkv"
wait_for_file "$final_video" 10

api_post_into id_stop_resp "/recording/stop"
json_field_into id_stop_status "status" "$id_stop_resp"
if [ "$id_stop_status" != "already_stopped" ]; then
  echo "Expected already_stopped, got: $id_stop_resp" >&2
  exit 1
fi

start_body="{\"session_root\":\"$SESSION_ROOT\",\"new_session\":false}"
api_post_json_into start2_resp "/recording/start" "$start_body"
json_field_into segment2 "segment" "$start2_resp"
if [ -z "$segment2" ] || [ "$segment2" -le "$segment" ]; then
  echo "Expected segment increment, got: $start2_resp" >&2
  exit 1
fi
await_state "recording" 10
api_post_into _stop_resp2 "/recording/stop" >/dev/null
await_state "idle" 10
segment2_suffix="$(printf '%03d' "$segment2")"
final_video2="${session_dir}/video_${segment2_suffix}.mkv"
wait_for_file "$final_video2" 10

echo "Recording API smoke test OK."
