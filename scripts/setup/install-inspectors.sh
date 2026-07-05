#!/usr/bin/env bash
set -e

TOOLS_DIR="/opt/winebot/windows-tools"

# 1. Check for pre-installed location (from build-time template)
if [ -f "$TOOLS_DIR/WinSpy/wininspect.exe" ] && [ -f "$TOOLS_DIR/WinSpy/wininspectd.exe" ]; then
    echo "WinInspect already pre-installed at $TOOLS_DIR/WinSpy"
    exit 0
fi

# If we are not root and can't write to TOOLS_DIR, use a local dir
if [ ! -w "$TOOLS_DIR" ]; then
    echo "Warning: No write access to $TOOLS_DIR. Using $HOME/windows-tools instead."
    TOOLS_DIR="$HOME/windows-tools"
fi

mkdir -p "$TOOLS_DIR/WinSpy"

WININSPECT_VERSION="${WININSPECT_VERSION:-v0.4.0}"
WININSPECT_SHA256="${WININSPECT_SHA256:-83b64999fef9ab01d749ab94193899e3915774d217900ac80c3c34021ff3e416}"
WININSPECT_URL="https://github.com/SemperSupra/WinInspect/releases/download/${WININSPECT_VERSION}/WinInspectPortable-${WININSPECT_VERSION#v}.zip"

echo "Downloading WinInspect ${WININSPECT_VERSION}..."
curl -fsSL -o /tmp/wininspect.zip "$WININSPECT_URL"
echo "${WININSPECT_SHA256}  /tmp/wininspect.zip" | sha256sum -c -
unzip -q -o /tmp/wininspect.zip -d "$TOOLS_DIR/WinSpy"
rm /tmp/wininspect.zip

echo "WinInspect installed to $TOOLS_DIR/WinSpy"
