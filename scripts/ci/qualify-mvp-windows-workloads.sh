#!/usr/bin/env bash
# Rights-cleared actual Windows app/game, not a synthetic program.
# NOTE: the game gate is a seeded-world GUI smoke, NOT gameplay/save acceptance.
set -euo pipefail
fail() { printf 'MVP_WORKLOAD stage=%s\n' "$1" >&2; exit 1; }
[ "${GITHUB_ACTIONS:-}" = true ] &&
  [ "${GITHUB_EVENT_NAME:-}" = pull_request ] || fail unqualified_venue
[[ "${GITHUB_RUN_ID:-}" =~ ^[0-9]+$ ]] &&
  [[ "${GITHUB_RUN_ATTEMPT:-}" =~ ^[0-9]+$ ]] || fail invalid_runner
test -f ../wine11-candidate/docker/base.Dockerfile || fail wine11_missing
test -f apps/mvp-ic1/npp/notepad++.exe || fail editor_missing
test -n "$(find apps/mvp-ic1/openttd -type f -iname openttd.exe -print -quit)" ||
  fail game_missing
test -z "$(find apps/mvp-ic1 -type l -print -quit)" || fail unexpected_symlink

prefix="mvp-ic1-$GITHUB_RUN_ID-$GITHUB_RUN_ATTEMPT"
export WINEBOT_APP_VOLUME="$prefix-apps"
export WINEBOT_PREFIX_VOLUME="$prefix-prefix"
export WINEBOT_HOME_VOLUME="$prefix-home"
export WINEBOT_CONFIG_VOLUME="$prefix-config"
export WINEBOT_USERDATA_VOLUME="$prefix-userdata"
export WINEBOT_ARTIFACT_VOLUME="$prefix-artifacts"
export WINEBOT_SHARED_VOLUME="$prefix-shared"
export WINEBOT_API_TOKEN=ic1-public-runner-synthetic-token-only
export WINEBOT_VNC_PASSWORD=ic1-public-runner-synthetic-password
volumes=("$WINEBOT_APP_VOLUME" "$WINEBOT_PREFIX_VOLUME" "$WINEBOT_HOME_VOLUME"
  "$WINEBOT_CONFIG_VOLUME" "$WINEBOT_USERDATA_VOLUME" "$WINEBOT_ARTIFACT_VOLUME"
  "$WINEBOT_SHARED_VOLUME")
cleanup() {
  docker compose -f compose/layered.yml down --remove-orphans >/dev/null 2>&1 || true
  for volume in "${volumes[@]}"; do
    docker volume rm "$volume" >/dev/null 2>&1 || true
  done
  docker image rm winebot:ic1 winebot-base:ic1 winebot-apps:ic1 >/dev/null 2>&1 || true
}
trap cleanup EXIT
for volume in "${volumes[@]}"; do
  if docker volume inspect "$volume" >/dev/null 2>&1; then fail volume_name_in_use; fi
  docker volume create "$volume" >/dev/null 2>&1 || fail volume_create
done
docker build -f ../wine11-candidate/docker/base.Dockerfile --target final \
  -t winebot-base:ic1 ../wine11-candidate >"$RUNNER_TEMP/ic1-base-build.log" 2>&1 ||
  fail base_build
cp ../wine11-candidate/scripts/init/20-setup-wine.sh scripts/init/20-setup-wine.sh
docker build -f docker/Dockerfile --target intent-rel \
  --build-arg BASE_IMAGE=winebot-base:ic1 --build-arg BUILD_INTENT=rel \
  -t winebot:ic1 . >"$RUNNER_TEMP/ic1-runtime-build.log" 2>&1 ||
  fail runtime_build
docker build -f docker/app-bundle.Dockerfile -t winebot-apps:ic1 . \
  >"$RUNNER_TEMP/ic1-app-build.log" 2>&1 || fail app_build
export WINEBOT_RUNTIME_IMAGE="$(docker image inspect -f '{{.Id}}' winebot:ic1)"
export WINEBOT_APP_BUNDLE_IMAGE="$(docker image inspect -f '{{.Id}}' winebot-apps:ic1)"
[[ "$WINEBOT_RUNTIME_IMAGE" =~ ^sha256:[0-9a-f]{64}$ ]] &&
  [[ "$WINEBOT_APP_BUNDLE_IMAGE" =~ ^sha256:[0-9a-f]{64}$ ]] ||
  fail image_identity
docker compose -f compose/layered.yml config --quiet >/dev/null 2>&1 ||
  fail compose_invalid
docker compose -f compose/layered.yml up -d --no-build winebot-interactive \
  >"$RUNNER_TEMP/ic1-compose-start.log" 2>&1 || fail startup
