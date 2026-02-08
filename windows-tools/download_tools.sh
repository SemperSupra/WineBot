#!/usr/bin/env bash
set -e

# Versions (Pinned for reproducibility)
AUTOIT_VER="3.3.16.1"
AUTOIT_URL="https://www.autoitscript.com/autoit3/files/archive/autoit/autoit-v${AUTOIT_VER}.zip"
AHK_VER="1.1.37.02"
AHK_URL="https://github.com/AutoHotkey/AutoHotkey/releases/download/v${AHK_VER}/AutoHotkey_${AHK_VER}.zip"
PYTHON_VER="3.13.11"
PYTHON_URL="https://www.python.org/ftp/python/${PYTHON_VER}/python-${PYTHON_VER}-embed-amd64.zip"
WINSPY_VER="1.8.4"
WINSPY_URL="https://github.com/strobejb/winspy/releases/download/v${WINSPY_VER}/WinSpy_Release_x86.zip"

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
# The .pth file is named python313._pth (for 3.13)
PTH_FILE="$TOOLS_DIR/Python/python313._pth"
if [ -f "$PTH_FILE" ]; then
    sed -i 's/^#import site/import site/' "$PTH_FILE"
fi

echo "Python installed."

# --- 4. WinSpy++ ---
echo "Downloading WinSpy++..."
WINSPY_URL="https://github.com/strobejb/winspy/releases/download/v1.8.4/WinSpy_Release_x86.zip"
mkdir -p "$TOOLS_DIR/WinSpy"
curl -sL -o /tmp/winspy.zip "$WINSPY_URL"
unzip -q -o /tmp/winspy.zip -d "$TOOLS_DIR/WinSpy"
rm /tmp/winspy.zip
echo "WinSpy++ installed."

# Cleanup
rm -rf /tmp/*.zip
