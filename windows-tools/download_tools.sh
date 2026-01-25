#!/usr/bin/env bash
set -e

# Versions
AUTOIT_URL="https://www.autoitscript.com/cgi-bin/getfile.pl?autoit3/autoit-v3.zip"
AHK_URL="https://github.com/AutoHotkey/AutoHotkey/releases/download/v1.1.37.02/AutoHotkey_1.1.37.02.zip"
PYTHON_VER="3.11.9"
PYTHON_URL="https://www.python.org/ftp/python/${PYTHON_VER}/python-${PYTHON_VER}-embed-amd64.zip"

TOOLS_DIR="/opt/winebot/windows-tools"
mkdir -p "$TOOLS_DIR"

# --- 1. AutoIt v3 ---
echo "Downloading AutoIt..."
mkdir -p "$TOOLS_DIR/AutoIt"
curl -sL -o /tmp/autoit.zip "$AUTOIT_URL"
unzip -q -o /tmp/autoit.zip -d "$TOOLS_DIR/AutoIt"
rm /tmp/autoit.zip
# AutoIt zip often has a nested "install" folder structure, let's flatten if needed or just use as is.
# Usually it extracts to "install/". Let's check if we need to move files.
if [ -d "$TOOLS_DIR/AutoIt/install" ]; then
    mv "$TOOLS_DIR/AutoIt/install"/* "$TOOLS_DIR/AutoIt/"
    rmdir "$TOOLS_DIR/AutoIt/install"
fi
echo "AutoIt installed."

# --- 2. AutoHotkey v1.1 ---
echo "Downloading AutoHotkey..."
mkdir -p "$TOOLS_DIR/AutoHotkey"
curl -sL -o /tmp/ahk.zip "$AHK_URL"
unzip -q -o /tmp/ahk.zip -d "$TOOLS_DIR/AutoHotkey"
rm /tmp/ahk.zip
echo "AutoHotkey installed."

# --- 3. Python Embedded ---
echo "Downloading Python ${PYTHON_VER}..."
mkdir -p "$TOOLS_DIR/Python"
curl -sL -o /tmp/python.zip "$PYTHON_URL"
unzip -q -o /tmp/python.zip -d "$TOOLS_DIR/Python"
rm /tmp/python.zip

# Enable 'site' package for pip to work
# The .pth file is named python311._pth (for 3.11)
PTH_FILE="$TOOLS_DIR/Python/python311._pth"
if [ -f "$PTH_FILE" ]; then
    sed -i 's/^#import site/import site/' "$PTH_FILE"
fi

echo "Python installed."

# Cleanup
rm -rf /tmp/*.zip
