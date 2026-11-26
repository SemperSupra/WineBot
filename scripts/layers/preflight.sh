#!/usr/bin/env bash
# Validate or initialize external volumes; never delete user state.
set -euo pipefail
case "${1:-}" in
  --check|--create|--check-volumes) operation="$1" ;;
  *) echo 'LAYERED_PREFLIGHT stage=invalid_operation' >&2; exit 2 ;;
esac

# --check-volumes is a read-only storage check for callers that separately
# verify local content-addressed images. It is not full deployment admission.
if [ "$operation" != --check-volumes ]; then
for image_var in WINEBOT_RUNTIME_IMAGE WINEBOT_APP_BUNDLE_IMAGE; do
  image="${!image_var:-}"
  if [[ ! "$image" =~ ^[^[:space:]]+@sha256:[0-9a-f]{64}$ ]]; then
    echo 'LAYERED_PREFLIGHT stage=unpinned_image' >&2
    exit 2
  fi
done
fi

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
# Never treat distinct volume NAMES as proof of distinct backing state.
# This conservative v1 profile admits ordinary local volumes only.
# Reject driver options (including bind aliases) and duplicate Docker-
# reported mountpoints before starting any state initializer or runtime.
declare -A seen_mount=()
check_identity() {
  local volume="$1" driver options mountpoint
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
}

# Validate every existing volume before creating any missing state.
missing=()
for variable in "${variables[@]}"; do
  volume="${!variable}"
  if docker volume inspect "$volume" >/dev/null 2>&1; then
    check_identity "$volume"
  else
    missing+=("$volume")
  fi
done
if (("${#missing[@]}" > 0)); then
  if [ "$operation" != --create ]; then
    echo 'LAYERED_PREFLIGHT stage=volume_missing' >&2; exit 1
  fi
  for volume in "${missing[@]}"; do
    docker volume create "$volume" >/dev/null 2>&1 || {
      echo 'LAYERED_PREFLIGHT stage=create_failed' >&2; exit 1
    }
  done
  seen_mount=()
  for variable in "${variables[@]}"; do
    check_identity "${!variable}"
  done
fi
if [ "$operation" = --check-volumes ]; then
  echo 'LAYERED_PREFLIGHT stage=volume_identity_ready'
else
  echo 'LAYERED_PREFLIGHT stage=ready'
fi