wait_health() {
  local cid state
  for _ in $(seq 1 100); do
    cid="$(docker compose -f compose/layered.yml ps -q winebot-interactive 2>/dev/null || true)"
    if [ -n "$cid" ]; then
      state="$(docker inspect -f '{{if .State.Health}}{{.State.Health.Status}}{{end}}' "$cid" 2>/dev/null || true)"
      [ "$state" = healthy ] && return 0
    fi
    sleep 2
  done
  return 1
}
wait_health || fail health_initial
docker compose -f compose/layered.yml exec -T winebot-interactive wine --version \
  2>/dev/null | grep -Eq '^wine-11([.]|$)' || fail wrong_wine_version
echo 'MVP_WORKLOAD stage=wine11_layered_ready'

# Actual editor executable shipped in immutable app store; saved document
# belongs to separately persistent UID1000 user data.
docker compose -f compose/layered.yml exec -T winebot-interactive /bin/bash -euo pipefail -c '
  editor="$(find /apps/mvp-ic1/npp -type f -iname notepad++.exe -print -quit)"
  [ -n "$editor" ] && [ "$(id -u)" -eq 1000 ] ||
    { echo "MVP_WORKLOAD_EDITOR_CAUSE=identity_failure"; exit 10; }
  mkdir -p /userdata/ic1-npp-settings
  printf "ic1-before\n" > /userdata/ic1-editor.txt
  doc="$(winepath -w /userdata/ic1-editor.txt)"
  settings="$(winepath -w /userdata/ic1-npp-settings)"
  # Official Notepad++ -settingsDir isolates configuration from read-only
  # application payload, which is intentionally never made writable.
  nohup wine "$editor" "-settingsDir=$settings" "$doc"     >/tmp/ic1-editor-local.log 2>&1 </dev/null &
  found=""
  for i in $(seq 1 90); do
    found="$(xdotool search --onlyvisible --name "Notepad++" 2>/dev/null | head -1 || true)"
    [[ "$found" =~ ^[0-9]{1,16}$ ]] && break
    sleep 1
  done
  [[ "$found" =~ ^[0-9]{1,16}$ ]] ||
    { echo "MVP_WORKLOAD_EDITOR_CAUSE=window_absent"; exit 11; }
  xdotool windowactivate --sync "$found" >/dev/null 2>&1 ||
    { echo "MVP_WORKLOAD_EDITOR_CAUSE=activation_failed"; exit 12; }
  xdotool key --clearmodifiers ctrl+End
  xdotool type --clearmodifiers --delay 20 "IC1-APP-INPUT-PROOF"
  xdotool key --clearmodifiers ctrl+s
  for i in $(seq 1 25); do
    grep -q IC1-APP-INPUT-PROOF /userdata/ic1-editor.txt && exit 0
    sleep 1
  done
  echo "MVP_WORKLOAD_EDITOR_CAUSE=save_timeout"
  exit 13
' >"$RUNNER_TEMP/ic1-editor-gate.log" 2>&1 || {
  # Never publish the captured program stdout/stderr. Only fixed categories.
  cause="$(grep -Eo 'MVP_WORKLOAD_EDITOR_CAUSE=(identity_failure|window_absent|activation_failed|save_timeout)'     "$RUNNER_TEMP/ic1-editor-gate.log" | tail -1 || true)"
  case "$cause" in
    MVP_WORKLOAD_EDITOR_CAUSE=*) printf '%s\n' "$cause" ;;
    *) echo 'MVP_WORKLOAD_EDITOR_CAUSE=unknown' ;;
  esac
  fail editor_gui_save
}
echo 'MVP_WORKLOAD stage=real_windows_editor_gui_save'

