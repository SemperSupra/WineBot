#!/usr/bin/env bash
set -euo pipefail

# diagnose-master.sh
# Unified Master Diagnostic & Test Suite for WineBot.
# Covers Environment, API, Input (CV), Tracing, and Recording.

LOG_DIR="/artifacts/diagnostics_master"
mkdir -p "$LOG_DIR"
exec > >(tee -a "$LOG_DIR/master.log") 2>&1

log() {
  echo "[$(date -u +'%Y-%m-%dT%H:%M:%SZ')] $*"
}

# 1. Environment & API Health
log "=== PHASE 1: Environment & API Health ==="
log "Waiting for API to be ready..."
for i in $(seq 1 30); do
    if curl -s http://localhost:8000/health > /dev/null; then
        log "API is ready."
        break
    fi
    if [ $i -eq 30 ]; then
        log "ERROR: API failed to start within 30 seconds."
        exit 1
    fi
    sleep 1
done

if ! curl -s --fail http://localhost:8000/health/environment | python3 -m json.tool > "$LOG_DIR/env_health.json"; then
    log "ERROR: Health check failed. API might be down or environment broken."
    exit 1
fi
log "Health check saved to $LOG_DIR/env_health.json"

# 2. Start Full Tracing & Recording
log "=== PHASE 2: Initializing Tracing & Recording ==="
curl -s -X POST http://localhost:8000/input/trace/start > /dev/null
curl -s -X POST http://localhost:8000/input/trace/windows/start > /dev/null
if [ "${WINEBOT_RECORD:-0}" = "1" ]; then
    curl -s -X POST http://localhost:8000/recording/start > /dev/null
    log "Recording active."
fi

# 3. Integrated Smoke Tests
log "=== PHASE 3: Integrated Smoke Tests ==="
# Run the existing smoke tests which cover AHK, AutoIt, winpy, etc.
if /tests/run_smoke_tests.sh; then
    log "Smoke tests: PASSED"
else
    log "Smoke tests: FAILED"
fi

# 4. Input & CV Validation
log "=== PHASE 4: Input & CV Validation ==="
if /scripts/diagnose-input-suite.sh --no-x11-core; then
    log "Input/CV tests: PASSED"
else
    log "Input/CV tests: FAILED"
fi

# 5. Trace Verification
log "=== PHASE 5: Trace Verification ==="

# 5.1 Coordinate Alignment Check
log "Running Coordinate Alignment Check..."
# Click 4 corners + center
TEST_POINTS=("100,100" "1180,100" "100,620" "1180,620" "640,360")
SESSION_ID=$(curl -s http://localhost:8000/lifecycle/status | python3 -c "import sys, json; print(json.load(sys.stdin).get('session_id'))")

for pt in "${TEST_POINTS[@]}"; do
    X=${pt%,*}
    Y=${pt#*,}
    log "Testing click at $X,$Y..."
    curl -s -X POST http://localhost:8000/input/mouse/click -H "Content-Type: application/json" -d "{\"x\": $X, \"y\": $Y}" > /dev/null
    sleep 1
done

# We check if events were recorded in the last 60 seconds
T0=$(python3 -c "import time; print(int((time.time() - 60) * 1000))")

check_trace() {
    local layer="$1"
    local count=$(curl -s "http://localhost:8000/input/events?source=${layer}&since_epoch_ms=${T0}&limit=50" | python3 -c "import sys, json; print(len(json.load(sys.stdin).get('events', [])))")
    if [ "$count" -gt 0 ]; then
        log "Trace layer '$layer': OK ($count events)"
    else
        log "Trace layer '$layer': NO EVENTS FOUND (last 60s)"
    fi
}

check_trace "x11"
check_trace "windows"
if [ "${WINEBOT_INPUT_TRACE_NETWORK:-0}" = "1" ]; then
    check_trace "network"
fi

# 6. Recording Artifact Verification
if [ "${WINEBOT_RECORD:-0}" = "1" ]; then
    log "=== PHASE 6: Recording Artifacts ==="
    # Briefly stop recording to finalize file
    curl -s -X POST http://localhost:8000/recording/stop > /dev/null
    sleep 2
    # Find most recent session
    SESSION_DIR=$(ls -td /artifacts/sessions/* 2>/dev/null | head -1 || true)
    if [ -n "$SESSION_DIR" ] && [ -f "$SESSION_DIR/video_001.mkv" ]; then
        log "Recording OK: $SESSION_DIR/video_001.mkv"
    else
        log "Recording FAIL: Artifacts missing or incomplete in $SESSION_DIR"
    fi
fi

log "=== DIAGNOSTICS COMPLETE ==="
log "Full log available at: $LOG_DIR/master.log"
