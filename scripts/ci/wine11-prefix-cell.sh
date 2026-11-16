#!/bin/sh
# Image-local, offline, bounded prefix cell: mimic entrypoint root setup.
set -eu
profile=${1:-invalid}
case "$profile:$WINEPREFIX" in
  target:/wineprefix|relaxed_pid:/wineprefix|alternate_prefix:/tmp/winebot-cold-prefix|prewarmed_control:/opt/winebot/prefix-template) ;;
  *) exit 31 ;;
esac
if [ "$(id -u)" -eq 0 ]; then
  case "$profile" in target|relaxed_pid) ;; *) exit 31 ;; esac
  # Real entrypoint's 00-setup-user.sh chowns the root-created prefix before
  # dropping privileges. The earlier nonroot direct probe omitted this step.
  chown winebot:winebot "$WINEPREFIX" >/dev/null 2>&1 || exit 30
  exec gosu winebot /bin/sh "$0" "$profile"
fi
[ "$(id -u)" -eq 1000 ] || exit 31
Xvfb :97 -screen 0 1280x720x24 -noreset >/dev/null 2>&1 &
ready=0
i=0
while [ "$i" -lt 40 ]; do
  if xdpyinfo -display :97 >/dev/null 2>&1; then ready=1; break; fi
  i=$((i + 1))
  sleep 0.2
done
[ "$ready" -eq 1 ] || exit 23
if [ "$profile" = prewarmed_control ]; then
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
