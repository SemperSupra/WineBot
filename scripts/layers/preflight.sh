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
  WINEBOT_SHARED_VOLUME
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
echo 'LAYERED_PREFLIGHT stage=ready'
