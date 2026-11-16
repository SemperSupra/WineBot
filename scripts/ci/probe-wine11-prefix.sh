#!/usr/bin/env bash
# Four bounded, offline Wine 11 discriminators; fixed-category output only.
# Production-equivalent ownership is prepared before dropping user identity.
set -euo pipefail
image="winebot:local-rel"
target_pass=0
for profile in target alternate_prefix prewarmed_control relaxed_pid; do
  pid_limit=256
  prefix=/wineprefix
  if [ "$profile" = alternate_prefix ]; then prefix=/tmp/winebot-cold-prefix; fi
  if [ "$profile" = prewarmed_control ]; then prefix=/opt/winebot/prefix-template; fi
  if [ "$profile" = relaxed_pid ]; then pid_limit=1024; fi
  identity=1000:1000
  if [ "$profile" = target ] || [ "$profile" = relaxed_pid ]; then identity=0:0; fi

  # No network, uploaded logs, host paths, runtime privilege retention or
  # external workloads. The entrypoint's root-to-winebot ownership step is
  # replicated by the shipped helper in an ephemeral container.
  options=(--rm --network none --cpus=2 --memory=3g
    --pids-limit="$pid_limit" --security-opt=no-new-privileges
    --user "$identity" --entrypoint /bin/sh
    --env HOME=/home/winebot --env DISPLAY=:97
    --env WINEARCH=win64 --env "WINEPREFIX=$prefix")
  set +e
  docker run "${options[@]}" "$image" /scripts/ci/wine11-prefix-cell.sh "$profile" >/dev/null 2>&1
  result=$?
  set -e
  case "$result" in
    0) stage=pass ;;
    21) stage=boot_timeout ;;
    22) stage=boot_nonzero_registry_missing ;;
    23) stage=x11_unready ;;
    24) stage=command_failed ;;
    25) stage=prefix_unwritable ;;
    26) stage=boot_nonzero_registry_command_pass ;;
    27) stage=boot_nonzero_registry_command_fail ;;
    28) stage=registry_missing ;;
    29) stage=server_wait_failed ;;
    30) stage=ownership_prepare_failed ;;
    31) stage=identity_mismatch ;;
    *) stage=container_failed ;;
  esac
  printf 'WINE_PREFIX_PROBE profile=%s stage=%s\n' "$profile" "$stage"
  if [ "$profile" = target ] && [ "$result" -eq 0 ]; then target_pass=1; fi
done
if [ "$target_pass" -ne 1 ]; then
  echo 'WINE_PREFIX_PROBE stage=target_mode_unqualified'
  exit 1
fi
echo 'WINE_PREFIX_PROBE stage=target_preflight_pass'
