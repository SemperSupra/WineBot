#!/usr/bin/env bash
set -euo pipefail

usage() {
  cat <<'EOF'
Usage: scripts/run-app.sh <app-exe> [options]

Run a Windows app from either /apps or the Wine prefix.

Options:
  --mode headless|interactive  Run mode (default: headless).
  --direct-cli                 Run via API /apps/run and print stdout (headless only).
  --args "..."                 Arguments for the app (optional).
  --workdir PATH               Working directory inside the container (optional).
  --winarch win32              Use a 32-bit Wine prefix for this run.
  --automation "CMD"           Run an automation command after launch.
  --winedbg                    Launch under winedbg.
  --winedbg-mode gdb|default   Set winedbg mode (default: gdb).
  --winedbg-port PORT          Set gdb proxy port (default: 2345).
  --winedbg-no-start           Do not auto-start gdb (default).
  --winedbg-command "CMD"      Run a winedbg command (default mode only).
  --winedbg-script PATH        Run winedbg commands from a file (default mode only).
  --record                     Enable session recording.
  --view [novnc|vnc|auto]      Auto-open viewer (forces --mode interactive, implies --detach).
  --novnc-url URL              Override dashboard/noVNC URL (default: http://localhost:8000/ui).
  --novnc-password PASS        noVNC password (optional; enables auto-connect without prompts).
  --no-password-url            Do not embed the password in the URL.
  --vnc-host HOST              VNC host (default: localhost).
  --vnc-port PORT              VNC port (default: 5900).
  --vnc-password PASS          VNC password (optional; used for non-interactive VNC viewers).
  --vnc-viewer CMD             Custom VNC viewer command (optional).
  --view-timeout SEC           Viewer wait timeout (default: 30).
  --detach, -d                 Run in the background.
  --no-build                   Skip building the image.
  -h, --help                   Show this help.

App path can be:
  - /apps/MyApp.exe (maps from ./apps on the host)
  - /wineprefix/drive_c/Program Files/MyApp/MyApp.exe
  - C:\\Program Files\\MyApp\\MyApp.exe (quote/escape backslashes)
EOF
}

if [ $# -lt 1 ]; then
  usage
  exit 1
fi

app_exe="$1"
shift

mode="headless"
direct_cli="0"
app_args=""
workdir=""
winearch=""
automation_cmd=""
enable_winedbg="0"
winedbg_mode=""
winedbg_port=""
winedbg_no_start=""
winedbg_command=""
winedbg_script=""
record="0"
build="1"
detach="0"
view_mode=""
novnc_url=""
novnc_password=""
novnc_password_set="0"
no_password_url="0"
vnc_host="${VNC_HOST:-localhost}"
vnc_port="${VNC_PORT:-5900}"
vnc_password=""
vnc_password_set="0"
view_timeout="30"
vnc_viewer=""

while [ $# -gt 0 ]; do
  case "$1" in
    --mode)
      mode="${2:-}"
      shift
      ;;
    --record)
      record="1"
      ;;
    --headless)
      mode="headless"
      ;;
    --interactive)
      mode="interactive"
      ;;
    --args)
      app_args="${2:-}"
      shift
      ;;
    --direct-cli)
      direct_cli="1"
      ;;
    --workdir)
      workdir="${2:-}"
      shift
      ;;
    --winarch)
      winearch="${2:-}"
      shift
      ;;
    --automation)
      automation_cmd="${2:-}"
      shift
      ;;
    --winedbg)
      enable_winedbg="1"
      ;;
    --winedbg-mode)
      enable_winedbg="1"
      winedbg_mode="${2:-}"
      shift
      ;;
    --winedbg-port)
      enable_winedbg="1"
      winedbg_port="${2:-}"
      shift
      ;;
    --winedbg-no-start)
      enable_winedbg="1"
      winedbg_no_start="1"
      ;;
    --winedbg-command)
      enable_winedbg="1"
      winedbg_command="${2:-}"
      shift
      ;;
    --winedbg-script)
      enable_winedbg="1"
      winedbg_script="${2:-}"
      shift
      ;;
    --view)
      if [ -n "${2:-}" ] && [[ ! "${2:-}" =~ ^- ]]; then
        view_mode="${2}"
        shift
      else
        view_mode="auto"
      fi
      ;;
    --novnc-url)
      novnc_url="${2:-}"
      shift
      ;;
    --novnc-password)
      novnc_password="${2-}"
      novnc_password_set="1"
      shift
      ;;
    --no-password-url)
      no_password_url="1"
      ;;
    --vnc-host)
      vnc_host="${2:-}"
      shift
      ;;
    --vnc-port)
      vnc_port="${2:-}"
      shift
      ;;
    --vnc-password)
      vnc_password="${2-}"
      vnc_password_set="1"
      shift
      ;;
    --vnc-viewer)
      vnc_viewer="${2:-}"
      shift
      ;;
    --view-timeout)
      view_timeout="${2:-}"
      shift
      ;;
    --detach|-d)
      detach="1"
      ;;
    --no-build)
      build="0"
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

