#!/usr/bin/env bash
# 10-setup-infra.sh: Initialize Session, X11, and Window Manager

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

# --- Xvfb Setup ---
rm -f "/tmp/.X${DISPLAY##*:}-lock" "/tmp/.X11-unix/X${DISPLAY##*:}"
Xvfb "$DISPLAY" -screen 0 "$SCREEN" -ac +extension RANDR >/dev/null 2>&1 &
XVFB_PID=$!

echo "--> Waiting for Xvfb on $DISPLAY..."
for i in $(seq 1 30); do
    if xdpyinfo -display "$DISPLAY" >/dev/null 2>&1; then
        echo "--> Xvfb is ready."
        break
    fi
    if [ $i -eq 30 ]; then
        echo "ERROR: Xvfb failed to start."
        exit 1
    fi
    sleep 0.5
done

# --- WM Setup ---
# Configure Openbox (copy configs)
OPENBOX_CONFIG_DIR="${HOME}/.config/openbox"
mkdir -p "$OPENBOX_CONFIG_DIR"
if [ -f "/etc/xdg/openbox/rc.xml" ] && [ ! -f "${OPENBOX_CONFIG_DIR}/rc.xml" ]; then
    cp "/etc/xdg/openbox/rc.xml" "${OPENBOX_CONFIG_DIR}/rc.xml"
fi
if [ -f "/etc/xdg/openbox/menu.xml" ] && [ ! -f "${OPENBOX_CONFIG_DIR}/menu.xml" ]; then
    cp "/etc/xdg/openbox/menu.xml" "${OPENBOX_CONFIG_DIR}/menu.xml"
fi

openbox --replace >/dev/null 2>&1 &

mkdir -p ~/.config/tint2
if [ -f "/etc/xdg/tint2/tint2rc" ]; then
    cp "/etc/xdg/tint2/tint2rc" ~/.config/tint2/tint2rc
fi
tint2 >/dev/null 2>&1 &
