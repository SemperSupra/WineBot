#!/usr/bin/env bash
# EXECUTION: IN_CONTAINER — long-running trace stress test; requires Wine+X11+trace layers
# STATUS: LEGACY — manually invoked for soak testing; not part of CI pipeline
set -euo pipefail

API_URL="${API_URL:-http://localhost:8000}"
API_TOKEN="${API_TOKEN:-}"
DURATION_SECONDS="${DURATION_SECONDS:-600}"
INTERVAL_SECONDS="${INTERVAL_SECONDS:-15}"
MAX_LOG_MB="${MAX_LOG_MB:-512}"
MAX_SESSION_MB="${MAX_SESSION_MB:-4096}"
MAX_PID1_RSS_MB="${MAX_PID1_RSS_MB:-2048}"

if [ -z "$API_TOKEN" ]; then
  for token_file in /tmp/winebot_api_token /winebot-shared/winebot_api_token; do
    if [ -f "$token_file" ]; then
      token_value="$(tr -d '[:space:]' < "$token_file" || true)"
      if [ -n "$token_value" ]; then
        API_TOKEN="$token_value"
        break
      fi
    fi
  done
fi

# Do not print hostnames, tokens, raw session paths or user-controlled budgets
# into public CI logs. All visible counters are bounded before reporting.
for setting in DURATION_SECONDS INTERVAL_SECONDS MAX_LOG_MB MAX_SESSION_MB MAX_PID1_RSS_MB; do
  value="${!setting}"
  if [[ ! "$value" =~ ^[0-9]{1,9}$ ]]; then
    echo "[soak] INVALID_CONFIG key=$setting" >&2
    exit 2
  fi
done
if [ "$INTERVAL_SECONDS" -lt 1 ] || [ "$MAX_LOG_MB" -lt 1 ] ||
   [ "$MAX_SESSION_MB" -lt 1 ] || [ "$MAX_PID1_RSS_MB" -lt 1 ]; then
  echo "[soak] INVALID_CONFIG stage=nonpositive_budget" >&2
  exit 2
fi

api_get() {
  local path="$1"
  if [ -n "$API_TOKEN" ]; then
    curl -fs -H "X-API-Key: $API_TOKEN" "${API_URL}${path}"
  else
    curl -fs "${API_URL}${path}"
  fi
}

to_bytes() {
  local mb="$1"
  echo $((mb * 1024 * 1024))
}

echo "[soak] starting trace/recording soak checks"
echo "[soak] duration=${DURATION_SECONDS}s interval=${INTERVAL_SECONDS}s"
echo "[soak] thresholds: logs<=${MAX_LOG_MB}MB session<=${MAX_SESSION_MB}MB pid1_rss<=${MAX_PID1_RSS_MB}MB"

started_at="$(date +%s)"
deadline=$((started_at + DURATION_SECONDS))
max_log_bytes="$(to_bytes "$MAX_LOG_MB")"
max_session_bytes="$(to_bytes "$MAX_SESSION_MB")"
max_pid1_rss_kb=$((MAX_PID1_RSS_MB * 1024))

while [ "$(date +%s)" -lt "$deadline" ]; do
  if ! api_get "/health" >/dev/null; then
    echo "[soak] FAIL stage=health_request" >&2
    exit 1
  fi
  if ! api_get "/health/system" >/dev/null; then
    echo "[soak] FAIL stage=system_health_request" >&2
    exit 1
  fi
  if ! recording_json="$(api_get "/health/recording")"; then
    echo "[soak] FAIL stage=recording_health_request" >&2
    exit 1
  fi
  if ! session_dir="$(python3 -c 'import json,sys; print((json.load(sys.stdin).get("session_dir") or "").strip())' <<<"$recording_json" 2>/dev/null)"; then
    echo "[soak] FAIL stage=recording_metadata_invalid" >&2
    exit 1
  fi

  session_state=absent
  if [ -n "$session_dir" ] && [ -d "$session_dir" ]; then
    session_state=present
    log_dir="${session_dir}/logs"
    log_bytes=0
    session_bytes=0
    if [ -d "$log_dir" ]; then
      if ! log_bytes="$(du -sb "$log_dir" 2>/dev/null | awk '{print $1}')"; then
        echo "[soak] FAIL stage=log_usage_unavailable" >&2
        exit 1
      fi
    fi
    if ! session_bytes="$(du -sb "$session_dir" 2>/dev/null | awk '{print $1}')"; then
      echo "[soak] FAIL stage=session_usage_unavailable" >&2
      exit 1
    fi

    if [ "$log_bytes" -gt "$max_log_bytes" ]; then
      echo "[soak] FAIL: log size ${log_bytes} exceeds ${max_log_bytes}" >&2
      exit 1
    fi
    if [ "$session_bytes" -gt "$max_session_bytes" ]; then
      echo "[soak] FAIL: session size ${session_bytes} exceeds ${max_session_bytes}" >&2
      exit 1
    fi
  fi

  pid1_rss_kb="$(awk '/VmRSS:/ {print $2}' /proc/1/status 2>/dev/null || echo 0)"
  if [ "${pid1_rss_kb:-0}" -gt "$max_pid1_rss_kb" ]; then
    echo "[soak] FAIL: pid1 VmRSS ${pid1_rss_kb}kB exceeds ${max_pid1_rss_kb}kB" >&2
    exit 1
  fi

  now="$(date +%s)"
  elapsed=$((now - started_at))
  echo "[soak] ok elapsed=${elapsed}s session_state=${session_state} pid1_rss_kb=${pid1_rss_kb:-0}"
  sleep "$INTERVAL_SECONDS"
done

echo "[soak] PASS: no threshold violations detected"
