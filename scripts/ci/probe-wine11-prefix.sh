#!/usr/bin/env bash
# Disposable source-qualified Wine 11 cold-prefix probe, run only on public CI.
# No application/host information, Wine logs, paths, screenshots or artifacts escape.
set -euo pipefail

image="winebot:local-rel"
target_pass=0
for caps in standard hardened; do
  for arch in default win64 win32; do
    # Every cell is network-disabled; compare capability and supported arch.
    options=(--rm --network none --cpus=2 --memory=3g --pids-limit=256
      --security-opt=no-new-privileges --user 1000:1000
      --entrypoint /bin/sh --env HOME=/home/winebot
      --env DISPLAY=:97 --env WINEPREFIX=/tmp/winebot-cold-prefix)
    if [ "$caps" = hardened ]; then options+=(--cap-drop=ALL); fi
    if [ "$arch" != default ]; then options+=(--env "WINEARCH=$arch"); fi
    set +e
    docker run "${options[@]}" "$image" -ec '
      Xvfb :97 -screen 0 1280x720x24 -noreset >/dev/null 2>&1 &
      display_ok=0
      i=0
      while [ "$i" -lt 20 ]; do
        if xdpyinfo -display :97 >/dev/null 2>&1; then display_ok=1; break; fi
        i=$((i + 1))
        sleep 0.2
      done
      [ "$display_ok" -eq 1 ] || exit 23
      if timeout -k 5s 90s env WINEDLLOVERRIDES=mscoree,mshtml= wineboot -i >/dev/null 2>&1; then
        code=0
      else
        code=$?
      fi
      if [ "$code" -eq 124 ] || [ "$code" -eq 137 ]; then exit 21; fi
      [ "$code" -eq 0 ] || exit 22
      timeout -k 5s 15s wine cmd /c exit 0 >/dev/null 2>&1 || exit 24
    ' >/dev/null 2>&1
  result=$?
  set -e
  case "$result" in
    0) stage=pass ;;
    21) stage=boot_timeout ;;
    22) stage=boot_nonzero ;;
    23) stage=x11_unready ;;
    24) stage=command_failed ;;
    *) stage=container_failed ;;
  esac
    printf 'WINE_PREFIX_PROBE caps=%s arch=%s stage=%s\n' "$caps" "$arch" "$stage"
    if [ "$caps" = standard ] && [ "$arch" = win64 ] && [ "$result" -eq 0 ]; then
      target_pass=1
    fi
  done
done

# Only the Compose target win64 mode qualifies the actual startup path.
if [ "$target_pass" -ne 1 ]; then
  echo 'WINE_PREFIX_PROBE stage=target_mode_unqualified'
  exit 1
fi
echo 'WINE_PREFIX_PROBE stage=target_preflight_pass'
