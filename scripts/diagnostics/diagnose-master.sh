#!/usr/bin/env bash
set -euo pipefail

# diagnose-master.sh
# Unified Master Diagnostic & Test Suite for WineBot.
# Supports granular phase selection for CI visibility.

LOG_DIR="/artifacts/diagnostics_master"
mkdir -p "$LOG_DIR"
exec > >(tee -a "$LOG_DIR/master.log") 2>&1

log() {
  echo "[$(date -u +'%Y-%m-%dT%H:%M:%SZ')] $*"
}

PHASE="${1:-all}"

wait_for_api_ready() {
    local timeout="${1:-120}"
    log "Waiting for API to be ready (up to ${timeout}s)..."
    for i in $(seq 1 "$timeout"); do
        if curl -s http://localhost:8000/health > /dev/null; then
            log "API is ready."
            return 0
        fi
        if [ "$i" -eq "$timeout" ]; then
            log "ERROR: API failed to start within ${timeout} seconds."
            SESSION_DIR=$(cat /tmp/winebot_current_session 2>/dev/null || echo "")
            if [ -n "$SESSION_DIR" ]; then
                log "Looking for logs in $SESSION_DIR/logs"
                ls -R "$SESSION_DIR/logs" || true
                if [ -f "$SESSION_DIR/logs/api.log" ]; then
                    log "--- API LOG TAIL ---"
                    tail -n 100 "$SESSION_DIR/logs/api.log"
                fi
                if [ -f "$SESSION_DIR/logs/entrypoint.log" ]; then
                    log "--- ENTRYPOINT LOG TAIL ---"
                    tail -n 100 "$SESSION_DIR/logs/entrypoint.log"
                fi
            fi
            return 1
        fi
        sleep 1
    done
}

# 1. Environment & API Health
if [[ "$PHASE" == "all" || "$PHASE" == "health" ]]; then
    log "=== PHASE 1: Environment & API Health ==="
    wait_for_api_ready 120 || exit 1

    if ! curl -s --fail http://localhost:8000/health/environment | python3 -m json.tool > "$LOG_DIR/env_health.json"; then
        log "ERROR: Health check failed. API might be down or environment broken."
        exit 1
    fi
    log "Health check saved to $LOG_DIR/env_health.json"

    # 1.1 Wine Registry Integrity
    log "--- Auditing Wine Registry ---"
    if /scripts/diagnostics/diagnose-wine-registry.sh "$LOG_DIR"; then
        log "Registry Audit: PASSED"
    else
        log "Registry Audit: FAILED"
        exit 1
    fi
fi

# 2. Start Full Tracing & Recording (Setup for following tests)
if [[ "$PHASE" != "health" ]]; then
    wait_for_api_ready 120 || exit 1
    log "=== SETUP: Initializing Tracing & Recording ==="
    # Grant control to agent for the duration of diagnostics
    curl -s -X POST http://localhost:8000/sessions/unknown/control/grant -H "Content-Type: application/json" -d '{"lease_seconds": 3600}' > /dev/null
    
    curl -s -X POST http://localhost:8000/input/trace/start > /dev/null
    curl -s -X POST http://localhost:8000/input/trace/windows/start > /dev/null
    if [ "${WINEBOT_RECORD:-0}" = "1" ]; then
        curl -s -X POST http://localhost:8000/recording/start > /dev/null
        log "Recording active."
    fi
    log "Waiting for tracers to initialize..."
    sleep 5
fi

# 3. Integrated Smoke Tests
if [[ "$PHASE" == "all" || "$PHASE" == "smoke" ]]; then
    log "=== PHASE 3: Integrated Smoke Tests ==="
    log "Waiting for Wine to be ready..."
    for i in $(seq 1 120); do
        if wine cmd /c "echo ready" >/dev/null 2>&1; then
            log "Wine is ready."
            break
        fi
        if [ "$i" -eq 120 ]; then
            log "ERROR: Wine failed to initialize within 120 seconds."
            exit 1
        fi
        sleep 1
    done
    # Run the existing smoke tests which cover AHK, AutoIt, winpy, etc.
    log "Checking for smoke test script at /tests/run_smoke_tests.sh..."
    ls -la / > /tmp/root_ls.log 2>&1 || true
    cat /tmp/root_ls.log | while read -r line; do log "LS_ROOT: $line"; done
    mount > /tmp/mount.log 2>&1 || true
    cat /tmp/mount.log | while read -r line; do log "MOUNT: $line"; done
    
    ls -l /tests/run_smoke_tests.sh || log "ERROR: Script NOT found via ls"
    if [ -x "/tests/run_smoke_tests.sh" ]; then
        if /tests/run_smoke_tests.sh; then
            log "Smoke tests: PASSED"
        else
            log "Smoke tests: FAILED"
            exit 1
        fi
    else
        log "ERROR: /tests/run_smoke_tests.sh not found or not executable"
        exit 1
    fi
