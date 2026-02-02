#!/usr/bin/env bash
set -e

TOOLS_DIR="/opt/winebot/windows-tools"
mkdir -p "$TOOLS_DIR/WinSpy"

WINSPY_URL="https://github.com/strobejb/winspy/releases/download/v1.8.4/WinSpy_Release_x86.zip"

echo "Downloading WinSpy++..."
curl -sL -o /tmp/winspy.zip "$WINSPY_URL"
unzip -q -o /tmp/winspy.zip -d "$TOOLS_DIR/WinSpy"
rm /tmp/winspy.zip

echo "WinSpy++ installed to $TOOLS_DIR/WinSpy"
