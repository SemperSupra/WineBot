#!/usr/bin/env bash
set -euo pipefail

# Source the X11 helper
if [ -f "/scripts/lib/x11_env.sh" ]; then
    source "/scripts/lib/x11_env.sh"
elif [ -f "$(dirname "$0")/../scripts/lib/x11_env.sh" ]; then
    source "$(dirname "$0")/../scripts/lib/x11_env.sh"
fi

if type winebot_ensure_x11_env >/dev/null 2>&1; then
    winebot_ensure_x11_env
fi

CMD="${1:-help}"
shift || true

case "$CMD" in
    list-windows)
        # IDs + Titles
        xdotool search --onlyvisible --name ".*" 2>/dev/null | while read -r id; do
            title=$(xdotool getwindowname "$id" 2>/dev/null || echo "N/A")
            echo "$id $title"
        done
        ;;
    active-window)
        xdotool getactivewindow 2>/dev/null || echo "No active window"
        ;;
    window-title)
        if [ -z "${1:-}" ]; then echo "Usage: $0 window-title <id>"; exit 1; fi
        xdotool getwindowname "$1"
        ;;
    window-class)
        if [ -z "${1:-}" ]; then echo "Usage: $0 window-class <id>"; exit 1; fi
        xprop -id "$1" WM_CLASS 2>/dev/null | cut -d'=' -f2-
        ;;
    focus)
        if [ -z "${1:-}" ]; then echo "Usage: $0 focus <id>"; exit 1; fi
        xdotool windowactivate "$1"
        ;;
    search)
        if [ "${1:-}" == "--name" ]; then
             shift
             pattern="${1:-}"
             if [ -z "$pattern" ]; then echo "Usage: $0 search --name <pattern>"; exit 1; fi
             xdotool search --name "$pattern"
        else
             echo "Usage: $0 search --name <pattern>"
             exit 1
        fi
        ;;
    xprop)
        xprop "$@"
        ;;
    xwininfo)
        xwininfo "$@"
        ;;
    click-at)
        if [ "$#" -lt 2 ]; then echo "Usage: $0 click-at <x> <y>"; exit 1; fi
        xdotool mousemove --sync "$1" "$2" click 1
        ;;
    help|*)
        echo "Usage: $0 <command> [args]"
        echo "Commands:"
        echo "  list-windows            List visible window IDs and titles"
        echo "  active-window           Get ID of active window"
        echo "  window-title <id>       Get title of window"
        echo "  window-class <id>       Get WM_CLASS of window"
        echo "  focus <id>              Activate/focus window"
        echo "  search --name <pat>     Search windows by name pattern"
        echo "  xprop <id> ...          Run xprop"
        echo "  xwininfo <id> ...       Run xwininfo"
        exit 1
        ;;
esac
