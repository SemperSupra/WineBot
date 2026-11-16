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
