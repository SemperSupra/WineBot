#!/usr/bin/env bash
# Public-runner-only $0 RDTE. Creates/deletes ONLY synthetic test volumes.
# No real user data, installer, credential, screenshot, raw stdout or image push.
set -euo pipefail
fail() {
  printf 'LAYER_RDTE stage=%s\n' "$1" >&2
  exit 1
}
[ "${GITHUB_ACTIONS:-}" = true ] && [ "${GITHUB_EVENT_NAME:-}" = pull_request ] ||
  fail unqualified_venue
[[ "${GITHUB_RUN_ID:-}" =~ ^[0-9]+$ ]] &&
  [[ "${GITHUB_RUN_ATTEMPT:-}" =~ ^[0-9]+$ ]] || fail invalid_identity
prefix="winebot-ci-${GITHUB_RUN_ID}-${GITHUB_RUN_ATTEMPT}"
volumes=()
cleanup() {
  for v in "${volumes[@]}"; do
    docker volume rm "$v" >/dev/null 2>&1 || true
  done
  docker image rm winebot-apps:fixture-v1 winebot-apps:fixture-v2 >/dev/null 2>&1 || true
}
trap cleanup EXIT
export WINEBOT_RUNTIME_IMAGE="debian@sha256:cedb1ef40439206b673ee8b33a46a03a0c9fa90bf3732f54704f99cb061d2c5a"
export WINEBOT_APP_BUNDLE_IMAGE="$WINEBOT_RUNTIME_IMAGE"
export WINEBOT_APP_VOLUME="$prefix-apps-v1"
export WINEBOT_PREFIX_VOLUME="$prefix-prefix"
export WINEBOT_HOME_VOLUME="$prefix-home"
export WINEBOT_CONFIG_VOLUME="$prefix-config"
export WINEBOT_USERDATA_VOLUME="$prefix-userdata"
export WINEBOT_ARTIFACT_VOLUME="$prefix-artifacts"
export WINEBOT_SHARED_VOLUME="$prefix-shared"
export WINEBOT_API_TOKEN=synthetic-ci-only-token
export WINEBOT_VNC_PASSWORD=synthetic-ci-only-password

# Dry-run should fail with missing external volumes, never create state.
if bash scripts/layers/preflight.sh --check >/dev/null 2>&1; then fail missing_volume_not_rejected; fi
bash scripts/layers/preflight.sh --create >/dev/null 2>&1 || fail preflight_create
bash scripts/layers/preflight.sh --check >/dev/null 2>&1 || fail preflight_check
volumes=("$WINEBOT_APP_VOLUME" "$WINEBOT_PREFIX_VOLUME" "$WINEBOT_HOME_VOLUME"
  "$WINEBOT_CONFIG_VOLUME" "$WINEBOT_USERDATA_VOLUME" "$WINEBOT_ARTIFACT_VOLUME"
  "$WINEBOT_SHARED_VOLUME")
# A distinct named volume with local bind options is not admissible custody.
# The negative is only inspected, never mounted, on the public disposable VM.
alias_volume="$prefix-option-negative"
if docker volume inspect "$alias_volume" >/dev/null 2>&1; then fail volume_name_in_use; fi
alias_source="$(mktemp -d)"
docker volume create --driver local --opt type=none --opt o=bind \
  --opt "device=$alias_source" "$alias_volume" >/dev/null 2>&1 || fail alias_fixture_create
volumes+=("$alias_volume")
rmdir "$alias_source"
if result="$(WINEBOT_SHARED_VOLUME="$alias_volume" bash scripts/layers/preflight.sh --check 2>&1)"; then
  fail alias_fixture_admitted
fi
[[ "$result" = "LAYERED_PREFLIGHT stage=volume_alias_or_driver" ]] || fail alias_fixture_wrong_diagnostic
echo 'LAYER_RDTE stage=real_local_option_refused'
docker compose -f compose/layered.yml config --quiet >/dev/null 2>&1 || fail compose_invalid

