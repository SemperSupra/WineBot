#!/usr/bin/env bash
# 30-start-services.sh: Start API, Tracing, and Supervisor Loop

echo "--> Pass 4: Service Startup (WINEBOT_INPUT_TRACE_WINDOWS=${WINEBOT_INPUT_TRACE_WINDOWS:-unset})"

# Post-Init Tracing (Ensures wineserver is stable)
if [ "${WINEBOT_INPUT_TRACE_WINDOWS:-0}" = "1" ]; then
    echo "--> Post-Init Tracing: AHK hook enabled."
    sleep 2
    WIN_TRACE_MS="${WINEBOT_INPUT_TRACE_WINDOWS_SAMPLE_MS:-5}"
    mkdir -p "$SESSION_DIR/logs"
    WINE_LOG_PATH=$(winepath -w "$SESSION_DIR/logs/input_events_windows.jsonl")
    WINE_SCRIPT_PATH=$(winepath -w /automation/core/input_trace_windows.ahk)
    echo "--> Starting Windows Input Trace..."
    (
      while true; do
        wine "/opt/winebot/windows-tools/AutoHotkey/AutoHotkeyU64.exe" "$WINE_SCRIPT_PATH" "$WINE_LOG_PATH" "$WIN_TRACE_MS" "$SESSION_ID" >> "$SESSION_DIR/logs/ahk_trace.log" 2>&1
        echo "--> AHK trace exited (RC: $?), restarting in 5s..." >> "$SESSION_DIR/logs/ahk_trace.log"
        sleep 5
      done
    ) &
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
    if [ -z "${API_TOKEN:-}" ]; then
        # Generate a random 16-char token for secure-by-default operation
        export API_TOKEN=$(cat /dev/urandom | tr -dc 'a-zA-Z0-9' | fold -w 16 | head -n 1)
        echo "--> [SECURITY] No API_TOKEN provided. Generated random token: ${API_TOKEN}"
        echo "--> [SECURITY] Use this token in 'X-API-Key' header for all requests."
        
    fi
    # Persist for internal tool discovery (use /tmp as /run is root-only)
    if [ -n "${API_TOKEN:-}" ]; then
        echo -n "$API_TOKEN" > /tmp/winebot_api_token
        chmod 600 /tmp/winebot_api_token
        if [ -d /winebot-shared ]; then
            if echo -n "$API_TOKEN" > /winebot-shared/winebot_api_token; then
                chmod 600 /winebot-shared/winebot_api_token || true
            else
                echo "--> [WARN] Could not write /winebot-shared/winebot_api_token; continuing with /tmp token only." >&2
            fi
        fi
    fi
    export DISPLAY="${DISPLAY}"
    export XAUTHORITY="${XAUTHORITY:-$HOME/.Xauthority}"
    export PYTHONPATH="${PYTHONPATH:-}:/"
    API_PORT="${API_PORT:-8000}"
    uvicorn api.server:app --host 0.0.0.0 --port "$API_PORT" > "$SESSION_DIR/logs/api.log" 2>&1 &
fi

# Supervisor
if [ "${WINEBOT_SUPERVISE_EXPLORER:-1}" = "1" ]; then
    echo "--> Starting Desktop Supervisor..."
    # Settle time
    sleep 2
    (
      # Reduce noise for the supervisor's wine calls
      export WINEDEBUG="-all"
      while true; do
        if ! pgrep -f "explorer.exe" > /dev/null; then
            # Small delay before restart to avoid tight crash loops
            sleep 2
            if ! pgrep -f "explorer.exe" > /dev/null; then
                if [ "${WINEBOT_LOG_LEVEL:-}" = "DEBUG" ]; then
                    echo "--> Supervisor: Restarting explorer.exe"
                fi
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

        # Ensure windows are managed (silent)
        for title in "Desktop" "Wine Desktop"; do
          wid=$(xdotool search --name "$title" 2>/dev/null | tail -n 1 || true)
          if [ -n "$wid" ]; then
            # Undecorate via Motif hints if needed (equivalent to wmctrl -b remove,undecorated)
            xprop -id "$wid" -f _MOTIF_WM_HINTS 32c -set _MOTIF_WM_HINTS "0x2, 0x0, 0x0, 0x0, 0x0" >/dev/null 2>&1 || true
          fi
        done
        sleep 5
      done
    ) &
else
    echo "--> Desktop Supervisor disabled (WINEBOT_SUPERVISE_EXPLORER=0)."
fi
