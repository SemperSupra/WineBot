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
# Coordinate with the runtime's exact /artifacts/sessions/.winebot-active-writer.lock.
# This protects concurrent state ownership mutations; it does NOT guarantee
# atomic ownership of a whole deployment across state-init -> runtime.
command -v flock >/dev/null 2>&1 || fail lock_unavailable
control_parent=/state/artifacts
control_root="$control_parent/sessions"
control_file="$control_root/.winebot-active-writer.lock"
[ -d "$control_parent" ] && [ ! -L "$control_parent" ] || fail mount_unavailable
if [ ! -d "$control_root" ]; then
  [ ! -e "$control_root" ] && [ ! -L "$control_root" ] || fail lock_identity_invalid
  mkdir -m 0700 "$control_root" >/dev/null 2>&1 || fail lock_unavailable
fi
[ -d "$control_root" ] && [ ! -L "$control_root" ] || fail lock_identity_invalid
if [ ! -e "$control_file" ]; then
  [ ! -L "$control_file" ] || fail lock_identity_invalid
  (umask 077; : > "$control_file") 2>/dev/null || fail lock_unavailable
fi
[ -f "$control_file" ] && [ ! -L "$control_file" ] || fail lock_identity_invalid
[ "$(stat -c '%h' "$control_file" 2>/dev/null)" = 1 ] || fail lock_identity_invalid
exec 9<>"$control_file" || fail lock_unavailable
[ "$(stat -c '%d:%i' "$control_file")" = "$(stat -Lc '%d:%i' /proc/self/fd/9)" ] ||
  fail lock_identity_invalid
flock -n -x 9 >/dev/null 2>&1 || fail lock_contended
# Revalidate identity while the lock is held; absent / attacker-controlled
# lock swaps are refused rather than treated as a new independent lock.
[ ! -L "$control_file" ] &&
  [ "$(stat -c '%d:%i' "$control_file")" = "$(stat -Lc '%d:%i' /proc/self/fd/9)" ] ||
  fail lock_identity_invalid
case "$(stat -c '%u:%g:%a' "$control_file" 2>/dev/null)" in
  0:0:600)
    chown 1000:1000 "$control_file" >/dev/null 2>&1 || fail ownership_failed
    ;;
  1000:1000:600) ;;
  *) fail lock_identity_invalid ;;
esac
case "$(stat -c '%u:%g' "$control_root" 2>/dev/null)" in
  0:0)
    chmod u+rwx "$control_root" >/dev/null 2>&1 || fail permissions_failed
    chown 1000:1000 "$control_root" >/dev/null 2>&1 || fail ownership_failed
    ;;
  1000:1000) ;;
  *) fail lock_identity_invalid ;;
esac
# FD9 remains open until this process exits; another writer's nonblocking
# kernel flock will reject mutations while this state-init owns the lock.
for dir in /state/prefix /state/home /state/config /state/userdata /state/artifacts /state/shared; do
  [ -d "$dir" ] && [ ! -L "$dir" ] || fail mount_unavailable
  owner="$(stat -c '%u:%g' "$dir" 2>/dev/null)" || fail mount_unavailable
  case "$owner" in
    1000:1000)
      # Idempotent restart: CAP_CHOWN-only root is NOT permitted to chmod a
      # user-owned directory. Verify the owner has rwx; never modify it.
      mode="$(stat -c '%A' "$dir" 2>/dev/null)" || fail mount_unavailable
      case "$mode" in
        drwx*) ;;
        *) fail permissions_failed ;;
      esac
      ;;
    0:0)
      # First deployment only. chmod while root still owns the directory;
      # afterward CAP_CHOWN alone cannot chmod the now-user-owned path.
      chmod u+rwx "$dir" >/dev/null 2>&1 || fail permissions_failed
      chown 1000:1000 "$dir" >/dev/null 2>&1 || fail ownership_failed
      ;;
    *)
      # Existing foreign-owner state is neither ours to migrate nor erase.
      fail unexpected_ownership
      ;;
  esac
done
echo 'STATE_LAYER_DIAGNOSTIC stage=ready'