fi

# 4. Input & CV Validation
if [[ "$PHASE" == "all" || "$PHASE" == "cv" ]]; then
    log "=== PHASE 4: Input & CV Validation ==="
    if /scripts/diagnostics/diagnose-input-suite.sh --no-x11-core; then
        log "Input/CV tests: PASSED"
    else
        log "Input/CV tests: FAILED"
        exit 1
    fi
fi

# 5. Trace Verification
if [[ "$PHASE" == "all" || "$PHASE" == "trace" ]]; then
    log "=== PHASE 5: Trace Verification ==="
    log "Running Coordinate Alignment Check..."
    log "Trace Status:"
    curl -s http://localhost:8000/input/trace/status | python3 -m json.tool || true
    curl -s http://localhost:8000/input/trace/windows/status | python3 -m json.tool || true
    
    # Click 4 corners + center
    TEST_POINTS=("100,100" "1180,100" "100,620" "1180,620" "640,360")
    for pt in "${TEST_POINTS[@]}"; do
        X=${pt%,*}
        Y=${pt#*,}
        log "Testing click at $X,$Y..."
        curl -s -X POST http://localhost:8000/input/mouse/click -H "Content-Type: application/json" -d "{\"x\": $X, \"y\": $Y}" > /dev/null
        sleep 1
    done

    # Check if events were recorded in the last 120 seconds
    T0=$(python3 -c "import time; print(int((time.time() - 120) * 1000))")
    
    check_trace() {
        local layer="$1"
        local count
        count="$(curl -s "http://localhost:8000/input/events?source=${layer}&since_epoch_ms=${T0}&limit=50" | python3 -c "import sys, json; print(len(json.load(sys.stdin).get('events', [])))" 2>/dev/null || echo 0)"
            if [ "$count" -gt 0 ]; then
                log "Trace layer '$layer': OK ($count events)"
            else
                log "Trace layer '$layer': NO EVENTS FOUND (last 120s)"
                return 1
            fi    }

    ERR=0
    check_trace "x11" || ERR=1
    check_trace "windows" || ERR=1
    if [ "${WINEBOT_INPUT_TRACE_NETWORK:-0}" = "1" ]; then
        check_trace "network" || ERR=1
    fi
    
    if [ $ERR -ne 0 ]; then
        log "Trace verification failed. Printing debug info:"
        SESSION_DIR=$(cat /tmp/winebot_current_session 2>/dev/null || echo "")
        if [ -n "$SESSION_DIR" ]; then
            for f in api.log input_trace.log input_trace_x11_core.stderr input_events.jsonl; do
                if [ -f "$SESSION_DIR/logs/$f" ]; then
                    log "--- $f TAIL ---"
                    tail -n 100 "$SESSION_DIR/logs/$f"
                fi
            done
        fi
        exit 1
    fi
fi

# 6. Recording Artifact Verification
if [[ "$PHASE" == "all" || "$PHASE" == "recording" ]]; then
    if [ "${WINEBOT_RECORD:-0}" = "1" ]; then
        log "=== PHASE 6: Recording Artifact Verification ==="
        if /scripts/internal/recording-smoke-test.sh http://localhost:8000; then
            log "Recording lifecycle + artifact checks: PASSED"
        else
            log "Recording lifecycle + artifact checks: FAILED"
            exit 1
        fi
    fi
fi

log "=== DIAGNOSTICS COMPLETE (Phase: $PHASE) ==="
log "Full log available at: $LOG_DIR/master.log"
