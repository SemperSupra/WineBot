#!/usr/bin/env bash
set -euo pipefail

TOOL_NAME="${1:-}"
TOOL_URL="${2:-}"
TOOL_SHA256="${3:-}"
DEST_DIR="${4:-}"

if [ "$#" -ne 4 ] || [ -z "$TOOL_NAME" ] || [ -z "$TOOL_URL" ] || [ -z "$DEST_DIR" ] ||
   ! [[ "$TOOL_SHA256" =~ ^[0-9a-fA-F]{64}$ ]]; then
    echo "Usage: $0 <name> <url> <sha256> <dest_dir>"
    exit 1
fi

temp_zip="$(mktemp /tmp/winebot-tool.XXXXXXXX.zip)"
trap 'rm -f "$temp_zip"' EXIT

echo "Downloading $TOOL_NAME..."
if ! curl --fail --show-error --silent --location --retry 2 \
    --retry-delay 1 --connect-timeout 15 --max-time 120 \
    --output "$temp_zip" "$TOOL_URL"; then
    echo "ERROR: download failed for $TOOL_NAME" >&2
    exit 1
fi

echo "Verifying integrity of $TOOL_NAME..."
printf '%s  %s\n' "$TOOL_SHA256" "$temp_zip" | sha256sum --check --status || {
    echo "ERROR: Checksum mismatch for $TOOL_NAME" >&2
    exit 1
}

mkdir -p "$DEST_DIR"
unzip -q -o "$temp_zip" -d "$DEST_DIR"

# Custom handling
if [ "$TOOL_NAME" = "AutoIt" ] && [ -d "$DEST_DIR/install" ]; then
    mv "$DEST_DIR/install"/* "$DEST_DIR/"
    rmdir "$DEST_DIR/install"
fi

# Enable site for embedded python
if [ "$TOOL_NAME" = "Python" ]; then
    PTH_FILE="$(find "$DEST_DIR" -maxdepth 1 -name 'python*._pth' | head -n 1)"
    if [ -n "$PTH_FILE" ] && [ -f "$PTH_FILE" ]; then
        sed -i 's/^#import site/import site/' "$PTH_FILE"
    fi
fi

echo "$TOOL_NAME installed to $DEST_DIR"
