#!/usr/bin/env bash
# Synthetic, disposable-only state backup + restore RDTE.
# NOT a production backup system. No user data, logs, image pushes or uploads.
set -euo pipefail
fail() { printf 'LAYER_BACKUP_RDTE stage=%s\n' "$1" >&2; exit 1; }
[ "${GITHUB_ACTIONS:-}" = true ] &&
  [ "${GITHUB_EVENT_NAME:-}" = pull_request ] || fail unqualified_venue
[[ "${GITHUB_RUN_ID:-}" =~ ^[0-9]+$ ]] &&
  [[ "${GITHUB_RUN_ATTEMPT:-}" =~ ^[0-9]+$ ]] || fail invalid_run
command -v docker >/dev/null 2>&1 || fail docker_unavailable
image='debian@sha256:cedb1ef40439206b673ee8b33a46a03a0c9fa90bf3732f54704f99cb061d2c5a'
prefix="winebot-recovery-$GITHUB_RUN_ID-$GITHUB_RUN_ATTEMPT"
backup_dir="$(mktemp -d "${RUNNER_TEMP:-/tmp}/winebot-recovery.XXXXXXXX")"
volumes=()
cleanup() {
  for name in "${volumes[@]}"; do
    docker volume rm "$name" >/dev/null 2>&1 || true
  done
  [ -n "$backup_dir" ] && rm -rf -- "$backup_dir"
}
trap cleanup EXIT
# App packs are separately immutable/versioned; six volumes contain user state.
roles=(prefix home config userdata artifacts shared)
for role in "${roles[@]}"; do
  source_volume="$prefix-$role-src"
  dest_volume="$prefix-$role-dst"
  for name in "$source_volume" "$dest_volume"; do
    if docker volume inspect "$name" >/dev/null 2>&1; then
      fail volume_already_exists
    fi
    docker volume create "$name" >/dev/null 2>&1 || fail volume_create
    volumes+=("$name")
  done
  # No preexisting content may be chowned or overwritten.
  for name in "$source_volume" "$dest_volume"; do
    docker run --rm --network none --read-only --cap-drop ALL --cap-add CHOWN \
      --security-opt no-new-privileges --memory 128m --pids-limit 32 \
      --entrypoint /bin/sh -v "$name:/state" "$image" -ec '
        test -z "$(find /state -mindepth 1 -maxdepth 1 -print -quit)"
        chown 1000:1000 /state
      ' >/dev/null 2>&1 || fail volume_init
  done
  docker run --rm --network none --read-only --user 1000:1000 --cap-drop ALL \
    --security-opt no-new-privileges --memory 128m --pids-limit 32 \
    --entrypoint /bin/sh -v "$source_volume:/state" "$image" -ec '
      mkdir /state/data
      printf "synthetic-volume-replay\n" > /state/data/proof.txt
      printf "synthetic-metadata\n" > /state/config.ini
    ' >/dev/null 2>&1 || fail source_write
  # Archive output never leaves this disposable runner.
  docker run --rm --network none --read-only --user "$(id -u):$(id -g)" \
    --cap-drop ALL --security-opt no-new-privileges --memory 128m \
    --pids-limit 32 --entrypoint /bin/sh \
    -v "$source_volume:/state:ro" -v "$backup_dir:/snapshots" \
    "$image" -ec 'tar -C /state -cf "/snapshots/$1.tar" .' sh "$role" \
    >/dev/null 2>&1 || fail snapshot
  (cd "$backup_dir" && sha256sum "$role.tar" > "$role.sha256") || fail digest_write
  (cd "$backup_dir" && sha256sum -c "$role.sha256" >/dev/null) ||
    fail digest_mismatch
  # Negative integrity control on a separate copy.
  cp "$backup_dir/$role.tar" "$backup_dir/tampered.tar"
  printf 'tamper' >> "$backup_dir/tampered.tar"
  if printf '%s  %s\n' "$(cut -d ' ' -f1 "$backup_dir/$role.sha256")" \
      "$backup_dir/tampered.tar" | sha256sum -c - >/dev/null 2>&1; then
    fail tampered_archive_accepted
  fi
  rm -f -- "$backup_dir/tampered.tar"
  # Restore to a different EMPTY state volume with unprivileged user.
  docker run --rm --network none --read-only --user 1000:1000 \
    --cap-drop ALL --security-opt no-new-privileges --memory 128m \
    --pids-limit 32 --entrypoint /bin/sh \
    -v "$dest_volume:/state" -v "$backup_dir:/snapshots:ro" \
    "$image" -ec '
      test -z "$(find /state -mindepth 1 -maxdepth 1 -print -quit)"
      tar --no-same-owner --no-same-permissions -C /state -xf "/snapshots/$1.tar"
    ' sh "$role" >/dev/null 2>&1 || fail restore
  # A new nonroot disposable process reads exactly restored synthetic state.
  docker run --rm --network none --read-only --user 1000:1000 --cap-drop ALL \
    --security-opt no-new-privileges --memory 128m --pids-limit 32 \
    --entrypoint /bin/sh -v "$dest_volume:/state:ro" "$image" -ec '
      test "$(id -u)" -eq 1000
      test "$(stat -c %u /state)" -eq 1000
      test "$(cat /state/data/proof.txt)" = synthetic-volume-replay
      test "$(cat /state/config.ini)" = synthetic-metadata
    ' >/dev/null 2>&1 || fail restored_replay
done
echo 'LAYER_BACKUP_RDTE stage=synthetic_six_volume_replay_passed'
