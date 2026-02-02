#!/usr/bin/env bash
#
# Shared X11 Environment Auto-Detection Helper
#
# Usage: source scripts/lib/x11_env.sh && winebot_ensure_x11_env
#

winebot_ensure_x11_env() {
    local debug="${WINEBOT_DEBUG_X11:-0}"
    local fixed_display=0
    local fixed_auth=0

    # --- 1. DISPLAY Detection ---
    if [ -n "${DISPLAY:-}" ]; then
        if [ "$debug" -eq 1 ]; then echo "[DEBUG] DISPLAY is set to '$DISPLAY'. Checking reachability..."; fi
        if command -v xdpyinfo >/dev/null 2>&1; then
             if ! xdpyinfo >/dev/null 2>&1; then
                 echo "[WARN] DISPLAY=$DISPLAY is set but unreachable. Attempting auto-detection..."
                 unset DISPLAY
             else
                 [ "$debug" -eq 1 ] && echo "[DEBUG] DISPLAY=$DISPLAY is reachable."
             fi
        fi
    fi

    if [ -z "${DISPLAY:-}" ]; then
        # Try to detect active X servers
        # Check for /tmp/.X11-unix/X*
        local candidates=()
        if [ -d /tmp/.X11-unix ]; then
            for s in /tmp/.X11-unix/X*; do
                [ -e "$s" ] || continue
                # Extract number, e.g., X99 -> :99
                local num="${s##*X}"
                candidates+=(":$num")
            done
        fi

        # Also check for Xvfb processes if we didn't find socket files (less reliable but fallback)
        # (Skip this if we found candidates via sockets, as sockets are the truth)

        if [ ${#candidates[@]} -eq 0 ]; then
             echo "[ERROR] No active X servers found in /tmp/.X11-unix."
             return 1
        fi

        # Probe candidates
        local found_display=""
        for d in "${candidates[@]}"; do
             if command -v xdpyinfo >/dev/null 2>&1; then
                 if DISPLAY="$d" xdpyinfo >/dev/null 2>&1; then
                     found_display="$d"
                     break
                 fi
             else
                 # If no xdpyinfo, just trust the first one
                 found_display="$d"
                 break
             fi
        done

        if [ -n "$found_display" ]; then
            export DISPLAY="$found_display"
            fixed_display=1
            [ "$debug" -eq 1 ] && echo "[DEBUG] Auto-detected DISPLAY=$DISPLAY"
        else
            echo "[ERROR] Could not find a reachable DISPLAY among: ${candidates[*]}"
            return 1
        fi
    fi

    # --- 2. XAUTHORITY Detection ---
    if [ -z "${XAUTHORITY:-}" ] || [ ! -r "${XAUTHORITY:-}" ]; then
         # Look for xvfb-run style auth files in /tmp/xvfb-run.*
         # These are often directories containing 'Xauthority'
         # Or sometimes files named Xauthority.*
         
         # Strategy: find newest file named *Xauthority* in /tmp or subdirs of /tmp/xvfb-run*
         local auth_candidate=""
         
         # Try find command to locate newest Xauthority file associated with xvfb
         # Limit depth to avoid scanning huge trees, look in /tmp
         # Common patterns: /tmp/xvfb-run.PID/Xauthority
         
         if [ -d /tmp ]; then
             # Find files named Xauthority in /tmp/xvfb-run.* dirs
             local found_files
             found_files=$( { find /tmp -maxdepth 3 -path "/tmp/xvfb-run.*/*Xauthority" -type f -printf '%T@ %p\n' 2>/dev/null || true; } | sort -n | tail -1 | cut -d' ' -f2-)
             
             if [ -n "$found_files" ]; then
                 auth_candidate="$found_files"
             elif [ -f "$HOME/.Xauthority" ]; then
                 auth_candidate="$HOME/.Xauthority"
             fi
         fi

         if [ -n "$auth_candidate" ] && [ -r "$auth_candidate" ]; then
             export XAUTHORITY="$auth_candidate"
             fixed_auth=1
             [ "$debug" -eq 1 ] && echo "[DEBUG] Auto-detected XAUTHORITY=$XAUTHORITY"
         fi
    else
         [ "$debug" -eq 1 ] && echo "[DEBUG] XAUTHORITY is set to '$XAUTHORITY'"
    fi

    if [ "$fixed_display" -eq 1 ] || [ "$fixed_auth" -eq 1 ]; then
        if [ "$debug" -eq 1 ]; then
             echo "[INFO] Fixed X11 environment: DISPLAY=${DISPLAY:-unset} XAUTHORITY=${XAUTHORITY:-unset}"
        fi
    fi
}
