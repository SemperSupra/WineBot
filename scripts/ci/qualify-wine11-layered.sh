#!/usr/bin/env bash
# Disposable composite HIL for pinned Wine11 R018 source and layer branch.
# This intentionally does not claim that either PR head alone is release-ready.
set -euo pipefail
fail() {
  printf 'WINE11_LAYER_HIL stage=%s\n' "$1" >&2
  exit 1
}
[ "${GITHUB_ACTIONS:-}" = true ] && [ "${GITHUB_EVENT_NAME:-}" = pull_request ] ||
  fail unqualified_venue
[[ "${GITHUB_RUN_ID:-}" =~ ^[0-9]+$ ]] &&
  [[ "${GITHUB_RUN_ATTEMPT:-}" =~ ^[0-9]+$ ]] || fail invalid_runner
[ -f ../wine11-candidate/docker/base.Dockerfile ] &&
  [ -f ../wine11-candidate/scripts/init/20-setup-wine.sh ] ||
  fail source_unavailable

prefix="winebot-hil-${GITHUB_RUN_ID}-${GITHUB_RUN_ATTEMPT}"
export WINEBOT_APP_VOLUME="$prefix-apps"
export WINEBOT_PREFIX_VOLUME="$prefix-prefix"
export WINEBOT_HOME_VOLUME="$prefix-home"
export WINEBOT_CONFIG_VOLUME="$prefix-config"
export WINEBOT_USERDATA_VOLUME="$prefix-userdata"
export WINEBOT_ARTIFACT_VOLUME="$prefix-artifacts"
export WINEBOT_SHARED_VOLUME="$prefix-shared"
export WINEBOT_API_TOKEN=synthetic-hil-local-only-token
export WINEBOT_VNC_PASSWORD=synthetic-hil-local-only-password
volumes=("$WINEBOT_APP_VOLUME" "$WINEBOT_PREFIX_VOLUME" "$WINEBOT_HOME_VOLUME"
  "$WINEBOT_CONFIG_VOLUME" "$WINEBOT_USERDATA_VOLUME" "$WINEBOT_ARTIFACT_VOLUME"
  "$WINEBOT_SHARED_VOLUME")
cleanup() {
  docker compose -f compose/layered.yml down --remove-orphans >/dev/null 2>&1 || true
  for volume in "${volumes[@]}"; do
    docker volume rm "$volume" >/dev/null 2>&1 || true
  done
  docker image rm winebot:layered-hil winebot-base:layered-hil winebot-apps:layered-hil >/dev/null 2>&1 || true
}
trap cleanup EXIT
for volume in "${volumes[@]}"; do
  docker volume create "$volume" >/dev/null 2>&1 || fail create_synthetic_volume
done

# The base and Wine init come exclusively from qualified Wine11 exact SHA.
# This is a declared composite experiment, never source-exact promotion.
docker build --file ../wine11-candidate/docker/base.Dockerfile --target final \
  --tag winebot-base:layered-hil ../wine11-candidate >/dev/null 2>&1 ||
  fail wine11_base_build
cp ../wine11-candidate/scripts/init/20-setup-wine.sh scripts/init/20-setup-wine.sh
docker build --file docker/Dockerfile --target intent-rel \
  --build-arg BASE_IMAGE=winebot-base:layered-hil \
  --build-arg BUILD_INTENT=rel \
  --tag winebot:layered-hil . >/dev/null 2>&1 || fail layered_runtime_build
docker build --file docker/app-bundle.Dockerfile \
  --tag winebot-apps:layered-hil . >/dev/null 2>&1 || fail app_pack_build

# Use immutable local OCI content IDs, not floating tags, in this HIL only.
export WINEBOT_RUNTIME_IMAGE="$(docker image inspect --format '{{.Id}}' winebot:layered-hil)"
export WINEBOT_APP_BUNDLE_IMAGE="$(docker image inspect --format '{{.Id}}' winebot-apps:layered-hil)"
[[ "$WINEBOT_RUNTIME_IMAGE" =~ ^sha256:[0-9a-f]{64}$ ]] &&
  [[ "$WINEBOT_APP_BUNDLE_IMAGE" =~ ^sha256:[0-9a-f]{64}$ ]] ||
  fail image_identity_invalid
docker compose -f compose/layered.yml config --quiet >/dev/null 2>&1 ||
  fail compose_invalid
