#!/usr/bin/env bash
# SPDX-License-Identifier: MIT
# Nonpublishing WineBot service+Wine synthetic fixture qualification.
set -euo pipefail
export DISPLAY=:99 WINEARCH=win64 WINEDEBUG=-all
export WINEPREFIX="$(mktemp -d /tmp/wine-service-prefix.XXXXXX)"
export XDG_RUNTIME_DIR="$(mktemp -d /tmp/wine-service-xdg.XXXXXX)"
chmod 0700 "$XDG_RUNTIME_DIR"
xvfb_pid=''
cleanup() {
  wineserver -k >/dev/null 2>&1 || true
  if [[ -n "$xvfb_pid" ]]; then kill "$xvfb_pid" >/dev/null 2>&1 || true; fi
  rm -rf "$WINEPREFIX" "$XDG_RUNTIME_DIR"
}
trap cleanup EXIT
fail() { printf 'FAIL: %s\n' "$1"; exit 1; }
Xvfb :99 -screen 0 1024x768x24 -nolisten tcp >/dev/null 2>&1 &
xvfb_pid=$!
for _ in $(seq 1 25); do
  xdotool getdisplaygeometry --shell >/dev/null 2>&1 && break
  sleep 0.2
done
xdotool getdisplaygeometry --shell >/dev/null 2>&1 || fail 'xvfb_start'
timeout 90s wineboot -u >/dev/null 2>&1 || fail 'wineboot'
python3 /scripts/ci/wine-events-service-live-smoke.py || fail 'service_wine_observer'
python3 /scripts/ci/wine-events-overflow-live-smoke.py || fail 'burst_wine_observer'
