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
    mkdir -p "$WINEPREFIX" "/home/winebot/.cache"
    chown -R winebot:winebot "/home/winebot" "$WINEPREFIX"
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

# 3. Start Window Manager (Openbox)
openbox >/dev/null 2>&1 &

# 4. Start VNC/noVNC if requested
if [ "${ENABLE_VNC:-0}" = "1" ] || [ "${MODE:-headless}" = "interactive" ]; then
    echo "--> Starting VNC/noVNC services..."
    VNC_ARGS=("-display" "$DISPLAY" "-forever" "-shared" "-rfbport" "${VNC_PORT:-5900}" "-bg")
    if [ -n "${VNC_PASSWORD:-}" ]; then
        mkdir -p "$HOME/.vnc"
        x11vnc -storepasswd "$VNC_PASSWORD" "$HOME/.vnc/passwd"
        VNC_ARGS+=("-rfbauth" "$HOME/.vnc/passwd")
    else
        VNC_ARGS+=("-nopw")
    fi
    x11vnc "${VNC_ARGS[@]}" >/dev/null 2>&1

    # Start noVNC (websockify)
    websockify --web /usr/share/novnc/ "${NOVNC_PORT:-6080}" "localhost:${VNC_PORT:-5900}" >/dev/null 2>&1 &
fi

# 5. Initialize Wine Prefix (if needed)
if [ "${INIT_PREFIX:-1}" = "1" ] && [ ! -f "$WINEPREFIX/system.reg" ]; then
    echo "--> Initializing WINEPREFIX..."
    wineboot --init >/dev/null 2>&1
else
    # Ensure Wine services (explorer, etc.) are running
    wine explorer >/dev/null 2>&1 &
fi

# 6. Execute under winedbg if requested
if [ "${ENABLE_WINEDBG:-0}" = "1" ]; then
    WINEDBG_MODE="${WINEDBG_MODE:-gdb}"
    WINEDBG_ARGS=()
    
    if [ "$WINEDBG_MODE" = "gdb" ]; then
        WINEDBG_ARGS+=("--gdb")
        if [ -n "${WINEDBG_PORT:-}" ] && [ "${WINEDBG_PORT}" != "0" ]; then
            WINEDBG_ARGS+=("--port" "$WINEDBG_PORT")
        fi
        if [ "${WINEDBG_NO_START:-0}" = "1" ]; then
            WINEDBG_ARGS+=("--no-start")
        fi
    else
        # default mode
        if [ -n "${WINEDBG_COMMAND:-}" ]; then
            WINEDBG_ARGS+=("--command" "$WINEDBG_COMMAND")
        fi
        if [ -n "${WINEDBG_SCRIPT:-}" ]; then
            WINEDBG_ARGS+=("--file" "$WINEDBG_SCRIPT")
        fi
    fi

    # Determine command to run
    if [ $# -gt 0 ]; then
        CMD=("$@")
    else
        CMD=("${APP_EXE:-cmd.exe}" $APP_ARGS)
    fi

    echo "--> Running under winedbg ($WINEDBG_MODE): ${CMD[*]}"
    exec winedbg "${WINEDBG_ARGS[@]}" "${CMD[@]}"
fi

# Start API if enabled
if [ "${ENABLE_API:-0}" = "1" ]; then
    echo "Starting API server on port 8000..."
    # Ensure X11 env is sourced for the python process if needed, 
    # though subprocess calls in server.py usually source x11_env.sh via wrapper scripts.
    # We run it as winebot user.
    if [ "$(id -u)" = "0" ]; then
        gosu winebot uvicorn api.server:app --host 0.0.0.0 --port 8000 &
    else
        uvicorn api.server:app --host 0.0.0.0 --port 8000 &
    fi
fi

# Keep container alive (if no command provided)
if [ -z "$@" ]; then
    tail -f /dev/null
else
    exec "$@"
fi