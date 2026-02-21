#!/usr/bin/env bash
set -e

TOOL_NAME="$1"
TOOL_URL="$2"
TOOL_SHA256="$3"
DEST_DIR="$4"

if [ -z "$TOOL_NAME" ] || [ -z "$TOOL_URL" ] || [ -z "$TOOL_SHA256" ] || [ -z "$DEST_DIR" ]; then
    echo "Usage: $0 <name> <url> <sha256> <dest_dir>"
    exit 1
fi

mkdir -p "$DEST_DIR"
echo "Downloading $TOOL_NAME..."
curl -sL -o /tmp/tool.zip "$TOOL_URL"

echo "Verifying integrity of $TOOL_NAME..."
echo "$TOOL_SHA256  /tmp/tool.zip" | sha256sum -c - || {
    echo "ERROR: Checksum mismatch for $TOOL_NAME" >&2
    exit 1
}

unzip -q -o /tmp/tool.zip -d "$DEST_DIR"
rm /tmp/tool.zip

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
