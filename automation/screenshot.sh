#!/usr/bin/env bash
set -euo pipefail

# Source the X11 helper
# Try absolute path first (container), then relative (local dev)
if [ -f "/scripts/lib/x11_env.sh" ]; then
    source "/scripts/lib/x11_env.sh"
elif [ -f "$(dirname "$0")/../scripts/lib/x11_env.sh" ]; then
    source "$(dirname "$0")/../scripts/lib/x11_env.sh"
else
    echo "Warning: x11_env.sh not found. Proceeding with existing env."
fi

# Ensure X11 environment
if type winebot_ensure_x11_env >/dev/null 2>&1; then
    winebot_ensure_x11_env
fi

# Defaults
WINDOW_ID="root"
DELAY_SEC=0
LABEL_TEXT=""
TARGET="/tmp"

# Helper for usage
usage() {
    echo "Usage: $0 [options] [path|directory]"
    echo "Options:"
    echo "  -w, --window <id>   Window ID to capture (default: root)"
    echo "  -d, --delay <sec>   Delay in seconds before capture (default: 0)"
    echo "  -l, --label <text>  Add text annotation to bottom of image"
    echo "  -h, --help          Show this help"
    echo ""
    echo "Arguments:"
    echo "  path|directory      Output file path or directory (default: /tmp)"
}

# Parse Args
# We manually parse to handle mixed flags and positional args easily
while [[ $# -gt 0 ]]; do
    case "$1" in
        -w|--window)
            WINDOW_ID="$2"
            shift 2
            ;; 
        -d|--delay)
            DELAY_SEC="$2"
            shift 2
            ;; 
        -l|--label)
            LABEL_TEXT="$2"
            shift 2
            ;; 
        -h|--help)
            usage
            exit 0
            ;; 
        -*)
            echo "Unknown option: $1"
            usage
            exit 1
            ;; 
        *)
            TARGET="$1"
            shift
            ;; 
    esac
done

# Delay if requested
if [ "$DELAY_SEC" -gt 0 ]; then
    [ "${WINEBOT_DEBUG_X11:-0}" -eq 1 ] && echo "[DEBUG] Sleeping for $DELAY_SEC seconds..."
    sleep "$DELAY_SEC"
fi

# Path handling
# Generate timestamp: YYYY-MM-DD_HH-MM-SS
timestamp=$(date +%Y-%m-%d_%H-%M-%S)
filename="screenshot_${timestamp}.png"

if [ -d "$TARGET" ]; then
    # It's a directory (remove trailing slash if present, then append filename)
    output_path="${TARGET%/}/$filename"
else
    # It's a file path (user specified the exact filename)
    output_path="$TARGET"
    # Ensure directory exists
    mkdir -p "$(dirname "$output_path")"
fi

display_value="${DISPLAY:-:99}"

# Debug output
if [ "${WINEBOT_DEBUG_X11:-0}" -eq 1 ]; then
    echo "[DEBUG] Taking screenshot on DISPLAY=$display_value window=$WINDOW_ID to $output_path"
fi

# Capture
# We prefer 'import' (ImageMagick) as it handles windows and formats well.
if command -v import >/dev/null 2>&1; then
    
    # Construct command
    CMD=("import" "-display" "$display_value" "-window" "$WINDOW_ID")
    
    # If we have a label, we might need an intermediate pipe or post-process?
    # Actually, `import` doesn't do annotation easily in one go. 
    # Better to capture raw, then annotate if needed using 'convert'.
    # But wait, we can just pipe `import ... png:- | convert png:- ... output`
    
    if [ -n "$LABEL_TEXT" ]; then
        # Capture to pipe -> convert (annotate) -> file
        import -display "$display_value" -window "$WINDOW_ID" png:- | \
        convert png:- -gravity South -background Black -fill White \
                -size "x30" -splice 0x30 \
                -annotate +0+5 "$LABEL_TEXT" "$output_path"
    else
        import -display "$display_value" -window "$WINDOW_ID" "$output_path"
    fi

elif command -v xwd >/dev/null 2>&1 && command -v convert >/dev/null 2>&1; then
    # Fallback to xwd + convert
    # xwd takes -id for window ID, or -root
    
    XWD_ARGS=("-display" "$display_value")
    if [ "$WINDOW_ID" == "root" ]; then
        XWD_ARGS+=("-root")
    else
        XWD_ARGS+=("-id" "$WINDOW_ID")
    fi
    
    if [ -n "$LABEL_TEXT" ]; then
        xwd "${XWD_ARGS[@]}" | \
        convert xwd:- -gravity South -background Black -fill White \
                -size "x30" -splice 0x30 \
                -annotate +0+5 "$LABEL_TEXT" "$output_path"
    else
        xwd "${XWD_ARGS[@]}" | convert xwd:- "$output_path"
    fi
else
    echo "Error: Neither 'import' nor 'xwd' found. Cannot take screenshot."
    exit 1
fi

echo "$output_path"