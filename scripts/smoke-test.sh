#!/usr/bin/env bash
set -euo pipefail

usage() {
  cat <<'EOF'
Usage: scripts/smoke-test.sh [options]

Run a basic smoke test against the WineBot services.

Options:
  --include-interactive  Also verify VNC/noVNC services.
  --include-debug        Run a winedbg smoke check.
  --phase NAME           Run a specific diagnostic phase (health, smoke, cv, trace, recording).
  --skip-base-checks     Skip base desktop/prefix/screenshot checks (for phased CI runs).
  --full                 Run all internal diagnostic phases.
  --no-build             Skip building the image.
  --cleanup              Stop services started by this script.
  -h, --help             Show this help.
EOF
}

include_interactive="0"
include_debug="0"
phase=""
full="0"
build="1"
cleanup="0"
skip_base_checks="0"

while [ $# -gt 0 ]; do
  case "$1" in
    --include-interactive)
      include_interactive="1"
      ;;
    --include-debug)
      include_debug="1"
      ;;
    --phase)
      phase="$2"
      shift
      ;;
    --skip-base-checks)
      skip_base_checks="1"
      ;;
    --full)
      full="1"
      ;;
    --no-build)
      build="0"
      ;;
    --cleanup)
      cleanup="1"
      ;;
    -h|--help)
      usage
      exit 0
      ;;
    *)
      echo "Unknown option: $1" >&2
      usage
      exit 1
      ;;
  esac
  shift
done

repo_root="$(cd "$(dirname "${BASH_SOURCE[0]}")/.."; pwd)"
compose_file="$repo_root/compose/docker-compose.yml"

if docker compose version >/dev/null 2>&1; then
  compose_cmd=(docker compose)
elif command -v docker-compose >/dev/null 2>&1; then
  compose_cmd=(docker-compose)
else
  echo "Docker Compose not found." >&2
  exit 1
fi

log() {
  printf '%s\n' "$*"
}

fail() {
  echo "ERROR: $*" >&2
  exit 1
}

service_running() {
  local profile="$1"
  local service="$2"
  set +e
  "${compose_cmd[@]}" -f "$compose_file" --profile "$profile" exec -T --user winebot "$service" true >/dev/null 2>&1
  rc=$?
  set -e
  [ "$rc" -eq 0 ]
}

compose_up() {
  local profile="$1"
  local service="$2"
  # Docker Compose v1 sometimes fails with ContainerConfig errors if stale containers exist.
  # Proactively clear any leftovers before starting.
  "${compose_cmd[@]}" -f "$compose_file" down --remove-orphans >/dev/null 2>&1 || true
  local args=("${compose_cmd[@]}" -f "$compose_file" --profile "$profile" up -d)
  if [ "$build" = "1" ]; then
    args+=(--build)
  fi
  args+=("$service")
  "${args[@]}"
}

compose_exec() {
  local profile="$1"
  local service="$2"
  local cmd="$3"
  "${compose_cmd[@]}" -f "$compose_file" --profile "$profile" exec -T --user winebot "$service" bash -lc "$cmd"
}

wait_for_windows() {
  local profile="$1"
  local service="$2"
  local attempts="${WINEBOT_WAIT_FOR_WINDOWS_ATTEMPTS:-360}"
  local delay_s="${WINEBOT_WAIT_FOR_WINDOWS_DELAY_S:-1}"
  local attempt
  for attempt in $(seq 1 "$attempts"); do
    set +e
    windows="$(compose_exec "$profile" "$service" "DISPLAY=:99 wmctrl -l" 2>/dev/null)"
    rc=$?
    set -e
    if [ "$rc" -eq 0 ] && [ -n "${windows:-}" ]; then
      return 0
    fi
    if [ $((attempt % 30)) -eq 0 ]; then
      log "Still waiting for windows on DISPLAY=:99 for $service (attempt ${attempt}/${attempts})..."
    fi
    sleep "$delay_s"
  done
  log "Timed out waiting for windows on DISPLAY=:99 for $service; showing recent service logs."
  "${compose_cmd[@]}" -f "$compose_file" --profile "$profile" logs --tail 200 "$service" || true
  fail "No windows detected on DISPLAY=:99 for $service after ${attempts} attempts"
}

started_headless="0"
started_interactive="0"
debug_proxy_container=""

cleanup_services() {
  if [ -n "$debug_proxy_container" ]; then
    docker rm -f "$debug_proxy_container" >/dev/null 2>&1 || true
    debug_proxy_container=""
  fi
  if [ "$cleanup" = "1" ]; then
    log "Stopping services started by smoke test..."
    if [ "$started_interactive" = "1" ]; then
      "${compose_cmd[@]}" -f "$compose_file" --profile interactive stop winebot-interactive
    fi
    if [ "$started_headless" = "1" ]; then
      "${compose_cmd[@]}" -f "$compose_file" --profile headless stop winebot
    fi
  fi
}

