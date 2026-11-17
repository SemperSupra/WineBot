#!/usr/bin/env bash
# Two-generation, six-volume recovery of a REAL Wine11-generated disposable
# prefix on a source-exact, read-only, nonroot WineBot layered runtime.
# NO real user profiles, snapshots, external devices or artifact uploads.
set -euo pipefail
fail() { printf 'MVP_LAYERED_RESTORE stage=%s\n' "$1" >&2; exit 1; }
[ "${GITHUB_ACTIONS:-}" = true ] &&
  [ "${GITHUB_EVENT_NAME:-}" = pull_request ] || fail unqualified_venue
[[ "${GITHUB_RUN_ID:-}" =~ ^[0-9]+$ ]] &&
  [[ "${GITHUB_RUN_ATTEMPT:-}" =~ ^[0-9]+$ ]] || fail invalid_run
test -f ../wine11-candidate/docker/base.Dockerfile || fail wine11_source_missing
readonly image='debian@sha256:cedb1ef40439206b673ee8b33a46a03a0c9fa90bf3732f54704f99cb061d2c5a'
readonly prefix="ic1-wine11-restore-$GITHUB_RUN_ID-$GITHUB_RUN_ATTEMPT"
roles=(prefix home config userdata artifacts shared)
names=()
export WINEBOT_APP_VOLUME="$prefix-apps"
export WINEBOT_API_TOKEN=synthetic-wine11-restore-token
export WINEBOT_VNC_PASSWORD=synthetic-wine11-restore-password
archive="$prefix-archive"
cleanup() {
  docker compose -f compose/layered.yml down --remove-orphans >/dev/null 2>&1 || true
  for name in "${names[@]}"; do
    docker volume rm "$name" >/dev/null 2>&1 || true
  done
  docker image rm winebot:ic1-restore winebot-base:ic1-restore \
    winebot-apps:ic1-restore >/dev/null 2>&1 || true
}
trap cleanup EXIT

# Create every temporary volume by an unguessable runner-specific name;
# detect name collision and never operate on an existing outside volume.
create_volume() {
  local name="$1"
  docker volume inspect "$name" >/dev/null 2>&1 && fail volume_collision
  docker volume create "$name" >/dev/null 2>&1 || fail volume_create
  names+=("$name")
}
create_volume "$WINEBOT_APP_VOLUME"
create_volume "$archive"
set_state() {
  local generation="$1"
  export WINEBOT_PREFIX_VOLUME="$prefix-$generation-prefix"
  export WINEBOT_HOME_VOLUME="$prefix-$generation-home"
  export WINEBOT_CONFIG_VOLUME="$prefix-$generation-config"
  export WINEBOT_USERDATA_VOLUME="$prefix-$generation-userdata"
  export WINEBOT_ARTIFACT_VOLUME="$prefix-$generation-artifacts"
  export WINEBOT_SHARED_VOLUME="$prefix-$generation-shared"
}
set_state original
for role in "${roles[@]}"; do create_volume "$prefix-original-$role"; done
for role in "${roles[@]}"; do create_volume "$prefix-recovered-$role"; done

# The archive volume is user-writable; recovered volumes are initialized to
# UID1000 only when confirmed empty, never recursive chown of user data.
prepare_empty_volume() {
  docker run --rm --network none --read-only --cap-drop ALL --cap-add CHOWN \
    --security-opt no-new-privileges --memory 128m --pids-limit 32 \
    --entrypoint /bin/sh -v "$1:/work" "$image" -ec '
      test -z "$(find /work -mindepth 1 -maxdepth 1 -print -quit)"
      chown 1000:1000 /work
    ' >/dev/null 2>&1 || fail prepare_empty_volume
}
prepare_empty_volume "$archive"
for role in "${roles[@]}"; do
  prepare_empty_volume "$prefix-recovered-$role"
done

# Original exact pinned Wine11 source. No push/registry publication.
docker build -f ../wine11-candidate/docker/base.Dockerfile --target final \
  -t winebot-base:ic1-restore ../wine11-candidate \
  >"$RUNNER_TEMP/ic1-wine-base.log" 2>&1 || fail base_build
cp ../wine11-candidate/scripts/init/20-setup-wine.sh scripts/init/20-setup-wine.sh
docker build -f docker/Dockerfile --target intent-rel --build-arg BUILD_INTENT=rel \
  --build-arg BASE_IMAGE=winebot-base:ic1-restore \
  -t winebot:ic1-restore . >"$RUNNER_TEMP/ic1-wine-runtime.log" 2>&1 ||
  fail runtime_build
docker build -f docker/app-bundle.Dockerfile \
  -t winebot-apps:ic1-restore . >"$RUNNER_TEMP/ic1-wine-apps.log" 2>&1 ||
  fail app_build
export WINEBOT_RUNTIME_IMAGE="$(docker image inspect -f '{{.Id}}' winebot:ic1-restore)"
export WINEBOT_APP_BUNDLE_IMAGE="$(docker image inspect -f '{{.Id}}' winebot-apps:ic1-restore)"
[[ "$WINEBOT_RUNTIME_IMAGE" =~ ^sha256:[0-9a-f]{64}$ ]] &&
  [[ "$WINEBOT_APP_BUNDLE_IMAGE" =~ ^sha256:[0-9a-f]{64}$ ]] ||
  fail invalid_image_identity

wait_health() {
  local id state
  for i in $(seq 1 100); do
    id="$(docker compose -f compose/layered.yml ps -q winebot-interactive 2>/dev/null || true)"
    if [ -n "$id" ]; then
      state="$(docker inspect -f '{{if .State.Health}}{{.State.Health.Status}}{{end}}' "$id" 2>/dev/null || true)"
      [ "$state" = healthy ] && return 0
    fi
    sleep 2
  done
  return 1
}
docker compose -f compose/layered.yml up -d --no-build winebot-interactive \
  >/dev/null 2>&1 || fail original_start
