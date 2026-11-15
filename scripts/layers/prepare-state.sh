#!/bin/sh
# Run once per deployment before a non-root WineBot runtime starts.
# Only adjust top-level volume ownership: never traverse, wipe, or migrate
# user files. This is a disposable, network-off bootstrap process.
set -eu
fail() {
  printf 'STATE_LAYER_DIAGNOSTIC stage=%s\n' "$1" >&2
  exit 1
}
[ "$(id -u)" = 0 ] || fail invalid_identity
for dir in /state/prefix /state/home /state/config /state/userdata /state/artifacts /state/shared; do
  [ -d "$dir" ] && [ ! -L "$dir" ] || fail mount_unavailable
  chown 1000:1000 "$dir" >/dev/null 2>&1 || fail ownership_failed
  chmod u+rwx "$dir" >/dev/null 2>&1 || fail permissions_failed
done
echo 'STATE_LAYER_DIAGNOSTIC stage=ready'
