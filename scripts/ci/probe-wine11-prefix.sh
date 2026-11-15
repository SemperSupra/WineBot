#!/usr/bin/env bash
# Four bounded, offline Wine 11 discriminators; fixed-category output only.
# All containers are disposable, unprivileged, non-networked public CI.
set -euo pipefail

image="winebot:local-rel"
target_pass=0
for profile in target alternate_prefix prewarmed_control relaxed_pid; do
  pid_limit=256
  prefix=/wineprefix
  if [ "$profile" = alternate_prefix ]; then prefix=/tmp/winebot-cold-prefix; fi
  if [ "$profile" = prewarmed_control ]; then prefix=/opt/winebot/prefix-template; fi
  if [ "$profile" = relaxed_pid ]; then pid_limit=1024; fi

  # Compare runtime environments without changing identity, network, privileges,
  # Wine version or architecture. A control cannot qualify the target.
  options=(--rm --network none --cpus=2 --memory=3g
    --pids-limit="$pid_limit" --security-opt=no-new-privileges
    --user 1000:1000 --entrypoint /bin/sh
    --env HOME=/home/winebot --env DISPLAY=:97
    --env WINEARCH=win64 --env "WINEPREFIX=$prefix")
  set +e
  docker run "${options[@]}" "$image" -ec '
    Xvfb :97 -screen 0 1280x720x24 -noreset >/dev/null 2>&1 &
    ready=0
    i=0
    while [ "$i" -lt 40 ]; do
      if xdpyinfo -display :97 >/dev/null 2>&1; then ready=1; break; fi
      i=$((i + 1))
      sleep 0.2
    done
    [ "$ready" -eq 1 ] || exit 23
    if [ "$WINEPREFIX" = /opt/winebot/prefix-template ]; then
      [ -s "$WINEPREFIX/system.reg" ] || exit 28
      timeout -k 5s 15s wine cmd /c exit 0 >/dev/null 2>&1 || exit 24
      exit 0
    fi
    mkdir -p "$WINEPREFIX" >/dev/null 2>&1 || exit 25
    [ -w "$WINEPREFIX" ] || exit 25
    if timeout -k 5s 90s env WINEDLLOVERRIDES=mscoree,mshtml= wineboot -i >/dev/null 2>&1; then
      code=0
    else
      code=$?
    fi
    if [ "$code" -eq 124 ] || [ "$code" -eq 137 ]; then exit 21; fi
    if [ "$code" -ne 0 ]; then
      [ -s "$WINEPREFIX/system.reg" ] || exit 22
      if timeout -k 5s 15s wine cmd /c exit 0 >/dev/null 2>&1; then exit 26; fi
      exit 27
    fi
    timeout -k 5s 30s wineserver -w >/dev/null 2>&1 || exit 29
    [ -s "$WINEPREFIX/system.reg" ] || exit 28
    timeout -k 5s 15s wine cmd /c exit 0 >/dev/null 2>&1 || exit 24
  ' >/dev/null 2>&1
  result=$?
  set -e
  case "$result" in
    0) stage=pass ;;
    21) stage=boot_timeout ;;
    22) stage=boot_nonzero_registry_missing ;;
    23) stage=x11_unready ;;
    24) stage=command_failed ;;
    25) stage=prefix_unwritable ;;
    26) stage=boot_nonzero_registry_command_pass ;;
    27) stage=boot_nonzero_registry_command_fail ;;
    28) stage=registry_missing ;;
    29) stage=server_wait_failed ;;
    *) stage=container_failed ;;
  esac
  printf 'WINE_PREFIX_PROBE profile=%s stage=%s\n' "$profile" "$stage"
  if [ "$profile" = target ] && [ "$result" -eq 0 ]; then target_pass=1; fi
done
if [ "$target_pass" -ne 1 ]; then
  echo 'WINE_PREFIX_PROBE stage=target_mode_unqualified'
  exit 1
fi
echo 'WINE_PREFIX_PROBE stage=target_preflight_pass'
