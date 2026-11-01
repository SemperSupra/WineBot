#!/usr/bin/env bash
# SPDX-License-Identifier: MIT
# Pinned Wine 11.0 synthetic target epoch differential vs native Win32.
set -euo pipefail
export DISPLAY=:99 WINEARCH=wow64 WINEDEBUG=-all WINEDLLOVERRIDES='mscoree,mshtml='
[[ "$(wine --version)" == 'wine-11.0' ]] || { echo 'FAIL: wrong_wine11_version'; exit 1; }
export WINEPREFIX="$(mktemp -d /tmp/wine11-target-correlation.XXXXXX)"
export XDG_RUNTIME_DIR="$(mktemp -d /tmp/wine11-target-xdg.XXXXXX)"
chmod 0700 "$XDG_RUNTIME_DIR"
xvfb_pid=''
cleanup() {
  wineserver -k >/dev/null 2>&1 || true
  [[ -z "$xvfb_pid" ]] || kill "$xvfb_pid" >/dev/null 2>&1 || true
  rm -rf "$WINEPREFIX" "$XDG_RUNTIME_DIR"
}
trap cleanup EXIT
Xvfb :99 -screen 0 1024x768x24 -nolisten tcp >/dev/null 2>&1 &
xvfb_pid=$!
for _ in $(seq 1 40); do
  xdotool getdisplaygeometry --shell >/dev/null 2>&1 && break
  sleep 0.2
done
xdotool getdisplaygeometry --shell >/dev/null 2>&1 || { echo 'FAIL: x11_not_ready'; exit 1; }
timeout 100s wineboot -u >/dev/null 2>&1 || { echo 'FAIL: wine11_boot'; exit 1; }
timeout 90s python3 /opt/rdte-tests/probe_target.py --wine \
  /opt/winebot-wine/rdte/win_event_target_probe.exe \
  /opt/winebot-wine/rdte/win_event_fixture.exe
echo 'PASS: wine11_target_correlated_fixture_vs_native_contract'
echo 'LIMITATION: fixture epochs are not authenticated principal/target identity or actuator authority'
