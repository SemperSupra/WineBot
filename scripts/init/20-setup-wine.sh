#!/usr/bin/env bash
set +e
# 20-setup-wine.sh: Wine Prefix, Theme, and VNC services

# VNC/noVNC
if [ "${ENABLE_VNC:-0}" = "1" ] || [ "${MODE:-headless}" = "interactive" ]; then
    if [ "${BUILD_INTENT:-rel}" = "rel-runner" ]; then
        echo "ERROR: BUILD_INTENT=rel-runner does not support interactive VNC/noVNC services." >&2
        echo "Use MODE=headless and ENABLE_VNC=0 for automation-only runner deployments." >&2
        exit 1
    fi
    if ! command -v x11vnc >/dev/null 2>&1 || ! command -v websockify >/dev/null 2>&1; then
        echo "ERROR: interactive VNC/noVNC dependencies are missing from this image." >&2
        exit 1
    fi
    echo "--> Starting VNC/noVNC services..."
    VNC_PORT="${VNC_PORT:-5900}"
    X11VNC_PORT="$VNC_PORT"
    
    # Input Proxy logic would go here, simplified for modularity
    if [ "${WINEBOT_INPUT_TRACE_NETWORK:-0}" = "1" ]; then
        X11VNC_PORT=$((VNC_PORT + 1))
        # Proxy start logic...
        NET_SAMPLE_MS="${WINEBOT_INPUT_TRACE_NETWORK_SAMPLE_MS:-10}"
        python3 -m automation.vnc_input_proxy \
            --listen-port "$VNC_PORT" \
            --target-port "$X11VNC_PORT" \
            --session-dir "$SESSION_DIR" \
            --sample-motion-ms "$NET_SAMPLE_MS" >/dev/null 2>&1 &
        echo "$!" > "${SESSION_DIR}/input_trace_network.pid"
    fi

    VNC_ARGS=("-display" "$DISPLAY" "-forever" "-shared" "-rfbport" "$X11VNC_PORT" "-bg" "-noxrecord" "-ncache" "0" "-cursor" "arrow" "-v" "-threads")
    if [ -n "${VNC_PASSWORD:-}" ]; then
        mkdir -p "$HOME/.vnc"
        x11vnc -storepasswd "$VNC_PASSWORD" "$HOME/.vnc/passwd"
        VNC_ARGS+=("-rfbauth" "$HOME/.vnc/passwd")
    else
        VNC_ARGS+=("-nopw")
    fi
    x11vnc "${VNC_ARGS[@]}" > "$SESSION_DIR/logs/x11vnc.log" 2>&1 &
    # We point --web to /usr/share/novnc so it can serve the standalone client
    websockify --web /usr/share/novnc "${NOVNC_PORT:-6080}" "localhost:${VNC_PORT}" > "$SESSION_DIR/logs/websockify.log" 2>&1 &
fi

# Wine Prefix
# (wineserver -k removed to avoid ownership noise)
sleep 1

# Check if prefix needs population from template
if [ "${INIT_PREFIX:-1}" = "1" ] && [ ! -f "$WINEPREFIX/system.reg" ]; then
    if [ -d "/opt/winebot/prefix-template" ]; then
        echo "--> Populating WINEPREFIX from template..."
        cp -rp /opt/winebot/prefix-template/. "$WINEPREFIX/"
    else
        echo "--> Initializing new WINEPREFIX (Template missing)..."
        export WINEDLLOVERRIDES="mscoree,mshtml="
        wineboot -u >/dev/null 2>&1
        wineserver -w
    fi
fi

echo "--> Ensuring wineserver is running..."
wineserver -p >/dev/null 2>&1 &
wineserver -w
echo "--> wineserver is ready."
sleep 2

run_wine_setup_step() {
    local label="$1"
    shift
    local attempts="${WINEBOT_WINE_SETUP_RETRIES:-20}"
    local delay_s="${WINEBOT_WINE_SETUP_RETRY_DELAY_S:-1}"
    local i
    for i in $(seq 1 "$attempts"); do
        if "$@" >/dev/null 2>&1; then
            return 0
        fi
        sleep "$delay_s"
    done
    echo "WARN: ${label} failed after ${attempts} attempts; continuing." >&2
    return 1
}

# Theme & Settings (Skip if already populated from template)
if [ ! -d "/opt/winebot/prefix-template" ]; then
    run_wine_setup_step "FontSmoothing" \
        wine reg add "HKEY_CURRENT_USER\Control Panel\Desktop" /v FontSmoothing /t REG_SZ /d 2 /f || true
    run_wine_setup_step "FontSmoothingType" \
        wine reg add "HKEY_CURRENT_USER\Control Panel\Desktop" /v FontSmoothingType /t REG_DWORD /d 2 /f || true
    run_wine_setup_step "UseXInput2" \
        wine reg add "HKEY_CURRENT_USER\Software\Wine\X11 Driver" /v UseXInput2 /t REG_SZ /d "N" /f || true
    run_wine_setup_step "Managed" \
        wine reg add "HKEY_CURRENT_USER\Software\Wine\X11 Driver" /v Managed /t REG_SZ /d "Y" /f || true

    if [ -x "/scripts/setup/install-theme.sh" ]; then
        /scripts/setup/install-theme.sh || echo "WARN: install-theme.sh failed; continuing." >&2
    fi
fi

# Cleanup
pkill -f "explorer.exe" || true
pkill -f "start.exe" || true
# wineserver -k removed
sleep 1
wineserver -p >/dev/null 2>&1 &

echo "--> Pass 3 complete."
set -e
# wineserver -w removed (blocking)
