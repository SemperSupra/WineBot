#!/usr/bin/env bash
# Loadout Manager — install curated software stacks for specific use cases.
#
# Usage:
#   WINEBOT_LOADOUT=installer-qa      (single loadout)
#   WINEBOT_LOADOUT=qa,re,cibuild     (multiple, comma-separated)
#
# Each loadout installs its required tools (Linux packages + Wine components).
# Called from 20-setup-wine.sh at container boot.

set -e

LOADOUT="${WINEBOT_LOADOUT:-}"
PREFIX="${WINEPREFIX:-/wineprefix}"
DRIVE_C="$PREFIX/drive_c"
LOADOUT_DIR="$DRIVE_C/loadout"

if [ -z "$LOADOUT" ]; then
    echo "--> No loadout selected (WINEBOT_LOADOUT="").
    echo "    Available: installer-qa, legacy-app, ci-build, re-sandbox, installer-builder, batch-proc"
    exit 0
fi

mkdir -p "$DRIVE_C/artifacts" "$LOADOUT_DIR" 2>/dev/null
chown -R winebot:winebot "$DRIVE_C/artifacts" "$LOADOUT_DIR" 2>/dev/null || true

echo "--> Installing loadout: $LOADOUT"

IFS=',' read -ra LOADS <<< "$LOADOUT"

# ── Per-loadout installers ──

install_7zip() {
    local dl="$DRIVE_C/artifacts/7z-installer.exe"
    if [ ! -f "$DRIVE_C/Program Files/7-Zip/7z.exe" ]; then
        echo "    Installing 7-Zip..."
        curl -sL "https://7-zip.org/a/7z2409-x64.exe" -o "$dl"
        chown winebot:winebot "$dl" 2>/dev/null || true
        gosu winebot env DISPLAY=:99 WINEPREFIX="$PREFIX" WINEDEBUG=-all \
            wine "$dl" /S 2>/dev/null || true
        rm -f "$dl"
    fi
}

install_irfanview() {
    local dl="$DRIVE_C/artifacts/iview-installer.exe"
    if [ ! -f "$DRIVE_C/Program Files/IrfanView/i_view64.exe" ]; then
        echo "    Installing IrfanView..."
        curl -sL "https://www.irfanview.info/files/iview460_x64_setup.exe" -o "$dl"
        chown winebot:winebot "$dl" 2>/dev/null || true
        gosu winebot env DISPLAY=:99 WINEPREFIX="$PREFIX" WINEDEBUG=-all \
            wine "$dl" /silent /desktop=0 2>/dev/null || true
        rm -f "$dl"
    fi
}

install_notepadpp() {
    local dl="$DRIVE_C/artifacts/npp-installer.exe"
    if [ ! -f "$DRIVE_C/Program Files/Notepad++/notepad++.exe" ]; then
        echo "    Installing Notepad++..."
        curl -sL "https://github.com/notepad-plus-plus/notepad-plus-plus/releases/download/v8.7.9/npp.8.7.9.Installer.x64.exe" -o "$dl"
        chown winebot:winebot "$dl" 2>/dev/null || true
        gosu winebot env DISPLAY=:99 WINEPREFIX="$PREFIX" WINEDEBUG=-all \
            wine "$dl" /S 2>/dev/null || true
        rm -f "$dl"
    fi
}

for load in "${LOADS[@]}"; do
    load=$(echo "$load" | xargs)  # trim whitespace
    echo ""
    echo "  Loadout: $load"

    case "$load" in
        installer-qa)
            echo "  ├─ Linux tools: already present (curl, file, sha256sum)"
            echo "  ├─ Wine tools: cmd.exe, reg.exe, certutil.exe (built-in)"
            echo "  └─ No additional installs needed"
            ;;

        legacy-app)
            echo "  ├─ Wine: vcrun2019 runtime"
            winetricks --unattended vcrun2019 2>/dev/null || echo "     [WARN] vcrun2019 install failed"
            wineserver -w
            echo "  ├─ Notepad++ (sample legacy app)"
            install_notepadpp
            echo "  ├─ AHK hook DLLs: pre-installed"
            echo "  └─ dialog_watcher.ahk: pre-installed"
            ;;

        ci-build)
            echo "  ├─ Wine: .NET 4.8 Framework"
            winetricks --unattended dotnet48 2>/dev/null || echo "     [WARN] dotnet48 install failed"
            wineserver -w
            echo "  ├─ 7-Zip (archive packaging)"
            install_7zip
            echo "  └─ Windows build tools: cmd.exe, cabarc, certutil (built-in)"
            ;;

        re-sandbox)
            echo "  ├─ Linux tools: file, strings, sha256sum, strace, objdump"
            apt-get install -y -qq strace binutils 2>/dev/null || true
            echo "  ├─ Wine tools: certutil, reg, wine_dbg (built-in)"
            echo "  └─ No additional installs needed"
            ;;

        installer-builder)
            echo "  ├─ Wine: NSIS + .NET 4.8"
            winetricks --unattended nsis,dotnet48 2>/dev/null || echo "     [WARN] winetricks install failed"
            wineserver -w
            echo "  ├─ 7-Zip (archive repackaging)"
            install_7zip
            echo "  └─ Installer build tools: makensis, WiX"
            ;;

        batch-proc)
            echo "  ├─ Linux: ImageMagick, Ghostscript"
            apt-get install -y -qq imagemagick ghostscript 2>/dev/null || true
            echo "  ├─ IrfanView (batch image processing)"
            install_irfanview
            echo "  ├─ 7-Zip (archive handling)"
            install_7zip
            echo "  └─ Cross-platform processing pipeline ready"
            ;;

        *)
            echo "  └─ Unknown loadout: $load"
            ;;
    esac
    echo ""
done

# Write loadout manifest for introspection
cat > "$LOADOUT_DIR/loadout.json" << EOF
{
  "loadout": "$LOADOUT",
  "installed_at": "$(date -u +%Y-%m-%dT%H:%M:%SZ)",
  "wine_prefix": "$PREFIX"
}
EOF
chown winebot:winebot "$LOADOUT_DIR/loadout.json" 2>/dev/null || true

echo "--> Loadout installation complete: $LOADOUT"
echo "    Manifest: $LOADOUT_DIR/loadout.json"