# OpenTTD 15.3 source documents -g new game and -G deterministic
# seed. Its in-game tilde/backquote console offers "save <filename>", and
# -q <game> independently validates that OpenTTD can decode a saved game.
# Keep all files in genuine persistent Wine prefix/home/userdata mounts.
docker compose -f compose/layered.yml exec -T winebot-interactive /bin/bash -euo pipefail -c '
  exe="$(find /apps/mvp-ic1/openttd -type f -iname openttd.exe -print -quit)"
  [ -n "$exe" ] && [ "$(id -u)" -eq 1000 ] || exit 20
  cd "$(dirname "$exe")"
  # The OpenTTD -c option selects an explicit persistent configuration file
  # and keeps savegames out of the immutable application payload. This is a
  # deliberate three-layer data-placement acceptance requirement.
  mkdir -p /userdata/ic1-openttd/save
  config="$(winepath -w /userdata/ic1-openttd/openttd.cfg)"
  nohup wine "$exe" -c "$config" -v win32 -m null -s null -g -G 61731 \
    >/tmp/ic1-game-local.log 2>&1 </dev/null &
  pid=$!
  found=""
  for i in $(seq 1 100); do
    found="$(xdotool search --onlyvisible --name OpenTTD 2>/dev/null | head -1 || true)"
    [[ "$found" =~ ^[0-9]{1,16}$ ]] && break
    kill -0 "$pid" 2>/dev/null || exit 21
    sleep 1
  done
  [[ "$found" =~ ^[0-9]{1,16}$ ]] || exit 22
  xdotool windowactivate --sync "$found" >/dev/null 2>&1 || exit 23
  xdotool key --clearmodifiers Escape
  kill -0 "$pid" 2>/dev/null || exit 24
  # OpenTTD 15.3 MakeNewGameDone() executes the immutable app bundle
  # scripts/game_start.scr after a real seeded world has been generated.
  # GUI keyboard action remains a separate observable interaction gate.
  test -s "$(dirname "$exe")/scripts/game_start.scr" ||
    { echo "MVP_WORKLOAD_GAME_CAUSE=start_script_missing"; exit 25; }
  game_save=""
  for i in $(seq 1 40); do
    game_save="$(find /home/winebot /wineprefix /userdata -type f \
      -iname "ic1_winebot_mvp.sav" -print -quit 2>/dev/null)"
    [ -n "$game_save" ] && break
    sleep 1
  done
  if [ -z "$game_save" ] || [ ! -s "$game_save" ]; then
    # OpenTTD writes openttd.cfg on shutdown; its absence during a running
    # session is not evidence that the save operation failed.
    echo "MVP_WORKLOAD_GAME_CAUSE=save_missing"
    exit 25
  fi
  [ "$(stat -c %s "$game_save")" -gt 1024 ] ||
    { echo "MVP_WORKLOAD_GAME_CAUSE=save_too_small"; exit 26; }
  digest="$(sha256sum "$game_save" | cut -d " " -f1)"
  [[ "$digest" =~ ^[0-9a-f]{64}$ ]] ||
    { echo "MVP_WORKLOAD_GAME_CAUSE=save_digest_invalid"; exit 27; }
  printf "%s\n" "$digest" > /userdata/ic1-game-save-digest
  # OpenTTD 15.3 Win32 ShowInfoI() uses a *modal MessageBox* for the
  # successful -q savegame-information result, unless -d initializes the
  # console first. Ordering matters: -d must precede -q (which exits early).
  # Prove an impossible save is rejected before accepting a real decoded one.
  if timeout 20 wine "$exe" -d 0 -c "$config" \
    -q "$(winepath -w /userdata/ic1-openttd/does-not-exist.sav)" \
    >/tmp/ic1-game-negative-local.log 2>&1; then
    echo "MVP_WORKLOAD_GAME_CAUSE=invalid_save_accepted"
    exit 28
  fi
  if ! timeout 35 wine "$exe" -d 0 -c "$config" \
    -q "$(winepath -w "$game_save")" \
    >/tmp/ic1-game-verify-local.log 2>&1; then
    echo "MVP_WORKLOAD_GAME_CAUSE=save_unreadable"
    exit 29
  fi
' >"$RUNNER_TEMP/ic1-game-gate.log" 2>&1 || {
  # Publish only the fixed failure stage, never the game or Wine logs.
  cause="$(grep -Eo 'MVP_WORKLOAD_GAME_CAUSE=(start_script_missing|save_missing|save_too_small|save_digest_invalid|invalid_save_accepted|save_unreadable)' \
    "$RUNNER_TEMP/ic1-game-gate.log" | tail -1 || true)"
  case "$cause" in
    MVP_WORKLOAD_GAME_CAUSE=*) printf '%s\n' "$cause" ;;
    *) echo 'MVP_WORKLOAD_GAME_CAUSE=launch_or_input_unknown' ;;
  esac
  fail game_save_validation
}
echo 'MVP_WORKLOAD stage=windows_game_save_validated'

# Quiesce the real Wine server after checking the save. Unclean runtime
# termination must not corrupt durable state or leave stale Wine processes.
docker compose -f compose/layered.yml exec -T winebot-interactive wineserver -k \
  >/dev/null 2>&1 || fail wine_quiesce
echo 'MVP_WORKLOAD stage=quiesced_before_recreate'
# Preserve immutable app and external user data across disposable process
# recreation; do not delete or mount a real user prefix.
docker compose -f compose/layered.yml up -d --force-recreate --no-build \
  winebot-interactive >/dev/null 2>&1 || fail recreate
