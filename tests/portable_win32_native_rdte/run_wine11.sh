#!/usr/bin/env bash
# SPDX-License-Identifier: MIT
# Test-only: current unmodified C observer and native-fixture oracle on pinned Wine 11.0.
set -euo pipefail
export DISPLAY=:99 WINEARCH=wow64 WINEDEBUG=-all
export WINEDLLOVERRIDES='mscoree,mshtml='
test "$(wine --version)" = 'wine-11.0' || { echo 'FAIL: incorrect_wine_source_version'; exit 1; }
export WINEPREFIX="$(mktemp -d /tmp/wine11-parity-prefix.XXXXXX)"
export XDG_RUNTIME_DIR="$(mktemp -d /tmp/wine11-parity-xdg.XXXXXX)"
chmod 0700 "$XDG_RUNTIME_DIR"
xvfb_pid=''
cleanup() {
  wineserver -k >/dev/null 2>&1 || true
  if [[ -n "$xvfb_pid" ]]; then kill "$xvfb_pid" >/dev/null 2>&1 || true; fi
  rm -rf "$WINEPREFIX" "$XDG_RUNTIME_DIR"
}
trap cleanup EXIT
Xvfb :99 -screen 0 1024x768x24 -nolisten tcp >/dev/null 2>&1 &
xvfb_pid=$!
for _ in $(seq 1 40); do
  if xdotool getdisplaygeometry --shell >/dev/null 2>&1; then break; fi
  sleep 0.2
done
xdotool getdisplaygeometry --shell >/dev/null 2>&1 || { echo 'FAIL: x11_not_ready'; exit 1; }
timeout 100s wineboot -u >/dev/null 2>&1 || { echo 'FAIL: wine11_boot'; exit 1; }
timeout 85s python3 /opt/rdte-tests/probe.py --wine \
  /opt/winebot-wine/rdte/win_event_observer.exe \
  /opt/winebot-wine/rdte/win_event_fixture.exe
printf '%s\n' \
  'PASS: exact_current_observer_under_pinned_wine11_source' \
  'PASS: same_event_sequence_and_private_Q_oracle_as_native_Windows_fixture'
