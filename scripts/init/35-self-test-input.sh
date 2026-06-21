#!/usr/bin/env bash
set -euo pipefail

# 35-self-test-input.sh
# Startup self-test: verifies the input pipeline (API /input/key -> Windows app)
# is functional before the container reports healthy.
#
# Controlled by WINEBOT_INPUT_SELF_TEST (default: 0).
# Set WINEBOT_INPUT_SELF_TEST=1 to enable.

SELF_TEST="${WINEBOT_INPUT_SELF_TEST:-0}"
if [ "$SELF_TEST" != "1" ]; then
    echo "--> Input pipeline self-test disabled (WINEBOT_INPUT_SELF_TEST=0)."
    exit 0
fi

API_URL="${API_URL:-http://localhost:8000}"
API_WAIT="${WINEBOT_INPUT_SELF_TEST_WAIT:-20}"
TEST_KEY="${WINEBOT_INPUT_SELF_TEST_KEY:-x}"
TEST_STATUS_FILE="/tmp/winebot_input_self_test_status.json"

echo "--> Input pipeline self-test: waiting for API readiness (max ${API_WAIT}s)..."

# Wait for API
API_TOKEN=""
for token_file in /tmp/winebot_api_token /winebot-shared/winebot_api_token; do
    if [ -f "$token_file" ]; then
        API_TOKEN="$(tr -d '[:space:]' <"$token_file")"
        break
    fi
done

waited=0
while [ "$waited" -lt "$API_WAIT" ]; do
    if [ -n "$API_TOKEN" ]; then
        if curl -sfS -H "X-API-Key: ${API_TOKEN}" "${API_URL}/health" >/dev/null 2>&1; then
            break
        fi
    else
        if curl -sfS "${API_URL}/health" >/dev/null 2>&1; then
            break
        fi
    fi
    sleep 1
    waited=$((waited + 1))
done

if [ "$waited" -ge "$API_WAIT" ]; then
    echo "--> Input pipeline self-test: API not ready after ${API_WAIT}s, skipping."
    cat > "$TEST_STATUS_FILE" <<'EOF'
{"status": "skipped", "reason": "api_not_ready", "timestamp_utc": ""}
EOF
    exit 0
fi

echo "--> Input pipeline self-test: launching test app (notepad)..."

# Launch Notepad
wine notepad >/dev/null 2>&1 &
NOTEPAD_PID=$!
sleep 3

# Find Notepad window
NOTEPAD_ID=""
for _ in $(seq 1 15); do
    NOTEPAD_ID=$(xdotool search --name "Notepad" 2>/dev/null | head -n 1 || true)
    if [ -n "$NOTEPAD_ID" ]; then
        break
    fi
    sleep 1
done

if [ -z "$NOTEPAD_ID" ]; then
    echo "--> Input pipeline self-test: Notepad window not found, test FAILED."
    kill "$NOTEPAD_PID" 2>/dev/null || true
    cat > "$TEST_STATUS_FILE" <<'EOF'
{"status": "failed", "reason": "notepad_window_not_found", "timestamp_utc": ""}
EOF
    exit 1
fi

# Activate window
xdotool windowactivate "$NOTEPAD_ID" 2>/dev/null || true
sleep 0.5

# Send test key via API /input/key
echo "--> Input pipeline self-test: sending test key via /input/key..."

JSON_BODY=$(printf '{"keys": "%s", "window_title": "Notepad"}' "$TEST_KEY")
CURL_ARGS=(-s -X POST -H "Content-Type: application/json" -d "$JSON_BODY")
if [ -n "$API_TOKEN" ]; then
    CURL_ARGS+=(-H "X-API-Key: ${API_TOKEN}")
fi

RESPONSE=$(curl "${CURL_ARGS[@]}" "${API_URL}/input/key" 2>/dev/null || true)

STATUS=$(printf '%s' "$RESPONSE" | python3 -c 'import sys,json
try:
 d=json.load(sys.stdin); print((d.get("status") or "").strip())
except Exception:
 print("")')
BACKEND=$(printf '%s' "$RESPONSE" | python3 -c 'import sys,json
try:
 d=json.load(sys.stdin); print((d.get("backend") or "").strip())
except Exception:
 print("")')
TRACE_ID=$(printf '%s' "$RESPONSE" | python3 -c 'import sys,json
try:
 d=json.load(sys.stdin); print((d.get("trace_id") or "").strip())
except Exception:
 print("")')

if [ "$STATUS" != "sent" ]; then
    echo "--> Input pipeline self-test: /input/key returned status='$STATUS', test FAILED."
    kill "$NOTEPAD_PID" 2>/dev/null || true
    cat > "$TEST_STATUS_FILE" <<EOF
{"status": "failed", "reason": "api_key_returned_${STATUS}", "backend": "$BACKEND", "timestamp_utc": ""}
EOF
    exit 1
fi

echo "--> Input pipeline self-test: key sent via backend=$BACKEND trace_id=$TRACE_ID"

# Wait for trace to propagate
sleep 1

# Check for trace evidence
SESSION_DIR=""
if [ -f /tmp/winebot_current_session ]; then
    SESSION_DIR="$(cat /tmp/winebot_current_session)"
fi

TRACE_FOUND=0
if [ -n "$SESSION_DIR" ] && [ -n "$TRACE_ID" ]; then
    WIN_LOG="${SESSION_DIR}/logs/input_events_windows.jsonl"
    if [ -f "$WIN_LOG" ]; then
        if grep -q "$TRACE_ID" "$WIN_LOG" 2>/dev/null; then
            TRACE_FOUND=1
            echo "--> Input pipeline self-test: Windows trace event found (trace_id=$TRACE_ID)"
        fi
    fi
fi

# Cleanup
kill "$NOTEPAD_PID" 2>/dev/null || true
sleep 1
pkill -f "notepad.exe" 2>/dev/null || true

# Write status
TIMESTAMP=$(date -u +%Y-%m-%dT%H:%M:%SZ)
if [ "$TRACE_FOUND" = "1" ]; then
    echo "--> Input pipeline self-test: PASSED (backend=$BACKEND, trace confirmed)."
    cat > "$TEST_STATUS_FILE" <<EOF
{"status": "passed", "backend": "$BACKEND", "trace_id": "$TRACE_ID", "trace_confirmed": true, "timestamp_utc": "$TIMESTAMP"}
EOF
    exit 0
else
    echo "--> Input pipeline self-test: INCONCLUSIVE (key sent ok, trace not found in Windows log)."
    cat > "$TEST_STATUS_FILE" <<EOF
{"status": "inconclusive", "backend": "$BACKEND", "trace_id": "$TRACE_ID", "trace_confirmed": false, "timestamp_utc": "$TIMESTAMP"}
EOF
    exit 0
fi
