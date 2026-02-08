#!/usr/bin/env bash
# 30-start-services.sh: Start API, Tracing, and Supervisor Loop

# Tracing
if [ "${WINEBOT_INPUT_TRACE_WINDOWS:-0}" = "1" ]; then
    WIN_TRACE_MS="${WINEBOT_INPUT_TRACE_WINDOWS_SAMPLE_MS:-10}"
    # Escape path for Wine (convert / to \)
    WINE_LOG_PATH="Z:${SESSION_DIR//\//\\}\\logs\\input_events_windows.jsonl"
    ahk /automation/input_trace_windows.ahk "$WINE_LOG_PATH" "$WIN_TRACE_MS" "$SESSION_ID" >/dev/null 2>&1 &
fi

if [ "${WINEBOT_INPUT_TRACE:-0}" = "1" ]; then
    python3 -m automation.input_trace start --session-dir "$SESSION_DIR" >/dev/null 2>&1 &
fi

# Recorder (if enabled)
if [ "${WINEBOT_RECORD:-0}" = "1" ]; then
    if [[ "$SCREEN" == *x*x* ]]; then RES="${SCREEN%x*}"; else RES="$SCREEN"; fi
    
    mkdir -p "$SESSION_DIR"
    SEGMENT_INDEX_FILE="${SESSION_DIR}/segment_index.txt"
    if [ -f "$SEGMENT_INDEX_FILE" ]; then
        SEGMENT_INDEX="$(cat "$SEGMENT_INDEX_FILE" 2>/dev/null || echo 1)"
    else
        SEGMENT_INDEX="1"
    fi
    echo "$((SEGMENT_INDEX + 1))" > "$SEGMENT_INDEX_FILE"

    python3 -m automation.recorder start \
        --session-dir "$SESSION_DIR" \
        --display "$DISPLAY" \
        --resolution "$RES" \
        --fps 30 \
        --segment "$SEGMENT_INDEX" > "$SESSION_DIR/logs/recorder.log" 2>&1 &
fi

# API
if [ "${ENABLE_API:-0}" = "1" ]; then
    export DISPLAY="${DISPLAY}"
    export XAUTHORITY="${XAUTHORITY:-$HOME/.Xauthority}"
    uvicorn api.server:app --host 0.0.0.0 --port 8000 > "$SESSION_DIR/logs/api.log" 2>&1 &
fi

# Supervisor
echo "--> Starting Desktop Supervisor..."
(
  while true; do
    if ! pgrep -f "explorer.exe" > /dev/null; then
        sleep 1
        if ! pgrep -f "explorer.exe" > /dev/null; then
            if command -v setsid >/dev/null 2>&1; then
                setsid wine explorer.exe >"$SESSION_DIR/logs/explorer.log" 2>&1 &
            else
                nohup wine explorer.exe >"$SESSION_DIR/logs/explorer.log" 2>&1 &
            fi
            sleep 5
        fi
    fi
    
    # Check for wineserver crash
    if ! pgrep -n "wineserver" > /dev/null; then
         rm -f /tmp/wineserver_missing_logged
    fi

    # Ensure windows are managed
    for title in "Desktop" "Wine Desktop"; do
      if xdotool search --name "$title" >/dev/null 2>&1; then
        wmctrl -r "$title" -b remove,undecorated >/dev/null 2>&1 || true
      fi
    done
    sleep 5
  done
) &