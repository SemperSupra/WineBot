#!/usr/bin/env bash
# Install WineBot API hook DLLs into the Wine prefix
# Called from 20-setup-wine.sh at container boot
#
# winebot_hook.dll: Single IAT-based hook (recommended, no system DLL conflicts)
#   Loaded via: WINEDLLOVERRIDES="winebot_hook=n" wine app.exe
#   Intercepts: MessageBoxW/A, GetSaveFileNameW, GetOpenFileNameW, SHBrowseForFolderW
#
# Per-DLL hooks (advanced): comdlg32.dll, user32.dll, shell32.dll
#   These are full DLL replacements — must be loaded via n,b override and
#   require all internal functions to be exported. Use winebot_hook instead
#   for most cases.

HOOK_DIR="/opt/winebot/hooks"
SYS32="$WINEPREFIX/drive_c/windows/system32"
SYSWOW64="$WINEPREFIX/drive_c/windows/syswow64"

if [ ! -d "$HOOK_DIR" ]; then
    echo "--> Hook DLL directory not found — skipping."
    exit 0
fi

mkdir -p "$SYS32" "$SYSWOW64" 2>/dev/null

echo "--> Installing WineBot hook DLL..."

# winebot_hook.dll (IAT-based, recommended — unique name, no conflicts)
if [ -f "$HOOK_DIR/winebot_hook_64.dll" ]; then
    cp "$HOOK_DIR/winebot_hook_64.dll" "$SYS32/winebot_hook.dll"
    chown winebot:winebot "$SYS32/winebot_hook.dll" 2>/dev/null || true
fi
if [ -f "$HOOK_DIR/winebot_hook_32.dll" ]; then
    cp "$HOOK_DIR/winebot_hook_32.dll" "$SYSWOW64/winebot_hook.dll"
    chown winebot:winebot "$SYSWOW64/winebot_hook.dll" 2>/dev/null || true
fi

echo "  winebot_hook.dll installed. Load with:"
echo "    WINEDLLOVERRIDES=\"winebot_hook=n\" wine app.exe"
echo ""
echo "  Per-DLL hooks (advanced) also available in $HOOK_DIR"
echo "  Use via install-comdlg32-hook.sh or manual copy + n,b override"
