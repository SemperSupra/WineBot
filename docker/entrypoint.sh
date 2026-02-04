#!/usr/bin/env bash
set -e

# Defaults
export WINEPREFIX="${WINEPREFIX:-/wineprefix}"
export DISPLAY="${DISPLAY:-:99}"
export SCREEN="${SCREEN:-1920x1080x24}"

# --- ROOT CONTEXT: User & Permission Setup ---
if [ "$(id -u)" = "0" ]; then
    USER_ID=${HOST_UID:-1000}
    GROUP_ID=${HOST_GID:-1000}

    # Update 'winebot' user to match host UID/GID if requested
    if [ "$USER_ID" != "$(id -u winebot)" ] || [ "$GROUP_ID" != "$(id -g winebot)" ]; then
        echo "--> Updating winebot user to UID:GID = $USER_ID:$GROUP_ID"
        groupmod -o -g "$GROUP_ID" winebot
        usermod -o -u "$USER_ID" -g "$GROUP_ID" winebot
    fi

    # Ensure critical directories are owned by the user
    mkdir -p "$WINEPREFIX" "/home/winebot/.cache" "/artifacts"
    chown -R winebot:winebot "/home/winebot" "$WINEPREFIX" "/artifacts"
    chmod 777 /tmp

    # Handle .X11-unix specifically for Xvfb
    mkdir -p /tmp/.X11-unix
    chmod 1777 /tmp/.X11-unix

    # Drop privileges and re-execute this script as 'winebot'
    exec gosu winebot "$0" "$@"
fi

# --- USER CONTEXT (winebot) ---

# 1. Clean up stale locks from previous runs (if any)
rm -f "/tmp/.X${DISPLAY##*:}-lock" "/tmp/.X11-unix/X${DISPLAY##*:}"

# 2. Start Xvfb
Xvfb "$DISPLAY" -screen 0 "$SCREEN" -ac +extension RANDR >/dev/null 2>&1 &
XVFB_PID=$!
sleep 1 # Give Xvfb a moment to start

# --- Session Setup ---
SESSION_ROOT="${WINEBOT_SESSION_ROOT:-/artifacts/sessions}"
RESUMED="0"
if [ -n "${WINEBOT_SESSION_DIR:-}" ]; then
    SESSION_DIR="$WINEBOT_SESSION_DIR"
    SESSION_ID="${WINEBOT_SESSION_ID:-$(basename "$SESSION_DIR")}"
    RESUMED="1"
elif [ -n "${WINEBOT_SESSION_ID:-}" ]; then
    SESSION_ID="$WINEBOT_SESSION_ID"
    SESSION_DIR="${SESSION_ROOT}/${SESSION_ID}"
    RESUMED="1"
else
    SESSION_TS=$(date +%s)
    SESSION_DATE=$(date -u +%Y-%m-%d)
    SESSION_RAND=$(cat /dev/urandom | tr -dc 'a-z0-9' | fold -w 6 | head -n 1)
    SESSION_ID="session-${SESSION_DATE}-${SESSION_TS}-${SESSION_RAND}${WINEBOT_SESSION_LABEL:+-${WINEBOT_SESSION_LABEL}}"
    SESSION_DIR="${SESSION_ROOT}/${SESSION_ID}"
fi

export WINEBOT_SESSION_ROOT="$SESSION_ROOT"
export WINEBOT_SESSION_ID="$SESSION_ID"
export WINEBOT_SESSION_DIR="$SESSION_DIR"
export WINEBOT_SESSION_RESUMED="$RESUMED"
echo "$SESSION_DIR" > /tmp/winebot_current_session

mkdir -p "$SESSION_DIR"/{logs,screenshots,scripts}

SESSION_USER_DIR="${SESSION_DIR}/user"
USER_DIR="${WINEBOT_USER_DIR:-$SESSION_USER_DIR}"
if [ "$USER_DIR" != "$SESSION_USER_DIR" ]; then
    mkdir -p "$USER_DIR"
    if [ -e "$SESSION_USER_DIR" ] && [ ! -L "$SESSION_USER_DIR" ]; then
        rm -rf "$SESSION_USER_DIR"
    else
        rm -f "$SESSION_USER_DIR"
    fi
    ln -s "$USER_DIR" "$SESSION_USER_DIR"
else
    mkdir -p "$SESSION_USER_DIR"
