#!/usr/bin/env bash
set -euo pipefail

url="${1:-http://localhost:8000/health}"
max_attempts="${2:-90}"
sleep_seconds="${3:-1}"

if ! [[ "$max_attempts" =~ ^[0-9]+$ ]] || [ "$max_attempts" -lt 1 ]; then
  echo "ERROR: max_attempts must be a positive integer" >&2
  exit 2
fi

if ! [[ "$sleep_seconds" =~ ^[0-9]+$ ]] || [ "$sleep_seconds" -lt 1 ]; then
  echo "ERROR: sleep_seconds must be a positive integer" >&2
  exit 2
fi

for ((i=1; i<=max_attempts; i++)); do
  if curl -fsS "$url" >/dev/null; then
    echo "API is ready at ${url}"
    exit 0
  fi
  echo "Waiting for API (${i}/${max_attempts}) at ${url}"
  sleep "$sleep_seconds"
done

echo "ERROR: API failed readiness check after ${max_attempts} attempts at ${url}" >&2
exit 1
