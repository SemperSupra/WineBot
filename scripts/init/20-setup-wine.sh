#!/usr/bin/env bash
# 20-setup-wine.sh: Wine Prefix, Theme, and VNC services

# VNC/noVNC
if [ "${ENABLE_VNC:-0}" = "1" ] || [ "${MODE:-headless}" = "interactive" ]; then
    echo "--> Starting VNC/noVNC services..."
    VNC_PORT="${VNC_PORT:-5900}"
    X11VNC_PORT="$VNC_PORT"
    
    # Input Proxy logic would go here, simplified for modularity
    if [ "${WINEBOT_INPUT_TRACE_NETWORK:-0}" = "1" ]; then
        X11VNC_PORT=$((VNC_PORT + 1))
        # Proxy start logic...
        NET_SAMPLE_MS="${WINEBOT_INPUT_TRACE_NETWORK_SAMPLE_MS:-10}"
        python3 -m automation.vnc_input_proxy 
            --listen-port "$VNC_PORT" 
            --target-port "$X11VNC_PORT" 
            --session-dir "$SESSION_DIR" 
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
    x11vnc "${VNC_ARGS[@]}" > "$SESSION_DIR/logs/x11vnc.log" 2>&1
    websockify --web /usr/share/novnc/ "${NOVNC_PORT:-6080}" "localhost:${VNC_PORT}" >/dev/null 2>&1 &
fi

# Wine Prefix
# (wineserver -k removed to avoid ownership noise)
sleep 1
echo "--> Ensuring wineserver is running..."
wineserver -p >/dev/null 2>&1 &
sleep 2

if [ "${INIT_PREFIX:-1}" = "1" ] && [ ! -f "$WINEPREFIX/system.reg" ]; then
    echo "--> Initializing WINEPREFIX..."
    wineboot -u >/dev/null 2>&1 || true
    wineserver -w
fi

# Theme & Settings
wine reg add "HKEY_CURRENT_USER\Control Panel\Desktop" /v FontSmoothing /t REG_SZ /d 2 /f >/dev/null 2>&1
wine reg add "HKEY_CURRENT_USER\Control Panel\Desktop" /v FontSmoothingType /t REG_DWORD /d 2 /f >/dev/null 2>&1
wine reg add "HKEY_CURRENT_USER\Software\Wine\X11 Driver" /v UseXInput2 /t REG_SZ /d "N" /f >/dev/null 2>&1
wine reg add "HKEY_CURRENT_USER\Software\Wine\X11 Driver" /v Managed /t REG_SZ /d "Y" /f >/dev/null 2>&1

if [ -x "/scripts/install-theme.sh" ]; then
    /scripts/install-theme.sh
fi

# Cleanup
pkill -f "explorer.exe" || true
pkill -f "start.exe" || true
# wineserver -k removed
sleep 1
wineserver -p >/dev/null 2>&1 &
# wineserver -w removed (blocking)
