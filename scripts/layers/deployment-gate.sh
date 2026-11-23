#!/bin/sh
# Hold a *separate* host-local, cooperative deployment admission until Compose
# stops this container. The lock volume is root-owned and NEVER mounted into
# the Wine guest runtime. It spans state-init's release of runtime-writer flock.
# NOT distributed consensus, per-guest access policy, or a full trust boundary.
set -eu
fail() {
  printf 'DEPLOYMENT_GATE stage=%s\n' "$1" >&2
  exit 73
}
[ "$(id -u)" = 0 ] || fail invalid_identity
command -v flock >/dev/null 2>&1 || fail lock_unavailable
root=/winebot-control
lock="$root/.winebot-deployment-gate.lock"
[ -d "$root" ] && [ ! -L "$root" ] || fail mount_unavailable
# A fresh external Docker volume normally starts as root-owned 0755.
# The controller may reduce permissions as the directory owner; it must
# never adopt user-owned or group-writable control state.
[ "$(stat -c '%u:%g' "$root" 2>/dev/null)" = "0:0" ] ||
  fail control_root_owner_invalid
case "$(stat -c '%a' "$root" 2>/dev/null)" in
  700) ;;
  755) chmod 0700 "$root" >/dev/null 2>&1 || fail control_root_permissions ;;
  *) fail control_root_permissions ;;
esac
[ "$(stat -c '%u:%g:%a' "$root" 2>/dev/null)" = "0:0:700" ] ||
  fail control_root_permissions
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
