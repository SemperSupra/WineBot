#!/usr/bin/env bash
set -euo pipefail

PROFILE="${1:-pr}"

case "$PROFILE" in
  pr)
    export DURATION_SECONDS="${DURATION_SECONDS:-1200}"   # 20 minutes
    export INTERVAL_SECONDS="${INTERVAL_SECONDS:-30}"
    ;;
  nightly)
    export DURATION_SECONDS="${DURATION_SECONDS:-3600}"   # 1 hour
    export INTERVAL_SECONDS="${INTERVAL_SECONDS:-30}"
    ;;
  weekly)
    export DURATION_SECONDS="${DURATION_SECONDS:-21600}"  # 6 hours
    export INTERVAL_SECONDS="${INTERVAL_SECONDS:-60}"
    ;;
  *)
    echo "Usage: $0 [pr|nightly|weekly]" >&2
    exit 1
    ;;
esac

export MAX_LOG_MB="${MAX_LOG_MB:-1024}"
export MAX_SESSION_MB="${MAX_SESSION_MB:-8192}"
export MAX_PID1_RSS_MB="${MAX_PID1_RSS_MB:-2048}"

exec /scripts/diagnostics/diagnose-trace-soak.sh