mkdir -p apps/ci-fixture
printf 'app-fixture-v1\n' > apps/ci-fixture/version.txt
docker build -f docker/app-bundle.Dockerfile -t winebot-apps:fixture-v1 . >/dev/null 2>&1 ||
  fail app_build_v1
app_image=winebot-apps:fixture-v1
# Seed only the dedicated applications volume; never mount personal state here.
docker run --rm --network none --read-only --cap-drop ALL \
  --security-opt no-new-privileges --memory 256m --pids-limit 64 \
  -v "$WINEBOT_APP_VOLUME:/winebot-apps" "$app_image" >/dev/null 2>&1 ||
  fail app_seed_v1
docker run --rm --network none --read-only --cap-drop ALL \
  --security-opt no-new-privileges --memory 256m --pids-limit 64 \
  -v "$WINEBOT_APP_VOLUME:/winebot-apps" "$app_image" >/dev/null 2>&1 ||
  fail app_seed_idempotency

# Fail closed on an unauthorized extra executable or symlink in an app volume.
docker run --rm --network none --read-only --cap-drop ALL \
  --security-opt no-new-privileges --entrypoint /bin/sh \
  -v "$WINEBOT_APP_VOLUME:/winebot-apps" "$app_image" -ec '
    printf "UNTRUSTED" >/winebot-apps/unexpected.exe
  ' >/dev/null 2>&1 || fail tamper_fixture
if docker run --rm --network none --read-only --cap-drop ALL \
  --security-opt no-new-privileges -v "$WINEBOT_APP_VOLUME:/winebot-apps" \
  "$app_image" >/dev/null 2>&1; then
  fail tamper_not_rejected
fi
docker run --rm --network none --read-only --cap-drop ALL \
  --security-opt no-new-privileges --entrypoint /bin/sh \
  -v "$WINEBOT_APP_VOLUME:/winebot-apps" "$app_image" -ec '
    rm /winebot-apps/unexpected.exe
  ' >/dev/null 2>&1 || fail tamper_cleanup
docker run --rm --network none --read-only --cap-drop ALL \
  --security-opt no-new-privileges -v "$WINEBOT_APP_VOLUME:/winebot-apps" \
  "$app_image" >/dev/null 2>&1 || fail reverified_app

# One-shot root task prepares only volume root ownership, never user contents.
docker run --rm --network none --read-only --cap-drop ALL --cap-add CHOWN \
  --security-opt no-new-privileges --memory 256m --pids-limit 64 \
  --entrypoint /bin/sh \
  -v "$WINEBOT_PREFIX_VOLUME:/state/prefix" \
  -v "$WINEBOT_HOME_VOLUME:/state/home" \
  -v "$WINEBOT_CONFIG_VOLUME:/state/config" \
  -v "$WINEBOT_USERDATA_VOLUME:/state/userdata" \
  -v "$WINEBOT_ARTIFACT_VOLUME:/state/artifacts" \
  -v "$WINEBOT_SHARED_VOLUME:/state/shared" \
  "$app_image" /usr/local/bin/winebot-prepare-state >/dev/null 2>&1 ||
  fail state_preparation

# Test two fully disposable nonroot containers against the same external state.
docker run --rm --network none --read-only --user 1000:1000 --cap-drop ALL \
  --security-opt no-new-privileges --memory 256m --pids-limit 64 \
  --tmpfs /tmp:rw,nosuid,nodev,mode=1777 \
  --entrypoint /bin/sh \
  -v "$WINEBOT_APP_VOLUME:/apps:ro" -v "$WINEBOT_USERDATA_VOLUME:/userdata" \
  -v "$WINEBOT_CONFIG_VOLUME:/config" \
  "$app_image" -ec '
    grep -qx app-fixture-v1 /apps/ci-fixture/version.txt
    printf "durable-user-file\n" >/userdata/proof.txt
    printf "durable-setting\n" >/config/proof.txt
    printf "ephemeral\n" >/tmp/not-retained
    if touch /apps/ci-fixture/new.txt >/dev/null 2>&1; then exit 9; fi
    if touch /opt/winebot/should-not-write >/dev/null 2>&1; then exit 10; fi
  ' >/dev/null 2>&1 || fail first_runtime

