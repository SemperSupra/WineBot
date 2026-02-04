#!/usr/bin/env bash
set -euo pipefail

# run-diagnostics-with-recording.sh
# Records a video of the diagnostic suite and validates artifacts.
# Assumes running inside the container (or has access to API).

API_URL="http://localhost:8000"
SESSION_DIR=""
if [ -f /tmp/winebot_current_session ]; then
    SESSION_DIR=$(cat /tmp/winebot_current_session)
fi

log() {
    echo "[$(date +'%H:%M:%S')] $*"
}

annotate() {
    local msg="$1"
    if [ -x "/scripts/annotate.sh" ]; then
        /scripts/annotate.sh --text "$msg" --type "subtitle" || true
    fi
}

log "Starting Recording..."
curl -s -X POST "$API_URL/recording/start" -H "Content-Type: application/json" -d '{"new_session": false}' >/dev/null

sleep 2

# 1. Bash Suite
log "Running Bash Diagnostic Suite..."
annotate "Running Bash Suite"
/scripts/diagnose-input-suite.sh || log "Bash Suite Failed"

# Cleanup
pkill -f "notepad.exe" || true
rm -f "/wineprefix/drive_c/ahk_test.txt" "/wineprefix/drive_c/autoit_test.txt"

# 2. AutoHotkey
log "Running AutoHotkey Diagnostics..."
annotate "Running AutoHotkey Suite"
if [ -x "/scripts/run-ahk.sh" ]; then
    /scripts/run-ahk.sh /scripts/diagnose-ahk.ahk || log "AHK Script Failed"
else
    log "run-ahk.sh not found"
fi

# Cleanup
pkill -f "notepad.exe" || true

# 3. AutoIt
log "Running AutoIt Diagnostics..."
annotate "Running AutoIt Suite"
if [ -x "/scripts/run-autoit.sh" ]; then
    /scripts/run-autoit.sh /scripts/diagnose-autoit.au3 || log "AutoIt Script Failed"
else
    log "run-autoit.sh not found"
fi

log "Stopping Recording..."
curl -s -X POST "$API_URL/recording/stop" >/dev/null

sleep 3

log "Validating Artifacts..."

# Video
VIDEO_FILES=$(find "$SESSION_DIR" -name "video_*.mkv")
if [ -n "$VIDEO_FILES" ]; then
    log "SUCCESS: Video file(s) found."
else
    log "FAILURE: No video file found."
    exit 1
fi

# Events
EVENTS_FILE=$(find "$SESSION_DIR" -name "events_*.jsonl" | sort | tail -n 1)
if [ -n "$EVENTS_FILE" ]; then
    if grep -q "Notepad: Create Script" "$EVENTS_FILE"; then
        log "SUCCESS: found 'Notepad: Create Script' (Bash)"
    else
        log "FAILURE: Missing annotation 'Notepad: Create Script'"
    fi
else
    log "FAILURE: No events file found."
fi

# File Validation
if [ -f "/wineprefix/drive_c/ahk_test.txt" ]; then
    log "SUCCESS: AHK created file."
else
    log "FAILURE: AHK failed to create file."
fi

if [ -f "/wineprefix/drive_c/autoit_test.txt" ]; then
    log "SUCCESS: AutoIt created file."
else
    log "FAILURE: AutoIt failed to create file."
fi

log "Validation Complete."