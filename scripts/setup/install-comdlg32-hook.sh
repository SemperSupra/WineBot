#!/usr/bin/env bash
# Install comdlg32 hook DLL into the Wine prefix
# Called from 20-setup-wine.sh at container boot

HOOK_64="/opt/winebot/comdlg32_hook_64.dll"
HOOK_32="/opt/winebot/comdlg32_hook_32.dll"
SYS32="$WINEPREFIX/drive_c/windows/system32"
SYSWOW64="$WINEPREFIX/drive_c/windows/syswow64"

# Only install if hook DLLs exist
if [ ! -f "$HOOK_64" ] && [ ! -f "$HOOK_32" ]; then
    echo "--> comdlg32 hook DLLs not found — skipping."
    exit 0
fi

echo "--> Installing comdlg32 hook DLLs..."

mkdir -p "$SYS32" "$SYSWOW64" 2>/dev/null

if [ -f "$HOOK_64" ]; then
    cp "$HOOK_64" "$SYS32/comdlg32.dll"
    chown winebot:winebot "$SYS32/comdlg32.dll" 2>/dev/null || true
    echo "  Installed 64-bit hook DLL."
fi

if [ -f "$HOOK_32" ]; then
    cp "$HOOK_32" "$SYSWOW64/comdlg32.dll"
    chown winebot:winebot "$SYSWOW64/comdlg32.dll" 2>/dev/null || true
    echo "  Installed 32-bit hook DLL."
fi

# NOTE: We do NOT set a global override. A global n,b override would load the
# DLL into every Wine process, crashing processes that call comdlg32 functions
# we don't export (e.g. ChooseColor, FindText, PrintDlg, PageSetupDlg).
#
# To enable the hook for a specific application:
#   WINEDLLOVERRIDES="comdlg32=n,b" wine notepad.exe
# Or per-app registry:
#   wine reg add "HKCU\\Software\\Wine\\AppDefaults\\notepad.exe\\DllOverrides" \
#     /v comdlg32 /t REG_SZ /d "n,b" /f
echo "  Comdlg32 hook DLLs installed (disabled by default)."
echo "  Enable per-app: WINEDLLOVERRIDES='comdlg32=n,b' wine notepad.exe"