wait_health || fail original_health
docker compose -f compose/layered.yml exec -T winebot-interactive wine --version \
  2>/dev/null | grep -Eq '^wine-11([.]|$)' || fail wine_version

# Force genuine Wine registry mutation (not a fake user.reg fixture), plus
# additional home/config/userdata files to prove distinct mount restoration.
docker compose -f compose/layered.yml exec -T winebot-interactive /bin/sh -ec '
  wine reg add "HKCU\Software\WineBotIC1Recovery" /v Proof \
    /t REG_SZ /d LayeredReady /f >/dev/null 2>&1
  wine reg query "HKCU\Software\WineBotIC1Recovery" /v Proof \
    >/dev/null 2>&1
  printf "IC1_REAL_LAYERED_WINE_STATE\n" > /userdata/ic1-recovery.txt
  printf "IC1_REAL_LAYERED_HOME\n" > /home/winebot/ic1-recovery.txt
  printf "IC1_REAL_LAYERED_CONFIG\n" > /config/ic1-recovery.txt
  printf "IC1_REAL_LAYERED_EVIDENCE\n" > /artifacts/ic1-recovery.txt
  printf "IC1_REAL_LAYERED_SHARED\n" > /winebot-shared/ic1-recovery.txt
  test -s /wineprefix/user.reg
' >/dev/null 2>&1 || fail source_mutation
echo 'MVP_LAYERED_RESTORE stage=wine11_source_mutated'

# Quiesce Wine before snapshot. Stop only disposable container; all external
# volumes stay alive and the app pack is immutable.
docker compose -f compose/layered.yml exec -T winebot-interactive \
  wineserver -k >/dev/null 2>&1 || fail wineserver_quiesce
docker compose -f compose/layered.yml stop winebot-interactive \
  >/dev/null 2>&1 || fail stop_before_snapshot

for role in "${roles[@]}"; do
  src="$prefix-original-$role"
  docker run --rm --network none --read-only --user 1000:1000 \
    --cap-drop ALL --security-opt no-new-privileges --memory 128m \
    --pids-limit 32 --entrypoint /bin/sh \
    -v "$src:/source:ro" -v "$archive:/archive" "$image" -ec '
      tar -C /source -cf "/archive/$1.tar" .
      cd /archive
      sha256sum "$1.tar" > "$1.sha256"
      sha256sum -c "$1.sha256" >/dev/null
    ' sh "$role" >/dev/null 2>&1 || fail source_archive
done
echo 'MVP_LAYERED_RESTORE stage=quiesced_six_volume_archive'

# Hash verification must reject the corrupted copy while keeping the original
# archive and restored data intact, all inside a container-private volume.
docker run --rm --network none --read-only --user 1000:1000 \
  --cap-drop ALL --security-opt no-new-privileges --memory 128m \
  --pids-limit 32 --entrypoint /bin/sh -v "$archive:/archive" "$image" -ec '
    cd /archive
    cp prefix.tar tamper.tar
    printf tamper >> tamper.tar
    original="$(cut -d " " -f1 prefix.sha256)"
    if printf "%s  tamper.tar\n" "$original" | sha256sum -c - >/dev/null 2>&1; then exit 1; fi
    rm -f tamper.tar
  ' >/dev/null 2>&1 || fail corrupt_archive_accepted
echo 'MVP_LAYERED_RESTORE stage=archive_tamper_rejected'

for role in "${roles[@]}"; do
  dst="$prefix-recovered-$role"
  docker run --rm --network none --read-only --user 1000:1000 \
    --cap-drop ALL --security-opt no-new-privileges --memory 128m \
    --pids-limit 32 --entrypoint /bin/sh \
    -v "$archive:/archive:ro" -v "$dst:/restore" "$image" -ec '
      cd /archive
      sha256sum -c "$1.sha256" >/dev/null
      test -z "$(find /restore -mindepth 1 -maxdepth 1 -print -quit)"
      tar --no-same-owner --no-same-permissions -C /restore -xf "$1.tar"
    ' sh "$role" >/dev/null 2>&1 || fail restore_archive
done
echo 'MVP_LAYERED_RESTORE stage=six_volumes_restored'

# Compose name is unchanged: never down -v, never remove external volumes.
docker compose -f compose/layered.yml down --remove-orphans \
  >/dev/null 2>&1 || fail original_teardown
set_state recovered
docker compose -f compose/layered.yml up -d --no-build winebot-interactive \
  >/dev/null 2>&1 || fail recovered_start
wait_health || fail recovered_health
docker compose -f compose/layered.yml exec -T winebot-interactive /bin/sh -ec '
  test "$(id -u)" -eq 1000
  wine --version | grep -Eq "^wine-11([.]|$)"
  wine reg query "HKCU\Software\WineBotIC1Recovery" /v Proof \
    >/dev/null 2>&1
  grep -qx IC1_REAL_LAYERED_WINE_STATE /userdata/ic1-recovery.txt
  grep -qx IC1_REAL_LAYERED_HOME /home/winebot/ic1-recovery.txt
  grep -qx IC1_REAL_LAYERED_CONFIG /config/ic1-recovery.txt
  grep -qx IC1_REAL_LAYERED_EVIDENCE /artifacts/ic1-recovery.txt
  grep -qx IC1_REAL_LAYERED_SHARED /winebot-shared/ic1-recovery.txt
  test -s /apps/.winebot-app-content-sha256
  test -s /wineprefix/user.reg
' >/dev/null 2>&1 || fail restored_state_not_replayed
echo 'MVP_LAYERED_RESTORE stage=wine11_six_volume_replay_pass'
