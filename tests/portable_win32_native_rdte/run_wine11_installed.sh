#!/usr/bin/env bash
# SPDX-License-Identifier: MIT
# Actual PE binaries installed inside an isolated Wine 11 prefix.
# Different from native Windows PowerShell installer acceptance.
set -euo pipefail
export DISPLAY=:99 WINEARCH=wow64 WINEDEBUG=-all
export WINEDLLOVERRIDES='mscoree,mshtml='
[[ "$(wine --version)" == 'wine-11.0' ]] || { echo 'FAIL: wrong_wine_version'; exit 1; }
export WINEPREFIX="$(mktemp -d /tmp/wine11-install-prefix.XXXXXX)"
export XDG_RUNTIME_DIR="$(mktemp -d /tmp/wine11-install-xdg.XXXXXX)"
chmod 0700 "$XDG_RUNTIME_DIR"
package="$(mktemp -d /tmp/wine11-package.XXXXXX)"
# The helper refuses preexisting package directories.
rmdir "$package"
root="$WINEPREFIX/drive_c/users/winebot/AppData/Local/WineBotToolkit"
xvfb_pid=''
cleanup() {
  wineserver -k >/dev/null 2>&1 || true
  [[ -z "$xvfb_pid" ]] || kill "$xvfb_pid" >/dev/null 2>&1 || true
  rm -rf "$WINEPREFIX" "$XDG_RUNTIME_DIR" "$package"
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
helper=/opt/rdte-tests/wine11_package_stage.py
python3 "$helper" prepare /opt/winebot-wine/rdte "$package"
for version in v1 v2; do
  python3 "$helper" install "$package" "$root" "$version"
  python3 "$helper" verify "$root/$version"
done
if python3 "$helper" install "$package" "$root" v1 >/dev/null 2>&1; then
  echo 'FAIL: overwrite_accepted'; exit 1
fi
if python3 "$helper" install "$package" "$root" ../outside >/dev/null 2>&1; then
  echo 'FAIL: traversal_accepted'; exit 1
fi
tampered="$(mktemp -d /tmp/wine11-bad-package.XXXXXX)"
cp -a "$package/." "$tampered/"
printf 'X' >>"$tampered/bin/win_event_fixture.exe"
if python3 "$helper" install "$tampered" "$root" tamper >/dev/null 2>&1; then
  echo 'FAIL: tampered_binary_accepted'; exit 1
fi
rm -rf "$tampered"
echo 'PASS: overwrite_traversal_and_digest_negatives'
# Installed-file tamper must be observable independently of source-package hashes.
printf 'X' >>"$root/v1/bin/win_event_fixture.exe"
if python3 "$helper" verify "$root/v1" >/dev/null 2>&1; then
  echo 'FAIL: modified_installed_binary_accepted'; exit 1
fi
cp "$package/bin/win_event_fixture.exe" "$root/v1/bin/win_event_fixture.exe"
python3 "$helper" verify "$root/v1"
for version in v1 v2; do
  observer="$root/$version/bin/win_event_observer.exe"
  fixture="$root/$version/bin/win_event_fixture.exe"
  for rep in $(seq 1 6); do
    timeout 95s python3 /opt/rdte-tests/probe.py --wine "$observer" "$fixture"
  done
  timeout 75s python3 /opt/rdte-tests/probe_control_stop.py "$observer"
  echo "PASS: wine11_installed_${version}_six_fixture_reps_and_control_negative"
done
echo 'PASS: wine11_installed_12_repeated_fixture_sessions'
python3 "$helper" uninstall "$root" v1
[[ -f "$root/v2/bin/win_event_fixture.exe" ]] || { echo 'FAIL: sibling_lost'; exit 1; }
python3 "$helper" uninstall "$root" v2
[[ ! -e "$root/v1" && ! -e "$root/v2" ]] || { echo 'FAIL: uninstall_residue'; exit 1; }
echo 'PASS: wine11_real_installed_x64_pe_two_versions_and_teardown'