# Project container state and fixed-domain diagnostics only. Never print raw
# Compose logs, environment variables, container IDs, mounts or user paths.
classify_startup() {
  local service cid state exit_code health
  for service in app-seed state-init winebot-interactive; do
    cid="$(docker compose -f compose/layered.yml ps -a -q "$service" 2>/dev/null || true)"
    if [ -z "$cid" ]; then
      printf 'WINE11_LAYER_HIL service=%s state=absent\n' "$service" >&2
      continue
    fi
    state="$(docker inspect --format '{{.State.Status}}' "$cid" 2>/dev/null || true)"
    exit_code="$(docker inspect --format '{{.State.ExitCode}}' "$cid" 2>/dev/null || true)"
    health="$(docker inspect --format '{{if .State.Health}}{{.State.Health.Status}}{{else}}none{{end}}' "$cid" 2>/dev/null || true)"
    case "$state" in created|running|restarting|exited|dead|paused) ;; *) state=unknown ;; esac
    case "$health" in healthy|unhealthy|starting|none) ;; *) health=unknown ;; esac
    [[ "$exit_code" =~ ^[0-9]{1,3}$ ]] || exit_code=unknown
    printf 'WINE11_LAYER_HIL service=%s state=%s exit=%s health=%s\n' "$service" "$state" "$exit_code" "$health" >&2
    # The scripts emit fixed-domain markers on failure. Process container logs
    # privately; the classifier emits ONLY one enumerated category, not raw text.
    case "$service" in
      app-seed|state-init)
        docker logs --tail 80 "$cid" 2>/dev/null |
          python3 scripts/ci/classify-layer-init-logs.py "$service" >&2 || true
        ;;
    esac
  done
}
if ! docker compose -f compose/layered.yml up --no-build -d winebot-interactive >/dev/null 2>&1; then
  classify_startup
  fail startup
fi

wait_health() {
  local attempt cid status
  for attempt in $(seq 1 90); do
    cid="$(docker compose -f compose/layered.yml ps -q winebot-interactive 2>/dev/null || true)"
    if [ -n "$cid" ]; then
      status="$(docker inspect --format '{{.State.Health.Status}}' "$cid" 2>/dev/null || true)"
      if [ "$status" = healthy ]; then return 0; fi
    fi
    sleep 2
  done
  return 1
}
wait_health || fail health_initial
docker compose -f compose/layered.yml exec -T winebot-interactive wine --version \
  2>/dev/null | grep -Eq '^wine-11([.]|$)' || fail wine11_version

# Verify ownership, persistent user state and immutable application mount.
docker compose -f compose/layered.yml exec -T winebot-interactive /bin/sh -ec '
  [ "$(id -u)" -eq 1000 ] || exit 12
  printf "durable-user\n" > /userdata/hil-proof
  printf "durable-config\n" > /config/hil-proof
  printf "durable-home\n" > /home/winebot/hil-proof
  printf "durable-wineprefix\n" > /wineprefix/hil-proof
  printf "durable-evidence\n" > /artifacts/hil-proof
  test -s /apps/.winebot-app-content-sha256
  if touch /apps/unauthorized-executable.exe >/dev/null 2>&1; then exit 13; fi
  if touch /opt/winebot/unauthorized-root-write >/dev/null 2>&1; then exit 14; fi
' >/dev/null 2>&1 || fail state_write_or_readonly

# Use the actual WineBot bounded trace/resource checker (90-second tier).
docker compose -f compose/layered.yml exec -T --user 1000 \
  -e DURATION_SECONDS=90 -e INTERVAL_SECONDS=15 \
  -e MAX_LOG_MB=1024 -e MAX_SESSION_MB=8192 \
  -e MAX_PID1_RSS_MB=2048 \
  winebot-interactive /scripts/diagnostics/soak-resource-bounds.sh nightly \
  >/dev/null 2>&1 || fail resource_sample

# Destroy/recreate only disposable runtime containers; never remove state.
docker compose -f compose/layered.yml up --no-build --force-recreate -d winebot-interactive \
  >/dev/null 2>&1 || fail runtime_recreate
wait_health || fail health_recreate
docker compose -f compose/layered.yml exec -T winebot-interactive /bin/sh -ec '
  grep -qx durable-user /userdata/hil-proof
  grep -qx durable-config /config/hil-proof
  grep -qx durable-home /home/winebot/hil-proof
  grep -qx durable-wineprefix /wineprefix/hil-proof
  grep -qx durable-evidence /artifacts/hil-proof
  test -s /apps/.winebot-app-content-sha256
' >/dev/null 2>&1 || fail state_replay
echo 'WINE11_LAYER_HIL stage=pass'
