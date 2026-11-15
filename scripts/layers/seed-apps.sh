#!/bin/sh
# One-shot, offline copier from immutable OCI app bundle to a versioned volume.
# Never upgrade or merge into an existing version: fail closed instead.
set -eu
umask 022
source_dir=/opt/winebot/app-payload
volume=/winebot-apps
manifest=/opt/winebot/app-manifest.sha256
stamp="$volume/.winebot-app-content-sha256"

fail() {
  printf 'APP_LAYER_DIAGNOSTIC stage=%s\n' "$1" >&2
  exit 1
}

[ -d "$source_dir" ] && [ -d "$volume" ] && [ -s "$manifest" ] || fail unavailable
[ ! -L "$volume" ] && [ ! -L "$stamp" ] || fail invalid_mount
digest="$(sha256sum "$manifest" | cut -c 1-64)"
case "$digest" in *[!0-9a-f]*|'') fail invalid_manifest;; esac
if [ -f "$stamp" ]; then
  [ "$(cat "$stamp")" = "$digest" ] || fail version_mismatch
  (cd "$volume" && sha256sum -c "$manifest" >/dev/null 2>&1) || fail integrity_mismatch
  echo 'APP_LAYER_DIAGNOSTIC stage=existing_verified'
  exit 0
fi
[ -z "$(find "$volume" -mindepth 1 -maxdepth 1 -print -quit)" ] || fail incomplete_volume
cp -a "$source_dir"/. "$volume"/ >/dev/null 2>&1 || fail copy_failed
(cd "$volume" && sha256sum -c "$manifest" >/dev/null 2>&1) || fail integrity_mismatch
printf '%s\n' "$digest" > "$stamp.tmp" || fail stamp_failed
mv "$stamp.tmp" "$stamp" || fail stamp_failed
echo 'APP_LAYER_DIAGNOSTIC stage=created_verified'
