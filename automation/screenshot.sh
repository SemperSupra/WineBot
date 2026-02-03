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
REQUEST_ID="${WINEBOT_REQUEST_ID:-}"
USER_TAG="${WINEBOT_USER_TAG:-}"
TARGET="/tmp"
TARGET_SET="0"

# Helper for usage
usage() {
    echo "Usage: $0 [options] [path|directory]"
    echo "Options:"
    echo "  -w, --window <id>   Window ID to capture (default: root)"
    echo "  -d, --delay <sec>   Delay in seconds before capture (default: 0)"
    echo "  -l, --label <text>  Add text annotation to bottom of image"
    echo "      --request-id    Request ID to embed in metadata"
    echo "      --tag <text>    User tag to embed in metadata"
    echo "  -h, --help          Show this help"
    echo ""
    echo "Arguments:"
    echo "  path|directory      Output file path or directory (default: session screenshots or /tmp)"
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
        --request-id)
            REQUEST_ID="$2"
            shift 2
            ;;
        --tag)
            USER_TAG="$2"
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
            TARGET_SET="1"
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

timestamp_unix="$(date +%s)"
timestamp_utc="$(date -u +%Y-%m-%dT%H:%M:%SZ)"
session_id="${WINEBOT_SESSION_ID:-}"
session_dir="${WINEBOT_SESSION_DIR:-}"
if [ -z "$session_id" ] || [ -z "$session_dir" ]; then
    if [ -f "/tmp/winebot_current_session" ]; then
        session_dir="$(cat /tmp/winebot_current_session 2>/dev/null || true)"
        if [ -n "$session_dir" ]; then
            session_id="$(basename "$session_dir")"
        fi
    fi
fi

if [ "$TARGET_SET" = "0" ] && [ -n "$session_dir" ]; then
    TARGET="${session_dir%/}/screenshots"
    mkdir -p "$TARGET"
fi

app_exe="${APP_EXE:-}"
app_args="${APP_ARGS:-}"
app_name="${APP_NAME:-}"
if [ -z "$app_name" ] && [ -n "$app_exe" ]; then
    app_name="$(basename "$app_exe")"
fi

window_title=""
if [ "$WINDOW_ID" = "root" ]; then
    window_title="root"
else
    if [ -x "/automation/x11.sh" ]; then
        window_title="$(/automation/x11.sh window-title "$WINDOW_ID" 2>/dev/null || true)"
    elif [ -x "$(dirname "$0")/x11.sh" ]; then
        window_title="$("$(dirname "$0")/x11.sh" window-title "$WINDOW_ID" 2>/dev/null || true)"
    elif command -v xdotool >/dev/null 2>&1; then
        window_title="$(xdotool getwindowname "$WINDOW_ID" 2>/dev/null || true)"
    fi
fi

if [ -z "$REQUEST_ID" ]; then
    REQUEST_ID="${timestamp_unix}-${RANDOM}"
fi

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
        import -display "$display_value" -window "$WINDOW_ID" png:- | \
        convert png:- "$output_path"
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

META_OUTPUT_PATH="${output_path}.json" \
META_TIMESTAMP_UTC="$timestamp_utc" \
META_TIMESTAMP_UNIX="$timestamp_unix" \
META_SESSION_ID="$session_id" \
META_SESSION_DIR="$session_dir" \
META_WINDOW_ID="$WINDOW_ID" \
META_WINDOW_TITLE="$window_title" \
META_APP_NAME="$app_name" \
META_APP_ARGS="$app_args" \
META_APP_EXE="$app_exe" \
META_REQUEST_ID="$REQUEST_ID" \
META_USER_TAG="$USER_TAG" \
python3 - <<'PY'
import json
import os
import struct
import tempfile
import zlib

def get(key):
    value = os.environ.get(key)
    return value if value else None

data = {
    "timestamp_utc": get("META_TIMESTAMP_UTC"),
    "timestamp_unix": get("META_TIMESTAMP_UNIX"),
    "session_id": get("META_SESSION_ID"),
    "session_dir": get("META_SESSION_DIR"),
    "window_id": get("META_WINDOW_ID"),
    "window_title": get("META_WINDOW_TITLE"),
    "app_name": get("META_APP_NAME"),
    "app_args": get("META_APP_ARGS"),
    "app_exe": get("META_APP_EXE"),
    "request_id": get("META_REQUEST_ID"),
    "user_tag": get("META_USER_TAG"),
}

out_path = os.environ.get("META_OUTPUT_PATH")
if out_path:
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=True, indent=2, sort_keys=True)

png_path = out_path
if png_path and png_path.endswith(".json"):
    png_path = png_path[:-5]

meta_items = {f"winebot_{k}": v for k, v in data.items() if v}

if png_path and meta_items:
    with open(png_path, "rb") as f:
        sig = f.read(8)
        if sig != b"\x89PNG\r\n\x1a\n":
            raise SystemExit(0)
        chunks = []
        while True:
            header = f.read(8)
            if len(header) < 8:
                break
            length, ctype = struct.unpack(">I4s", header)
            chunk = f.read(length)
            crc = f.read(4)
            chunks.append((ctype, chunk, crc))
            if ctype == b"IEND":
                break

    text_chunks = []
    for key, value in meta_items.items():
        key_bytes = key.encode("ascii", errors="ignore")[:79]
        value_bytes = value.encode("ascii", errors="replace")
        data_bytes = key_bytes + b"\x00" + value_bytes
        crc = zlib.crc32(b"tEXt" + data_bytes) & 0xFFFFFFFF
        text_chunks.append((b"tEXt", data_bytes, struct.pack(">I", crc)))

    target_dir = os.path.dirname(png_path) or "."
    with tempfile.NamedTemporaryFile("wb", delete=False, dir=target_dir) as tmp:
        tmp.write(sig)
        inserted = False
        for ctype, chunk, crc in chunks:
            tmp.write(struct.pack(">I", len(chunk)))
            tmp.write(ctype)
            tmp.write(chunk)
            tmp.write(crc)
            if ctype == b"IHDR" and not inserted:
                for ttype, tdata, tcrc in text_chunks:
                    tmp.write(struct.pack(">I", len(tdata)))
                    tmp.write(ttype)
                    tmp.write(tdata)
                    tmp.write(tcrc)
                inserted = True
    os.replace(tmp.name, png_path)
PY

echo "$output_path"
