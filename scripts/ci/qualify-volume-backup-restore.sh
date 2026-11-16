#!/usr/bin/env bash
# Synthetic, disposable-only state backup + restore RDTE.
# NOT a production backup system. No user data, logs, image pushes or uploads.
set -euo pipefail
fail() { printf 'LAYER_BACKUP_RDTE stage=%s\n' "$1" >&2; exit 1; }
[ "${GITHUB_ACTIONS:-}" = true ] || fail unqualified_venue
case "${GITHUB_EVENT_NAME:-}" in
  pull_request) ;;
  push)
    # Exact temporary public RDTE child branch only; never generalize to
    # default-branch pushes or deployment hosts.
    [ "${GITHUB_REF:-}" = refs/heads/rdte/volume-restore-guard-fix-20261116 ] ||
      fail unqualified_venue
    ;;
  *) fail unqualified_venue ;;
esac
[[ "${GITHUB_RUN_ID:-}" =~ ^[0-9]+$ ]] &&
  [[ "${GITHUB_RUN_ATTEMPT:-}" =~ ^[0-9]+$ ]] || fail invalid_run
command -v docker >/dev/null 2>&1 || fail docker_unavailable
image='debian@sha256:cedb1ef40439206b673ee8b33a46a03a0c9fa90bf3732f54704f99cb061d2c5a'
prefix="winebot-recovery-$GITHUB_RUN_ID-$GITHUB_RUN_ATTEMPT"
backup_volume="$prefix-snapshots"
if docker volume inspect "$backup_volume" >/dev/null 2>&1; then
  fail volume_already_exists
fi
docker volume create "$backup_volume" >/dev/null 2>&1 || fail volume_create
volumes=("$backup_volume")
cleanup() {
  for name in "${volumes[@]}"; do
    docker volume rm "$name" >/dev/null 2>&1 || true
  done
}
trap cleanup EXIT
# An isolated synthetic archive volume is initialized once; no host paths,
# temporary directories, or real user state cross this container boundary.
docker run --rm --network none --read-only --cap-drop ALL --cap-add CHOWN \
  --security-opt no-new-privileges --memory 128m --pids-limit 32 \
  --entrypoint /bin/sh -v "$backup_volume:/snapshots" "$image" -ec '
    test -z "$(find /snapshots -mindepth 1 -maxdepth 1 -print -quit)"
    chown 1000:1000 /snapshots
  ' >/dev/null 2>&1 || fail backup_volume_init
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
  docker run --rm --network none --read-only --user 1000:1000 \
    --cap-drop ALL --security-opt no-new-privileges --memory 128m \
    --pids-limit 32 --entrypoint /bin/sh \
    -v "$source_volume:/state:ro" -v "$backup_volume:/snapshots" \
    "$image" -ec 'tar -C /state -cf "/snapshots/$1.tar" .' sh "$role" \
    >/dev/null 2>&1 || fail snapshot
  # Archive integrity and tamper-negative tests run only in a fresh, nonroot
  # short-lived container against the disposable backup volume.
  docker run --rm --network none --read-only --user 1000:1000 \
    --cap-drop ALL --security-opt no-new-privileges --memory 128m \
    --pids-limit 32 --entrypoint /bin/sh \
    -v "$backup_volume:/snapshots" "$image" -ec '
      cd /snapshots
      sha256sum "$1.tar" > "$1.sha256"
      sha256sum -c "$1.sha256" >/dev/null
      cp "$1.tar" tampered.tar
      printf tamper >> tampered.tar
      expected="$(cut -d " " -f1 "$1.sha256")"
      if printf "%s  tampered.tar\n" "$expected" | sha256sum -c - >/dev/null 2>&1; then
        exit 41
      fi
      rm -f tampered.tar
    ' sh "$role" >/dev/null 2>&1 || fail archive_integrity_negative
  # Restore to a different EMPTY state volume with unprivileged user.
  docker run --rm --network none --read-only --user 1000:1000 \
    --cap-drop ALL --security-opt no-new-privileges --memory 128m \
    --pids-limit 32 --entrypoint /bin/sh \
    -v "$dest_volume:/state" -v "$backup_volume:/snapshots:ro" \
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
