#!/usr/bin/env bash
set -euo pipefail

# Source the X11 helper
if [ -f "/scripts/lib/x11_env.sh" ]; then
    source "/scripts/lib/x11_env.sh"
elif [ -f "$(dirname "$0")/lib/x11_env.sh" ]; then
    source "$(dirname "$0")/lib/x11_env.sh"
fi

if type winebot_ensure_x11_env >/dev/null 2>&1; then
    winebot_ensure_x11_env
fi

# Defaults
FOCUS_TITLE=""
FOCUS_ID=""
LOG_FILE="/tmp/winebot_autoit_$(date +%Y-%m-%d_%H-%M-%S).log"
SCRIPT=""
SCRIPT_ARGS=()

# Parse args
while [[ $# -gt 0 ]]; do
    case "$1" in
        --focus-title)
            FOCUS_TITLE="$2"
            shift 2
            ;;
        --focus-id)
            FOCUS_ID="$2"
            shift 2
            ;;
        --log)
            LOG_FILE="$2"
            shift 2
            ;;
        *)
            if [ -z "$SCRIPT" ]; then
                SCRIPT="$1"
            else
                SCRIPT_ARGS+=("$1")
            fi
            shift
            ;;
    esac
done

if [ -z "$SCRIPT" ]; then
    echo "Usage: $0 [options] <script.au3> [args]"
    echo "Options:"
    echo "  --focus-title <pattern>   Focus window matching title pattern before run"
    echo "  --focus-id <id>           Focus window by ID before run"
    echo "  --log <path>              Path to log file (default: /tmp/winebot_autoit_*.log)"
    exit 1
fi

# Ensure Wine is ready
if [ "${WINEBOT_DEBUG_X11:-0}" -eq 1 ]; then echo "[DEBUG] Initializing wineboot..."; fi
wineboot -u

# Focus window if requested
if [ -n "$FOCUS_ID" ]; then
    if [ "${WINEBOT_DEBUG_X11:-0}" -eq 1 ]; then echo "[DEBUG] Focusing window ID $FOCUS_ID"; fi
    xdotool windowactivate "$FOCUS_ID" || echo "Warning: Failed to focus window ID $FOCUS_ID"
elif [ -n "$FOCUS_TITLE" ]; then
    if [ "${WINEBOT_DEBUG_X11:-0}" -eq 1 ]; then echo "[DEBUG] Searching and focusing window '$FOCUS_TITLE'"; fi
    wid=$(xdotool search --name "$FOCUS_TITLE" | tail -1 || true)
    if [ -n "$wid" ]; then
         xdotool windowactivate "$wid" || echo "Warning: Failed to focus window ID $wid"
    else
         echo "Warning: No window found matching '$FOCUS_TITLE'"
    fi
fi

# Run AutoIt
echo "Running AutoIt script: $SCRIPT"
echo "Logging to: $LOG_FILE"

mkdir -p "$(dirname "$LOG_FILE")"

set +e
# Run using existing 'autoit' wrapper
autoit "$SCRIPT" "${SCRIPT_ARGS[@]}" > "$LOG_FILE" 2>&1
EXIT_CODE=$?
set -e

if [ $EXIT_CODE -ne 0 ]; then
    echo "AutoIt script failed with exit code $EXIT_CODE"
    echo "Last 10 lines of log:"
    tail -10 "$LOG_FILE"
else
    echo "AutoIt script completed successfully."
fi

exit $EXIT_CODE
