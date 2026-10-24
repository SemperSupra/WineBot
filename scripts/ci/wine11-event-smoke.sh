#!/usr/bin/env bash
# SPDX-License-Identifier: MIT
# Synthetic Win32 event observer vs X11 window presence. No raw-event publication.
set -euo pipefail
export DISPLAY=:99 WINEARCH="${WINEARCH:-wow64}" WINEDEBUG=-all
export WINEDLLOVERRIDES='mscoree,mshtml='
export WINEPREFIX="$(mktemp -d /tmp/wine11-events.XXXXXX)"
export XDG_RUNTIME_DIR="$(mktemp -d /tmp/wine11-xdg.XXXXXX)"
chmod 0700 "$XDG_RUNTIME_DIR"
observation_file="$(mktemp /tmp/wine11-observation.XXXXXX)"
xvfb_pid=''
observer_pid=''
fixture_pid=''
cleanup() {
  if [[ -n "$observer_pid" ]]; then kill "$observer_pid" 2>/dev/null || true; fi
  if [[ -n "$fixture_pid" ]]; then kill "$fixture_pid" 2>/dev/null || true; fi
  wineserver -k >/dev/null 2>&1 || true
  if [[ -n "$xvfb_pid" ]]; then kill "$xvfb_pid" 2>/dev/null || true; fi
  rm -rf "$observation_file" "$WINEPREFIX" "$XDG_RUNTIME_DIR"
}
trap cleanup EXIT
fail() { printf 'FAIL: %s\n' "$1"; exit 1; }
python3 /usr/local/bin/verify-wine11-events --self-test || fail 'schema_self_test'
Xvfb :99 -screen 0 1024x768x24 -nolisten tcp >/dev/null 2>&1 &
xvfb_pid=$!
for _ in $(seq 1 20); do
  xdotool getdisplaygeometry --shell >/dev/null 2>&1 && break
  sleep 1
done
xdotool getdisplaygeometry --shell >/dev/null 2>&1 || fail 'x11_ready'
timeout 90s wineboot -u >/dev/null 2>&1 || fail 'wineboot'
timeout 22s wine /opt/winebot-wine/rdte/win_event_observer.exe >"$observation_file" 2>/dev/null &
observer_pid=$!
ready=0
for _ in $(seq 1 50); do
  if grep -Fq '"kind":"ready"' "$observation_file"; then ready=1; break; fi
  kill -0 "$observer_pid" 2>/dev/null || break
  sleep 0.2
done
[[ "$ready" == 1 ]] || fail 'observer_ready'
timeout 15s wine /opt/winebot-wine/rdte/win_event_fixture.exe >/dev/null 2>&1 &
fixture_pid=$!
visible=0
for _ in $(seq 1 40); do
  if xdotool search --onlyvisible --name 'WineBot RDTE Fixture' >/dev/null 2>&1; then
    visible=1
    break
  fi
  kill -0 "$fixture_pid" 2>/dev/null || break
  sleep 0.2
done
[[ "$visible" == 1 ]] || fail 'x11_fixture_visible'
printf 'PASS: x11_fixture_visible\n'
wait "$fixture_pid" || fail 'fixture_exit'
fixture_pid=''
wait "$observer_pid" || fail 'observer_exit'
observer_pid=''
python3 /usr/local/bin/verify-wine11-events "$observation_file" || fail 'semantic_win_events'