# Replay the exact privileged bootstrap against *already user-owned* volumes
# with preserved files. CAP_CHOWN-only root must not try chmod on UID1000.
docker run --rm --network none --read-only --cap-drop ALL --cap-add CHOWN \
  --security-opt no-new-privileges --memory 256m --pids-limit 64 \
  --entrypoint /bin/sh \
  -v "$WINEBOT_PREFIX_VOLUME:/state/prefix" \
  -v "$WINEBOT_HOME_VOLUME:/state/home" \
  -v "$WINEBOT_CONFIG_VOLUME:/state/config" \
  -v "$WINEBOT_USERDATA_VOLUME:/state/userdata" \
  -v "$WINEBOT_ARTIFACT_VOLUME:/state/artifacts" \
  -v "$WINEBOT_SHARED_VOLUME:/state/shared" \
  "$app_image" /usr/local/bin/winebot-prepare-state >/dev/null 2>&1 ||
  fail state_preparation_idempotency

docker run --rm --network none --read-only --user 1000:1000 --cap-drop ALL \
  --security-opt no-new-privileges --memory 256m --pids-limit 64 \
  --tmpfs /tmp:rw,nosuid,nodev,mode=1777 \
  --entrypoint /bin/sh \
  -v "$WINEBOT_APP_VOLUME:/apps:ro" -v "$WINEBOT_USERDATA_VOLUME:/userdata" \
  -v "$WINEBOT_CONFIG_VOLUME:/config" \
  "$app_image" -ec '
    grep -qx app-fixture-v1 /apps/ci-fixture/version.txt
    grep -qx durable-user-file /userdata/proof.txt
    grep -qx durable-setting /config/proof.txt
    test ! -e /tmp/not-retained
  ' >/dev/null 2>&1 || fail state_replay

# A different app pack must refuse the old versioned volume without mutation.
printf 'app-fixture-v2\n' > apps/ci-fixture/version.txt
docker build -f docker/app-bundle.Dockerfile -t winebot-apps:fixture-v2 . >/dev/null 2>&1 ||
  fail app_build_v2
if docker run --rm --network none --read-only --cap-drop ALL \
  --security-opt no-new-privileges -v "$WINEBOT_APP_VOLUME:/winebot-apps" \
  winebot-apps:fixture-v2 >/dev/null 2>&1; then
  fail version_mismatch_not_rejected
fi
docker volume create "$prefix-apps-v2" >/dev/null 2>&1 || fail second_volume
volumes+=("$prefix-apps-v2")
docker run --rm --network none --read-only --cap-drop ALL \
  --security-opt no-new-privileges -v "$prefix-apps-v2:/winebot-apps" \
  winebot-apps:fixture-v2 >/dev/null 2>&1 || fail app_seed_v2
docker run --rm --network none --read-only --user 1000:1000 --cap-drop ALL \
  --security-opt no-new-privileges --entrypoint /bin/sh \
  -v "$prefix-apps-v2:/apps:ro" -v "$WINEBOT_USERDATA_VOLUME:/userdata" \
  -v "$WINEBOT_CONFIG_VOLUME:/config" \
  winebot-apps:fixture-v2 -ec '
    grep -qx app-fixture-v2 /apps/ci-fixture/version.txt
    grep -qx durable-user-file /userdata/proof.txt
    grep -qx durable-setting /config/proof.txt
  ' >/dev/null 2>&1 || fail app_upgrade_replay
echo 'LAYER_RDTE stage=pass'