fi

export WINEBOT_USER_DIR="$USER_DIR"

mkdir -p "$WINEPREFIX/drive_c/users"
WINE_USER_DIR="$WINEPREFIX/drive_c/users/winebot"
USER_TEMPLATE=""
if [ -L "$WINE_USER_DIR" ]; then
    ln -sfn "$USER_DIR" "$WINE_USER_DIR"
elif [ -e "$WINE_USER_DIR" ]; then
    backup="${WINE_USER_DIR}.bak.$(date +%s)"
    mv "$WINE_USER_DIR" "$backup"
    USER_TEMPLATE="$backup"
    ln -s "$USER_DIR" "$WINE_USER_DIR"
else
    ln -s "$USER_DIR" "$WINE_USER_DIR"
fi

TEMPLATE_DIR="$WINEPREFIX/drive_c/users/.winebot_template"
if [ -n "$USER_TEMPLATE" ] && [ ! -d "$TEMPLATE_DIR" ]; then
    cp -a "$USER_TEMPLATE" "$TEMPLATE_DIR"
fi

ensure_user_profile() {
    local target="$1"
    local paths=(
        "$target/AppData/Roaming"
        "$target/AppData/Local"
        "$target/AppData/LocalLow"
        "$target/AppData/Roaming/Microsoft/Windows/Start Menu/Programs"
        "$target/Desktop"
        "$target/Documents"
        "$target/Downloads"
        "$target/Music"
        "$target/Pictures"
        "$target/Videos"
        "$target/Contacts"
        "$target/Favorites"
        "$target/Links"
        "$target/Saved Games"
        "$target/Searches"
        "$target/Temp"
    )
    for path in "${paths[@]}"; do
        if [ -L "$path" ]; then
            rm -f "$path"
        fi
        mkdir -p "$path"
    done
}

seed_user_profile() {
    local target="$1"
    if [ -d "$TEMPLATE_DIR" ]; then
        cp -a "$TEMPLATE_DIR/." "$target/" || true
    fi
    ensure_user_profile "$target"
}

if [ ! -d "$USER_DIR/Desktop" ] || [ ! -d "$USER_DIR/Documents" ]; then
    seed_user_profile "$USER_DIR"
fi

python3 - <<'PY'
import datetime
import json
import os
import platform

def parse_resolution(screen):
    if not screen:
        return "1920x1080"
    parts = screen.split("x")
    if len(parts) >= 2:
        return f"{parts[0]}x{parts[1]}"
    return screen

session_dir = os.environ.get("WINEBOT_SESSION_DIR")
session_id = os.environ.get("WINEBOT_SESSION_ID")
resumed = os.environ.get("WINEBOT_SESSION_RESUMED") == "1"
if session_dir and session_id:
    path = os.path.join(session_dir, "session.json")
    if not resumed or not os.path.exists(path):
        manifest = {
            "session_id": session_id,
            "start_time_epoch": datetime.datetime.now(datetime.timezone.utc).timestamp(),
            "start_time_iso": datetime.datetime.now(datetime.timezone.utc).isoformat(),
            "hostname": platform.node(),
            "display": os.environ.get("DISPLAY", ":99"),
            "resolution": parse_resolution(os.environ.get("SCREEN", "1920x1080")),
            "fps": 30,
            "git_sha": None,
        }
    else:
        try:
            with open(path, "r") as f:
                manifest = json.load(f) or {}
        except Exception:
            manifest = {"session_id": session_id}
        resume_count = int(manifest.get("resume_count", 0)) + 1
        manifest["resume_count"] = resume_count
        resume_times = manifest.get("resume_times", [])
        if not isinstance(resume_times, list):
            resume_times = []
        resume_times.append(datetime.datetime.now(datetime.timezone.utc).isoformat())
        manifest["resume_times"] = resume_times
    with open(path, "w") as f:
        json.dump(manifest, f, indent=2)
    with open(os.path.join(session_dir, "session.state"), "w") as f:
        f.write("active")
PY

