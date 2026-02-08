#!/usr/bin/env bash
# 00-setup-user.sh: Handle root-level setup and privilege dropping

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
    
    # Always re-assert ownership and permissions if running as root
    echo "--> Preparing environment for winebot user (UID: $USER_ID)..."
    
    # Critical: Clean up any stale root-owned wineserver sockets
    rm -rf /tmp/.wine-$(id -u winebot) 2>/dev/null || true

    chown -R winebot:winebot "$WINEPREFIX" "/home/winebot" "/artifacts" || echo "Warning: chown failed"
    chmod 1777 /tmp
    chmod 777 "$WINEPREFIX"

    # Handle .X11-unix specifically for Xvfb
    mkdir -p /tmp/.X11-unix
    chmod 1777 /tmp/.X11-unix

    # Drop privileges and re-execute the main entrypoint as 'winebot'
    # We assume the caller (entrypoint.sh) handles the exec
    # Returning 0 means "continue as user", 1 means "stop" (not used here)
fi
