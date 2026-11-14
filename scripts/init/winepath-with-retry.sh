#!/usr/bin/env bash
# Convert Linux path for Wine tracing, retrying transient startup.
# Diagnostic output is fixed/enumerated; no private paths or Wine stderr.
set -euo pipefail
if [ "$#" -ne 1 ] || [ -z "$1" ]; then
  exit 2
fi
if ! command -v winepath >/dev/null 2>&1; then
  printf 'WINEPATH_DIAGNOSTIC stage=missing_binary\n' >&2
  exit 1
fi
last_stage=nonzero
for attempt in 1 2 3 4; do
  translated=""
  if translated="$(timeout 8s winepath -w "$1" 2>/dev/null | sed 's/\r$//')"; then
    if [ -n "$translated" ] &&
       [[ "$translated" != *$'\n'* ]] &&
       [[ "$translated" != *$'\r'* ]]; then
      printf '%s\n' "$translated"
      exit 0
    fi
    last_stage=invalid_output
  else
    rc="$?"
    case "$rc" in
      124) last_stage=timeout ;;
      *) last_stage=nonzero ;;
    esac
  fi
  if [ "$attempt" -lt 4 ]; then sleep 1; fi
done
printf 'WINEPATH_DIAGNOSTIC stage=%s\n' "$last_stage" >&2
exit 1