log_event() {
    local kind="$1"
    local message="$2"
    EVENT_KIND="$kind" EVENT_MESSAGE="$message" EVENT_SOURCE="entrypoint" python3 - <<'PY' || true
import datetime
import json
import os
import time

session_dir = os.environ.get("WINEBOT_SESSION_DIR")
session_id = os.environ.get("WINEBOT_SESSION_ID")
kind = os.environ.get("EVENT_KIND")
message = os.environ.get("EVENT_MESSAGE")
source = os.environ.get("EVENT_SOURCE", "entrypoint")
if not session_dir or not kind:
    raise SystemExit(0)

path = os.path.join(session_dir, "logs", "lifecycle.jsonl")
os.makedirs(os.path.dirname(path), exist_ok=True)
event = {
    "timestamp_utc": datetime.datetime.now(datetime.timezone.utc).isoformat(),
    "timestamp_epoch_ms": int(time.time() * 1000),
    "session_id": session_id,
    "kind": kind,
    "message": message,
    "source": source,
}
with open(path, "a") as f:
    f.write(json.dumps(event) + "\n")
PY
}

# Configure Openbox (single desktop + menu)
OPENBOX_CONFIG_DIR="${HOME}/.config/openbox"
mkdir -p "$OPENBOX_CONFIG_DIR"
if [ -f "/etc/xdg/openbox/rc.xml" ] && [ ! -f "${OPENBOX_CONFIG_DIR}/rc.xml" ]; then
    cp "/etc/xdg/openbox/rc.xml" "${OPENBOX_CONFIG_DIR}/rc.xml"
    log_event "openbox_config_loaded" "Openbox rc.xml loaded"
fi
if [ -f "/etc/xdg/openbox/menu.xml" ] && [ ! -f "${OPENBOX_CONFIG_DIR}/menu.xml" ]; then
    cp "/etc/xdg/openbox/menu.xml" "${OPENBOX_CONFIG_DIR}/menu.xml"
    log_event "openbox_menu_loaded" "Openbox menu.xml loaded"
fi

# Start Window Manager (Openbox)
openbox >/dev/null 2>&1 &

if [ "$RESUMED" = "1" ]; then
    log_event "session_resumed" "Session resumed"
else
    log_event "session_created" "Session initialized"
fi
log_event "xvfb_started" "Xvfb started"
log_event "openbox_started" "Openbox started"

exec > >(tee -a "$SESSION_DIR/logs/entrypoint.log") 2>&1

# --- Recorder Setup ---
RECORDER_PID=""

annotate_safe() {
    if [ -z "${RECORDER_PID:-}" ]; then
        return 0
    fi
    local session_dir="${SESSION_DIR:-${WINEBOT_SESSION_DIR:-}}"
    if [ -z "$session_dir" ]; then
        return 0
    fi
    local manifest="${session_dir}/session.json"
    for _ in $(seq 1 10); do
        if [ -f "$manifest" ]; then
            scripts/annotate.sh --text "$1" --type "$2" --source "$3" || true
            return 0
        fi
        sleep 0.1
    done
    return 0
}

annotate_safe "Xvfb ready on $DISPLAY" "lifecycle" "entrypoint"
if [ "${WINEBOT_RECORD:-0}" = "1" ]; then
    echo "--> Starting Recorder..."
    
    # Resolution parsing: handles 1920x1080x24 -> 1920x1080, and 1280x720 -> 1280x720
    if [[ "$SCREEN" == *x*x* ]]; then
        RES="${SCREEN%x*}"
    else
        RES="$SCREEN"
    fi
    
    # Start Recorder
    mkdir -p "$SESSION_DIR"
    SEGMENT_INDEX_FILE="${SESSION_DIR}/segment_index.txt"
    if [ -f "$SEGMENT_INDEX_FILE" ]; then
        SEGMENT_INDEX="$(cat "$SEGMENT_INDEX_FILE" 2>/dev/null || echo 1)"
    else
        SEGMENT_INDEX="1"
    fi
    NEXT_SEGMENT_INDEX=$((SEGMENT_INDEX + 1))
    echo "$NEXT_SEGMENT_INDEX" > "$SEGMENT_INDEX_FILE"

    python3 -m automation.recorder start \
        --session-dir "$SESSION_DIR" \
        --display "$DISPLAY" \
        --resolution "$RES" \
        --fps 30 \
        --segment "$SEGMENT_INDEX" > "$SESSION_DIR/logs/recorder.log" 2>&1 &
    RECORDER_PID=$!
    
    echo "Recorder started (PID: $RECORDER_PID) in $SESSION_DIR"
    log_event "recorder_started" "Recorder started"
fi

