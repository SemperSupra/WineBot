#!/usr/bin/env bash
set -e

# Defaults
export WINEPREFIX="${WINEPREFIX:-/wineprefix}"
export DISPLAY="${DISPLAY:-:99}"
export SCREEN="${SCREEN:-1280x720x24}"

# 1. Root Level Setup (User creation, permissions)
source /scripts/init/00-setup-user.sh

# Drop privileges and re-execute this script as 'winebot'
if [ "$(id -u)" = "0" ]; then
    exec gosu winebot "$0" "$@"
fi

# --- USER CONTEXT (winebot) ---

# Prevent multiple entrypoint runs
if [ -f /tmp/entrypoint.user.pid ]; then
    existing_pid="$(cat /tmp/entrypoint.user.pid)"
else
    existing_pid=""
fi
if [ -n "$existing_pid" ] && ps -p "$existing_pid" > /dev/null 2>&1; then
    echo "--> Entrypoint already running for user $(id -un) (PID ${existing_pid})."
    if [ $# -gt 0 ]; then
        exec "$@"
    else
        exit 0
    fi
fi
echo $$ > /tmp/entrypoint.user.pid

# Load runtime configuration overrides
WINEBOT_CONFIG_FILE="/wineprefix/winebot.env"
WINEBOT_INSTANCE_CONFIG="/wineprefix/winebot.${HOSTNAME}.env"

if [ -f "$WINEBOT_CONFIG_FILE" ]; then
    chmod 600 "$WINEBOT_CONFIG_FILE"
    set -a; source "$WINEBOT_CONFIG_FILE"; set +a
fi
if [ -f "$WINEBOT_INSTANCE_CONFIG" ]; then
    chmod 600 "$WINEBOT_INSTANCE_CONFIG"
    set -a; source "$WINEBOT_INSTANCE_CONFIG"; set +a
fi

export BUILD_INTENT="${BUILD_INTENT:-rel}"
if [ -z "${WINEBOT_LOG_LEVEL:-}" ]; then
    case "$BUILD_INTENT" in
        dev) export WINEBOT_LOG_LEVEL="DEBUG" ;;
        test) export WINEBOT_LOG_LEVEL="INFO" ;;
        *) export WINEBOT_LOG_LEVEL="WARN" ;;
    esac
fi

if { [ "$BUILD_INTENT" = "rel" ] || [ "$BUILD_INTENT" = "rel-runner" ]; } && [ "${WINEBOT_SUPPORT_MODE:-0}" = "1" ]; then
    export WINEBOT_LOG_LEVEL="INFO"
    ttl_min="${WINEBOT_SUPPORT_MODE_MINUTES:-60}"
    now_epoch="$(date -u +%s)"
    export WINEBOT_SUPPORT_MODE_UNTIL_EPOCH="$((now_epoch + (ttl_min * 60)))"
    echo "--> Support Mode enabled for ${ttl_min} minutes (until epoch ${WINEBOT_SUPPORT_MODE_UNTIL_EPOCH})."
fi

# 2. Infrastructure Setup (Session, X11, WM)
echo "--> Pass 2: Infrastructure..."
source /scripts/init/10-setup-infra.sh

# 3. Wine Environment Setup (Prefix, Theme, VNC)
echo "--> Pass 3: Wine Environment..."
source /scripts/init/20-setup-wine.sh

# 4. Service Startup (API, Recorder, Supervisor)
echo "--> Pass 4: Services..."
source /scripts/init/30-start-services.sh

if [ "${DEBUG:-0}" = "1" ]; then
    echo "--> DEBUG: Windows automation tool versions..."
    (autoit /? | head -n 2) || true
    (ahk /? | head -n 2) || true
    (winpy -c "import sys; print(sys.version)" | head -n 1) || true
fi

# Keep container alive or run app
if [ $# -eq 0 ]; then
    if [ -n "${APP_EXE:-}" ]; then
        echo "--> Launching application: ${APP_EXE} ${APP_ARGS:-}"
        # We use 'wine' explicitly if it looks like a Windows path or exe
        if [[ "$APP_EXE" == *.exe ]] || [[ "$APP_EXE" == *.bat ]] || [[ "$APP_EXE" == *.msi ]] || [[ "$APP_EXE" == *\\* ]]; then
            # Run wine and capture exit code
            # We don't use 'exec' here because we might want to keep the container alive
            # or handle cleanup. But for CLI apps, we usually want the container to exit when the app exits.
            wine "$APP_EXE" ${APP_ARGS:-}
            EXIT_CODE=$?
            exit $EXIT_CODE
        else
            # Native command
            "$APP_EXE" ${APP_ARGS:-}
            EXIT_CODE=$?
            exit $EXIT_CODE
        fi
    fi
    tail -f /dev/null
else
    "$@"
    EXIT_CODE=$?
    exit $EXIT_CODE
fi
