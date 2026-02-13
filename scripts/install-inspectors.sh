#!/usr/bin/env bash
set -e

TOOLS_DIR="/opt/winebot/windows-tools"

# 1. Check for pre-installed location (from build-time template)
if [ -f "$TOOLS_DIR/WinSpy/WinSpy.exe" ]; then
    echo "WinSpy++ already pre-installed at $TOOLS_DIR/WinSpy/WinSpy.exe"
    exit 0
fi

if [ -f "$TOOLS_DIR/WinSpy/winspy.exe" ]; then
    echo "WinSpy++ already pre-installed at $TOOLS_DIR/WinSpy/winspy.exe"
    exit 0
fi

# If we are not root and can't write to TOOLS_DIR, use a local dir
if [ ! -w "$TOOLS_DIR" ]; then
    echo "Warning: No write access to $TOOLS_DIR. Using $HOME/windows-tools instead."
    TOOLS_DIR="$HOME/windows-tools"
fi

mkdir -p "$TOOLS_DIR/WinSpy"

WINSPY_URL="https://github.com/strobejb/winspy/releases/download/v1.8.4/WinSpy_Release_x86.zip"

echo "Downloading WinSpy++..."
curl -sL -o /tmp/winspy.zip "$WINSPY_URL"
unzip -q -o /tmp/winspy.zip -d "$TOOLS_DIR/WinSpy"
rm /tmp/winspy.zip

echo "WinSpy++ installed to $TOOLS_DIR/WinSpy"
