#!/usr/bin/env bash
set -euo pipefail

API_URL="${API_URL:-http://localhost:8000}"
API_TOKEN="${API_TOKEN:-}"
RECOVERY_TIMEOUT_SECONDS="${RECOVERY_TIMEOUT_SECONDS:-30}"

api_curl() {
  local headers=()
  if [ -n "$API_TOKEN" ]; then
    headers+=(-H "X-API-Key: $API_TOKEN")
  fi
  curl -fsS "${headers[@]}" "$@"
}

wait_openbox_ok() {
  local deadline
  deadline=$(( $(date +%s) + RECOVERY_TIMEOUT_SECONDS ))
  while [ "$(date +%s)" -lt "$deadline" ]; do
    if api_curl "${API_URL}/lifecycle/status" | python3 -c 'import sys,json; d=json.load(sys.stdin); print("1" if d.get("processes",{}).get("openbox",{}).get("ok") else "0")' | grep -q "^1$"; then
      return 0
    fi
    sleep 1
  done
  return 1
}

echo "[fault] injecting openbox termination..."
api_curl -X POST "${API_URL}/apps/run" \
  -H "Content-Type: application/json" \
  -d '{"path":"pkill","args":"-f openbox","detach":false}' >/dev/null || true

echo "[fault] requesting openbox restart..."
api_curl -X POST "${API_URL}/openbox/restart" >/dev/null

echo "[fault] verifying recovery..."
if ! wait_openbox_ok; then
  echo "[fault] FAIL: openbox did not recover within ${RECOVERY_TIMEOUT_SECONDS}s" >&2
  exit 1
fi

echo "[fault] PASS: openbox recovery validated"
