#!/usr/bin/env bash
# Convert one Linux path for Wine input tracing, retrying transient Wine startup.
# No fallback path and no sensitive Wine stderr are admitted to caller logs.
set -euo pipefail
if [ "$#" -ne 1 ] || [ -z "$1" ]; then
  exit 2
fi
for attempt in 1 2 3 4; do
  translated=""
  if translated="$(timeout 8s winepath -w "$1" 2>/dev/null)"; then
    # Command substitution strips final LF but retains CR from CRLF output.
    # Normalize only that terminator; reject embedded control characters.
    translated="${translated%
  if [ "$attempt" -lt 4 ]; then sleep 1; fi
done
exit 1
\r'}"
    if [ -n "$translated" ] &&
        [[ "$translated" != *
  if [ "$attempt" -lt 4 ]; then sleep 1; fi
done
exit 1
\n'* ]] &&
        [[ "$translated" != *
  if [ "$attempt" -lt 4 ]; then sleep 1; fi
done
exit 1
\r'* ]]; then
      printf '%s\n' "$translated"
      exit 0
    fi
  fi
  if [ "$attempt" -lt 4 ]; then sleep 1; fi
done
exit 1
