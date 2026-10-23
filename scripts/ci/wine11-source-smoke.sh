#!/usr/bin/env bash
# SPDX-License-Identifier: MIT
# Bounded, non-publishing, synthetic Wine 11.0/WoW64 headless validation.
set -euo pipefail
export WINEDEBUG=-all
export WINEDLLOVERRIDES='mscoree,mshtml='
export DISPLAY=:99
export WINEPREFIX="$(mktemp -d /tmp/winebot-wine11-prefix.XXXXXX)"
export XDG_RUNTIME_DIR="$(mktemp -d /tmp/winebot-wine11-xdg.XXXXXX)"
chmod 0700 "$XDG_RUNTIME_DIR"
xvfb_pid='' 
cleanup() {
  wineserver -k >/dev/null 2>&1 || true
  if [[ -n "$xvfb_pid" ]]; then kill "$xvfb_pid" >/dev/null 2>&1 || true; fi
  rm -rf "$WINEPREFIX" "$XDG_RUNTIME_DIR"
}
trap cleanup EXIT
fail() { printf 'FAIL: %s\n' "$1"; exit 1; }

[[ "$(wine --version)" == 'wine-11.0' ]] || fail 'version'
printf 'PASS: wine_source_version_11_0\n'

Xvfb :99 -screen 0 1024x768x24 -nolisten tcp >/dev/null 2>&1 &
xvfb_pid=$!
for _ in $(seq 1 15); do
  if xdpyinfo -display :99 >/dev/null 2>&1; then break; fi
  sleep 1
done
xdpyinfo -display :99 >/dev/null 2>&1 || fail 'xvfb'

if ! timeout 90s wineboot -u >/dev/null 2>&1; then fail 'wineboot'; fi
printf 'PASS: fresh_prefix\n'

if ! timeout 45s wine 'C:\\windows\\syswow64\\cmd.exe' /c exit 0 >/dev/null 2>&1; then
  fail 'wow64_32bit_cmd'
fi
printf 'PASS: wow64_32bit_cmd\n'

wine 'C:\\windows\\system32\\notepad.exe' >/dev/null 2>&1 &
for _ in $(seq 1 20); do
  if xdotool search --onlyvisible --name '[Nn]otepad' >/dev/null 2>&1; then
    printf 'PASS: 64bit_notepad_x11_window\n'
    exit 0
  fi
  sleep 1
done
fail 'notepad_visible'
