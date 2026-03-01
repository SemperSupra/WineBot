#!/usr/bin/env bash
set -euo pipefail

if [ "${WINEBOT_SUPPRESS_DEPRECATION:-0}" != "1" ]; then
  echo "DEPRECATED: scripts/health-check.sh is deprecated. Use scripts/winebotctl health or /health endpoints instead." >&2
fi

usage() {
  cat <<'EOF'
Usage: scripts/health-check.sh [options]

Options:
  --host URL        Base URL (default: http://localhost:8000)
  --token TOKEN     API token (defaults to API_TOKEN env var if set)
  --all             Check all /health subendpoints
  --timeout SEC     Curl timeout in seconds (default: 20)
  -h, --help        Show this help
EOF
}

host="http://localhost:8000"
token="${API_TOKEN:-}"
all="0"
timeout="${WINEBOT_HEALTHCHECK_TIMEOUT_SECONDS:-20}"

while [ $# -gt 0 ]; do
  case "$1" in
    --host)
      host="${2:-}"
      shift
      ;;
    --token)
      token="${2:-}"
      shift
      ;;
    --all)
      all="1"
      ;;
    --timeout)
      timeout="${2:-}"
      shift
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

if [ -z "$host" ]; then
  echo "Host URL required." >&2
  exit 1
fi

headers=()
if [ -n "$token" ]; then
  headers=(-H "X-API-Key: ${token}")
fi

endpoints=(/health)
if [ "$all" = "1" ]; then
  endpoints+=(
    /health/system
    /health/x11
    /health/windows
    /health/wine
    /health/tools
    /health/storage
    /health/recording
  )
fi

for endpoint in "${endpoints[@]}"; do
  url="${host%/}${endpoint}"
  if curl -s --fail --max-time "$timeout" "${headers[@]}" "$url" >/dev/null; then
    echo "OK ${endpoint}"
  else
    echo "FAIL ${endpoint}" >&2
    exit 1
  fi
done
