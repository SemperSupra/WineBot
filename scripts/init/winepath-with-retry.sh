#!/usr/bin/env bash
# Convert one Linux path for Wine input tracing, retrying transient Wine startup.
# No fallback path and no sensitive Wine stderr are admitted to caller logs.
set -euo pipefail
if [ "$#" -ne 1 ] || [ -z "$1" ]; then
  exit 2
fi
for attempt in 1 2 3 4; do
  translated=""
  if translated="$(timeout 8s winepath -w "$1" 2>/dev/null | sed 's/\r$//')" &&
      [ -n "$translated" ] &&
      [[ "$translated" != *$'\n'* ]] &&
      [[ "$translated" != *$'\r'* ]]; then
    printf '%s\n' "$translated"
    exit 0
  fi
  if [ "$attempt" -lt 4 ]; then sleep 1; fi
done
exit 1