if [ "$cleanup" = "1" ]; then
  trap cleanup_services EXIT
fi

if service_running headless winebot; then
  log "Headless service already running."
else
  log "Starting headless service..."
  compose_up headless winebot
  started_headless="1"
fi

if [ "$skip_base_checks" != "1" ]; then
  log "Waiting for headless desktop..."
  wait_for_windows headless winebot

  log "Checking Xvfb and openbox..."
  compose_exec headless winebot "pgrep -x Xvfb >/dev/null"
  compose_exec headless winebot "pgrep -x openbox >/dev/null"

  log "Validating Openbox menu commands..."
  compose_exec headless winebot "/scripts/openbox-menu-test.sh --run-x11 --run-wine"

  log "Checking window list..."
  window_list="$(compose_exec headless winebot "DISPLAY=:99 wmctrl -l")"
  window_count="$(echo "$window_list" | grep -v "^$" | wc -l)"
  window_count="$(echo "$window_count" | tr -d ' ')"
  log "Found $window_count window(s):"
  log "$window_list"
  if [ "${window_count:-0}" -lt 1 ]; then
    fail "Expected at least one window, found ${window_count:-0}"
  fi

  log "Capturing screenshot..."
  screenshot_path="$(compose_exec headless winebot "./automation/screenshot.sh" | tail -n 1 | tr -d '\r')"
  compose_exec headless winebot "test -s '$screenshot_path'"

  log "Validating prefix persistence..."
  marker="/wineprefix/drive_c/winebot_smoke_$(date +%s).txt"
  compose_exec headless winebot "echo 'winebot smoke' > '$marker'"
  "${compose_cmd[@]}" -f "$compose_file" --profile headless run --rm --user winebot --entrypoint bash winebot -lc "test -f '$marker'"
  compose_exec headless winebot "rm -f '$marker'"

  if [ "$full" = "1" ]; then
    log "Running Notepad automation..."
    notepad_output="/wineprefix/drive_c/users/winebot/Temp/winebot_smoke_test.txt"
    compose_exec headless winebot "pkill -f '[n]otepad.exe' >/dev/null 2>&1 || true"
    compose_exec headless winebot "python3 automation/notepad_create_and_verify.py --text 'WineBot smoke test' --output '$notepad_output' --launch --timeout 120 --save-timeout 60 --retry-interval 2 --delay 100"
  fi
else
  log "Skipping base checks by request (--skip-base-checks)."
fi

if [ "$include_debug" = "1" ]; then
  log "Running winedbg smoke check..."
  winedbg_env=(ENABLE_WINEDBG=1 WINEDBG_MODE=default "WINEDBG_COMMAND=info proc" APP_EXE=cmd.exe "APP_ARGS=/c exit")
  env "${winedbg_env[@]}" "${compose_cmd[@]}" -f "$compose_file" --profile headless run --rm winebot
fi

if [ "$full" = "1" ] || [ -n "$phase" ]; then
  target_phase="${phase:-all}"
  log "Running internal diagnostics (Phase: $target_phase)..."
  if ! compose_exec headless winebot "/scripts/diagnose-master.sh $target_phase"; then
      log "Internal diagnostics failed. Showing container logs:"
      "${compose_cmd[@]}" -f "$compose_file" --profile headless logs winebot
      exit 1
  fi
fi

if [ "$include_interactive" = "1" ]; then
  if service_running interactive winebot-interactive; then
    log "Interactive service already running."
  else
    log "Starting interactive service..."
    compose_up interactive winebot-interactive
    started_interactive="1"
  fi

  log "Waiting for interactive desktop..."
  wait_for_windows interactive winebot-interactive

  log "Checking VNC/noVNC processes..."
  compose_exec interactive winebot-interactive "pgrep -x x11vnc >/dev/null"
  compose_exec interactive winebot-interactive "pgrep -f novnc_proxy >/dev/null || pgrep -f websockify >/dev/null"

  log "Checking VNC/noVNC ports..."
  compose_exec interactive winebot-interactive "python3 - <<'PY'
import socket
for port in (5900, 6080):
    sock = socket.socket()
    sock.settimeout(1)
    try:
        sock.connect(('127.0.0.1', port))
    except OSError as exc:
        raise SystemExit(f'Port {port} not accepting connections: {exc}') from exc
    finally:
        sock.close()
PY"
fi

log "Smoke test complete."
