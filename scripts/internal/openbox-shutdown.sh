#!/usr/bin/env bash
set -euo pipefail

mode="${1:-}"

usage() {
  cat <<'EOF'
Usage: scripts/internal/openbox-shutdown.sh <graceful|power-off>

Runs a confirmed WineBot shutdown request from Openbox menu actions.
EOF
}

case "$mode" in
  graceful|power-off)
    ;;
  *)
    usage >&2
    exit 1
    ;;
esac

api_url="${WINEBOT_API_URL:-${WINEBOT_BASE_URL:-http://localhost:8000}}"
token="${API_TOKEN:-${WINEBOT_API_TOKEN:-}}"
if [ -z "$token" ] && [ -f /winebot-shared/winebot_api_token ]; then
  token="$(tr -d '[:space:]' </winebot-shared/winebot_api_token)"
elif [ -z "$token" ] && [ -f /tmp/winebot_api_token ]; then
  token="$(tr -d '[:space:]' </tmp/winebot_api_token)"
fi

if [ "$mode" = "graceful" ]; then
  label="Graceful Shutdown"
  prompt="Gracefully shut down WineBot now?\n\nThis will stop recording and shut down Wine components cleanly."
  endpoint="${api_url}/lifecycle/shutdown"
else
  label="Power Off (Unsafe)"
  prompt="Power off WineBot immediately?\n\nThis is unsafe and may skip graceful teardown."
  endpoint="${api_url}/lifecycle/shutdown?power_off=true"
fi

confirm_exit=1
if command -v xmessage >/dev/null 2>&1; then
  if xmessage -center -buttons "Cancel:1,Confirm:0" -default "Cancel" "$prompt"; then
    confirm_exit=0
  fi
elif [ -t 0 ]; then
  echo "$label confirmation required."
  read -r -p "Type YES to continue: " answer
  if [ "$answer" = "YES" ]; then
    confirm_exit=0
  fi
fi

if [ "$confirm_exit" -ne 0 ]; then
  exit 0
fi

curl_args=(-fsS -X POST)
if [ -n "$token" ]; then
  curl_args+=(-H "X-API-Key: $token")
fi

curl "${curl_args[@]}" "$endpoint" >/dev/null
