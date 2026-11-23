#!/usr/bin/env bash
# Validate or initialize external volumes; never delete user state.
set -euo pipefail
case "${1:-}" in
  --check|--create) operation="$1" ;;
  *) echo 'LAYERED_PREFLIGHT stage=invalid_operation' >&2; exit 2 ;;
esac

for image_var in WINEBOT_RUNTIME_IMAGE WINEBOT_APP_BUNDLE_IMAGE; do
  image="${!image_var:-}"
  if [[ ! "$image" =~ ^[^[:space:]]+@sha256:[0-9a-f]{64}$ ]]; then
    echo 'LAYERED_PREFLIGHT stage=unpinned_image' >&2
    exit 2
  fi
done

variables=(
  WINEBOT_APP_VOLUME WINEBOT_PREFIX_VOLUME WINEBOT_HOME_VOLUME
  WINEBOT_CONFIG_VOLUME WINEBOT_USERDATA_VOLUME WINEBOT_ARTIFACT_VOLUME
  WINEBOT_SHARED_VOLUME WINEBOT_CONTROL_VOLUME
)
declare -A seen=()
for variable in "${variables[@]}"; do
  value="${!variable:-}"
  if [[ ! "$value" =~ ^winebot-[a-z0-9][a-z0-9-]{1,70}$ ]] || [[ -n "${seen[$value]:-}" ]]; then
    echo 'LAYERED_PREFLIGHT stage=invalid_volume_namespace' >&2
    exit 2
  fi
  seen[$value]=1
done

if ! command -v docker >/dev/null 2>&1; then
  echo 'LAYERED_PREFLIGHT stage=docker_unavailable' >&2
  exit 2
fi
for variable in "${variables[@]}"; do
  volume="${!variable}"
  if docker volume inspect "$volume" >/dev/null 2>&1; then continue; fi
  if [ "$operation" = --check ]; then
    echo 'LAYERED_PREFLIGHT stage=volume_missing' >&2
    exit 1
  fi
  docker volume create "$volume" >/dev/null 2>&1 || {
    echo 'LAYERED_PREFLIGHT stage=create_failed' >&2
    exit 1
  }
done
# Never treat distinct volume NAMES as proof of distinct backing state.
# This conservative v1 profile admits ordinary local volumes only.
# Reject driver options (including bind aliases) and duplicate Docker-
# reported mountpoints before starting any state initializer or runtime.
declare -A seen_mount=()
for variable in "${variables[@]}"; do
  volume="${!variable}"
  driver="$(docker volume inspect --format '{{.Driver}}' "$volume" 2>/dev/null)" || {
    echo 'LAYERED_PREFLIGHT stage=volume_identity_unavailable' >&2
    exit 2
  }
  options="$(docker volume inspect --format '{{json .Options}}' "$volume" 2>/dev/null)" || {
    echo 'LAYERED_PREFLIGHT stage=volume_identity_unavailable' >&2
    exit 2
  }
  mountpoint="$(docker volume inspect --format '{{.Mountpoint}}' "$volume" 2>/dev/null)" || {
    echo 'LAYERED_PREFLIGHT stage=volume_identity_unavailable' >&2
    exit 2
  }
  if [ "$driver" != local ] ||
     { [ "$options" != null ] && [ "$options" != '{}' ]; } ||
     [[ "$mountpoint" != /* ]] || [ "$mountpoint" = / ] ||
     [[ -n "${seen_mount[$mountpoint]:-}" ]]; then
    echo 'LAYERED_PREFLIGHT stage=volume_alias_or_driver' >&2
    exit 2
  fi
  seen_mount["$mountpoint"]=1
done
echo 'LAYERED_PREFLIGHT stage=ready'