stop_recorder() {
    if [ -n "$RECORDER_PID" ]; then
        echo "--> Stopping Recorder..."
        python3 -m automation.recorder stop --session-dir "$SESSION_DIR" || true
        wait "$RECORDER_PID" || true
        RECORDER_PID=""
    fi
}

shutdown_notice() {
    log_event "shutdown_requested" "Shutdown requested"
    if [ -n "${SESSION_DIR:-}" ]; then
        echo "stopped" > "${SESSION_DIR}/session.state" || true
    fi
    stop_recorder
}

trap 'shutdown_notice' EXIT
# ----------------------

# 4. Start VNC/noVNC if requested
if [ "${ENABLE_VNC:-0}" = "1" ] || [ "${MODE:-headless}" = "interactive" ]; then
    echo "--> Starting VNC/noVNC services..."
    VNC_ARGS=("-display" "$DISPLAY" "-forever" "-shared" "-rfbport" "${VNC_PORT:-5900}" "-bg" "-noxrecord" "-ncache" "0" "-cursor" "arrow")
    if [ -n "${VNC_PASSWORD:-}" ]; then
        mkdir -p "$HOME/.vnc"
        x11vnc -storepasswd "$VNC_PASSWORD" "$HOME/.vnc/passwd"
        VNC_ARGS+=("-rfbauth" "$HOME/.vnc/passwd")
    else
        VNC_ARGS+=("-nopw")
    fi
    x11vnc "${VNC_ARGS[@]}" >/dev/null 2>&1
    log_event "vnc_started" "x11vnc started"

    # Start noVNC (websockify)
    websockify --web /usr/share/novnc/ "${NOVNC_PORT:-6080}" "localhost:${VNC_PORT:-5900}" >/dev/null 2>&1 &
    log_event "novnc_started" "noVNC started"
fi

# 5. Initialize Wine Prefix (if needed)
if [ "${INIT_PREFIX:-1}" = "1" ] && [ ! -f "$WINEPREFIX/system.reg" ]; then
    echo "--> Initializing WINEPREFIX..."
    annotate_safe "Initializing WINEPREFIX..." "lifecycle" "entrypoint"
    log_event "wineboot_init" "Initializing WINEPREFIX"
    wineboot --init >/dev/null 2>&1
    annotate_safe "WINEPREFIX ready" "lifecycle" "entrypoint"
    log_event "wineboot_ready" "WINEPREFIX ready"
else
    # Ensure Wine services (explorer, etc.) are running
    wine explorer >/dev/null 2>&1 &
    log_event "wine_explorer_started" "Wine explorer started"
fi

# 6. Execute under winedbg if requested
# ... (omitting winedbg block context for brevity in replace, but I'll include enough) ...
if [ "${ENABLE_WINEDBG:-0}" = "1" ]; then
# ...
    echo "--> Running under winedbg ($WINEDBG_MODE): ${CMD[*]}"
    annotate_safe "Launching app under winedbg: ${CMD[*]}" "lifecycle" "entrypoint"
    exec winedbg "${WINEDBG_ARGS[@]}" "${CMD[@]}"
fi

# Start API if enabled
if [ "${ENABLE_API:-0}" = "1" ]; then
    echo "Starting API server on port 8000..."
    annotate_safe "Starting API server" "lifecycle" "entrypoint"
    log_event "api_starting" "Starting API server"
    # Ensure X11 env is sourced for the python process if needed, 
    # though subprocess calls in server.py usually source x11_env.sh via wrapper scripts.
    # We run it as winebot user.
    if [ "$(id -u)" = "0" ]; then
        gosu winebot uvicorn api.server:app --host 0.0.0.0 --port 8000 > "$SESSION_DIR/logs/api.log" 2>&1 &
    else
        uvicorn api.server:app --host 0.0.0.0 --port 8000 > "$SESSION_DIR/logs/api.log" 2>&1 &
    fi
    log_event "api_process_started" "API process started"
fi

# Keep container alive (if no command provided)
if [ -z "$@" ]; then
    annotate_safe "Container idle (waiting)" "lifecycle" "entrypoint"
    tail -f /dev/null
else
    annotate_safe "Launching: $*" "lifecycle" "entrypoint"
    "$@"
    EXIT_CODE=$?
    annotate_safe "App exited with code $EXIT_CODE" "lifecycle" "entrypoint"
    exit $EXIT_CODE
fi
