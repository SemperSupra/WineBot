#!/bin/sh
# Hold a *separate* host-local, cooperative deployment admission until Compose
# stops this container. This spans state-init's release of runtime-writer flock.
# NOT distributed consensus, a hostile same-UID defense, or a privilege boundary.
set -eu
fail() {
  printf 'DEPLOYMENT_GATE stage=%s\n' "$1" >&2
  exit 73
}
[ "$(id -u)" = 0 ] || fail invalid_identity
command -v flock >/dev/null 2>&1 || fail lock_unavailable
parent=/state/artifacts
root="$parent/sessions"
lock="$root/.winebot-deployment-gate.lock"
[ -d "$parent" ] && [ ! -L "$parent" ] || fail mount_unavailable
if [ ! -d "$root" ]; then
  [ ! -e "$root" ] && [ ! -L "$root" ] || fail lock_identity_invalid
  mkdir -m 0700 "$root" >/dev/null 2>&1 || fail lock_unavailable
fi
[ -d "$root" ] && [ ! -L "$root" ] || fail lock_identity_invalid
if [ ! -e "$lock" ]; then
  [ ! -L "$lock" ] || fail lock_identity_invalid
  (umask 077; : > "$lock") 2>/dev/null || fail lock_unavailable
fi
[ -f "$lock" ] && [ ! -L "$lock" ] || fail lock_identity_invalid
[ "$(stat -c '%u:%g:%a:%h' "$lock" 2>/dev/null)" = 0:0:600:1 ] ||
  fail lock_identity_invalid
exec 9<>"$lock" || fail lock_unavailable
[ "$(stat -c '%d:%i' "$lock" 2>/dev/null)" = "$(stat -Lc '%d:%i' /proc/self/fd/9)" ] ||
  fail lock_identity_invalid
flock -n -x 9 >/dev/null 2>&1 || fail lock_contended
[ ! -L "$lock" ] &&
  [ "$(stat -c '%d:%i' "$lock")" = "$(stat -Lc '%d:%i' /proc/self/fd/9)" ] ||
  fail lock_identity_invalid
# Probe before claiming healthy; readiness only after the exclusive lease.
: > /run/winebot-deployment-ready || fail readiness_unavailable
echo 'DEPLOYMENT_GATE stage=admitted'
# PID1 retains the same exact OFD across exec; SIGTERM/SIGKILL releases it.
# A separate runtime writer lock remains necessary after gate loss.
exec sleep infinity