wait_health || fail recreate_health
docker compose -f compose/layered.yml exec -T winebot-interactive /bin/bash -euo pipefail -c '
  grep -q IC1-APP-INPUT-PROOF /userdata/ic1-editor.txt ||
    { echo "MVP_WORKLOAD_REPLAY_CAUSE=editor_data_missing"; exit 40; }
  test -s /apps/.winebot-app-content-sha256 ||
    { echo "MVP_WORKLOAD_REPLAY_CAUSE=app_integrity_missing"; exit 41; }
  test -n "$(find /apps/mvp-ic1/openttd -type f -iname openttd.exe -print -quit)" ||
    { echo "MVP_WORKLOAD_REPLAY_CAUSE=game_executable_missing"; exit 42; }
  test -n "$(find /apps/mvp-ic1/npp -type f -iname notepad++.exe -print -quit)" ||
    { echo "MVP_WORKLOAD_REPLAY_CAUSE=editor_executable_missing"; exit 43; }
  test "$(id -u)" -eq 1000 ||
    { echo "MVP_WORKLOAD_REPLAY_CAUSE=wrong_uid"; exit 44; }
  game_save="$(find /home/winebot /wineprefix /userdata -type f \
    -iname ic1_winebot_mvp.sav -print -quit 2>/dev/null)"
  [ -n "$game_save" ] && [ -s "$game_save" ] ||
    { echo "MVP_WORKLOAD_REPLAY_CAUSE=game_save_missing"; exit 45; }
  digest="$(sha256sum "$game_save" | cut -d " " -f1)"
  [ "$digest" = "$(cat /userdata/ic1-game-save-digest)" ] ||
    { echo "MVP_WORKLOAD_REPLAY_CAUSE=game_save_digest_changed"; exit 46; }
  exe="$(find /apps/mvp-ic1/openttd -type f -iname openttd.exe -print -quit)"
  cd "$(dirname "$exe")"
  config="$(winepath -w /userdata/ic1-openttd/openttd.cfg)"
  save_path="$(winepath -w "$game_save")"
  # Actual OpenTTD Windows decoder acceptance, not a file-only false positive.
  if ! timeout 35 wine "$exe" -d 0 -c "$config" -q "$save_path" \
    >/tmp/ic1-game-reopen-local.log 2>&1; then
    echo "MVP_WORKLOAD_REPLAY_CAUSE=decoder_failed"
    exit 47
  fi
  echo "MVP_WORKLOAD_REPLAY_PASS=decoder"
  nohup wine "$exe" -c "$config" -v win32 -m null -s null -x \
    -g "$save_path" >/tmp/ic1-game-loaded-local.log 2>&1 </dev/null &
  pid=$!
  found=""
  for i in $(seq 1 80); do
    found="$(xdotool search --onlyvisible --name OpenTTD 2>/dev/null | head -1 || true)"
    [[ "$found" =~ ^[0-9]{1,16}$ ]] && break
    kill -0 "$pid" 2>/dev/null ||
      { echo "MVP_WORKLOAD_REPLAY_CAUSE=game_exited"; exit 48; }
    sleep 1
  done
  [[ "$found" =~ ^[0-9]{1,16}$ ]] ||
    { echo "MVP_WORKLOAD_REPLAY_CAUSE=game_window_missing"; exit 49; }
  sleep 2
  kill -0 "$pid" 2>/dev/null ||
    { echo "MVP_WORKLOAD_REPLAY_CAUSE=game_exited_after_window"; exit 50; }
  echo "MVP_WORKLOAD_REPLAY_PASS=window"
' >"$RUNNER_TEMP/ic1-replay-local.log" 2>&1 || {
  # Never print subprocess stdout, saved files, display data or raw Wine logs.
  cause="$(grep -Eo 'MVP_WORKLOAD_REPLAY_CAUSE=(editor_data_missing|app_integrity_missing|game_executable_missing|editor_executable_missing|wrong_uid|game_save_missing|game_save_digest_changed|decoder_failed|game_exited|game_window_missing|game_exited_after_window)' \
    "$RUNNER_TEMP/ic1-replay-local.log" | tail -1 || true)"
  case "$cause" in
    MVP_WORKLOAD_REPLAY_CAUSE=*) printf '%s\n' "$cause" ;;
    *) echo 'MVP_WORKLOAD_REPLAY_CAUSE=unknown' ;;
  esac
  fail workload_state_replay
}
grep -q 'MVP_WORKLOAD_REPLAY_PASS=decoder' "$RUNNER_TEMP/ic1-replay-local.log" ||
  fail replay_decoder_receipt
grep -q 'MVP_WORKLOAD_REPLAY_PASS=window' "$RUNNER_TEMP/ic1-replay-local.log" ||
  fail replay_window_receipt
echo 'MVP_WORKLOAD stage=editor_saved_state_replayed'
echo 'MVP_WORKLOAD stage=game_save_reloaded'
echo 'MVP_WORKLOAD stage=bounded_qualification_pass'