if [ "$mode" != "headless" ] && [ "$mode" != "interactive" ]; then
  echo "Invalid mode: $mode (expected headless or interactive)" >&2
  exit 1
fi

if [ -n "$view_mode" ]; then
  if [ "$mode" = "headless" ]; then
    mode="interactive"
  fi
  if [ "$detach" != "1" ]; then
    detach="1"
  fi
fi

if [ "$direct_cli" = "1" ] && [ "$mode" != "headless" ]; then
  echo "--direct-cli cannot be combined with interactive/viewer mode." >&2
  exit 1
fi

repo_root="$(cd "$(dirname "${BASH_SOURCE[0]}")/.."; pwd)"

resolve_app_exe() {
  local input="$1"
  local host_path=""
  local container_path=""

  if [[ "$input" == /apps/* ]]; then
    container_path="$input"
    host_path="$repo_root/apps/${input#/apps/}"
  elif [[ "$input" == "$repo_root/apps/"* ]]; then
    host_path="$input"
    container_path="/apps/${input#$repo_root/apps/}"
  elif [[ "$input" == ./apps/* ]]; then
    host_path="$repo_root/${input#./}"
    container_path="/${input#./}"
  elif [[ "$input" == apps/* ]]; then
    host_path="$repo_root/$input"
    container_path="/$input"
  elif [[ -f "$repo_root/apps/$input" ]]; then
    host_path="$repo_root/apps/$input"
    container_path="/apps/$input"
  else
    container_path="$input"
  fi

  if [ -n "$host_path" ] && [ ! -f "$host_path" ]; then
    echo "App executable not found: $host_path" >&2
    exit 1
  fi

  printf '%s\n' "$container_path"
}

container_app_exe="$(resolve_app_exe "$app_exe")"

if docker compose version >/dev/null 2>&1; then
  compose_cmd=(docker compose)
elif command -v docker-compose >/dev/null 2>&1; then
  compose_cmd=(docker-compose)
else
  echo "Docker Compose not found." >&2
  exit 1
fi

compose_file="$repo_root/compose/docker-compose.yml"

if [ "$mode" = "interactive" ]; then
  profile="interactive"
  service="winebot-interactive"
else
  profile="headless"
  service="winebot"
fi

env_vars=()
if [ "$direct_cli" != "1" ]; then
  env_vars+=(APP_EXE="$container_app_exe")
  if [ -n "$app_args" ]; then
    env_vars+=(APP_ARGS="$app_args")
  fi
else
  env_vars+=(WINEBOT_SUPERVISE_EXPLORER="0")
fi
if [ -n "$workdir" ]; then
  env_vars+=(WORKDIR="$workdir")
fi
if [ -n "$winearch" ]; then
  env_vars+=(WINEARCH="$winearch")
fi
if [ -n "$automation_cmd" ]; then
  env_vars+=(RUN_AUTOMATION="1" AUTOMATION_CMD="$automation_cmd")
fi
if [ "$enable_winedbg" = "1" ]; then
  env_vars+=(ENABLE_WINEDBG="1")
fi
if [ -n "$winedbg_mode" ]; then
  env_vars+=(WINEDBG_MODE="$winedbg_mode")
fi
if [ -n "$winedbg_port" ]; then
  env_vars+=(WINEDBG_PORT="$winedbg_port")
fi
if [ -n "$winedbg_no_start" ]; then
  env_vars+=(WINEDBG_NO_START="$winedbg_no_start")
fi
if [ -n "$winedbg_command" ]; then
  env_vars+=(WINEDBG_COMMAND="$winedbg_command")
fi
if [ -n "$winedbg_script" ]; then
  env_vars+=(WINEDBG_SCRIPT="$winedbg_script")
fi
if [ "$record" = "1" ]; then
  env_vars+=(WINEBOT_RECORD="1")
fi

compose_args=("${compose_cmd[@]}" -f "$compose_file" --profile "$profile" up --force-recreate)
if [ "$build" = "1" ]; then
  compose_args+=(--build)
fi
if [ "$detach" = "1" ]; then
  compose_args+=(-d)
fi
compose_args+=("$service")

direct_cli_cleanup="0"
if [ "$direct_cli" = "1" ]; then
  if [ "$detach" != "1" ]; then
    direct_cli_cleanup="1"
  fi
  detach="1"
  compose_args=("${compose_cmd[@]}" -f "$compose_file" --profile "$profile" up --force-recreate -d)
  if [ "$build" = "1" ]; then
    compose_args+=(--build)
  fi
  compose_args+=("$service")
fi

env "${env_vars[@]}" "${compose_args[@]}"

if [ "$direct_cli" = "1" ]; then
  cleanup_direct_cli() {
    if [ "$direct_cli_cleanup" = "1" ]; then
      "${compose_cmd[@]}" -f "$compose_file" --profile "$profile" down --remove-orphans >/dev/null 2>&1 || true
    fi
  }
  trap cleanup_direct_cli EXIT

  for i in $(seq 1 90); do
    if [ -n "${API_TOKEN:-}" ]; then
      if curl -fsS -H "X-API-Key: ${API_TOKEN}" http://localhost:8000/health >/dev/null 2>&1; then
        break
      fi
    elif curl -fsS http://localhost:8000/health >/dev/null 2>&1; then
      break
    fi
    if [ "$i" -eq 90 ]; then
      echo "Timed out waiting for API readiness in direct CLI mode." >&2
      "${compose_cmd[@]}" -f "$compose_file" --profile "$profile" logs --tail 200 "$service" >&2 || true
      exit 1
    fi
    sleep 1
  done

  run_args=(apps run "$container_app_exe")
  if [ -n "$app_args" ]; then
    run_args+=(--args "$app_args")
  fi

  run_output="$("$repo_root/scripts/winebotctl" "${run_args[@]}")"
  if parsed_stdout="$(printf '%s' "$run_output" | python3 -c 'import json,sys; d=json.load(sys.stdin); print(d.get("stdout", ""), end="")' 2>/dev/null)"; then
    printf '%s' "$parsed_stdout"
    exit 0
  fi
  printf '%s\n' "$run_output"
  exit 0
fi

if [ -n "$view_mode" ]; then
  novnc_host="${NOVNC_HOST:-localhost}"
  if [ -z "$novnc_url" ]; then
    novnc_url="http://${novnc_host}:8000/ui"
  fi
  if [ "$novnc_password_set" != "1" ]; then
    if [ -n "${NOVNC_PASSWORD:-}" ]; then
      novnc_password="${NOVNC_PASSWORD}"
    elif [ -n "${VNC_PASSWORD:-}" ]; then
      novnc_password="${VNC_PASSWORD}"
    else
      novnc_password="winebot"
    fi
  fi
  if [ "$vnc_password_set" != "1" ]; then
    if [ -n "${VNC_PASSWORD:-}" ]; then
      vnc_password="${VNC_PASSWORD}"
    elif [ -n "${NOVNC_PASSWORD:-}" ]; then
      vnc_password="${NOVNC_PASSWORD}"
    else
      vnc_password="winebot"
    fi
  fi
  view_args=(--mode "$view_mode" --novnc-url "$novnc_url" --vnc-host "$vnc_host" --vnc-port "$vnc_port" --timeout "$view_timeout")
  if [ -n "$novnc_password" ]; then
    view_args+=(--novnc-password "$novnc_password")
  fi
  if [ "$no_password_url" = "1" ]; then
    view_args+=(--no-password-url)
  fi
  if [ -n "$vnc_password" ]; then
    view_args+=(--vnc-password "$vnc_password")
  fi
  if [ -n "$vnc_viewer" ]; then
    view_args+=(--viewer "$vnc_viewer")
  fi
  "$repo_root/scripts/auto-view.sh" "${view_args[@]}" || true
fi
