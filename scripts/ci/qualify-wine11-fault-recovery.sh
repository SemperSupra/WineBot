#!/usr/bin/env bash
# Public-RDTE, fail-closed openbox recovery after successful Wine11 REL soak.
# Fixed-category evidence only. Never print process IDs, raw logs or API tokens.
set -euo pipefail
compose_file="${1:-compose/docker-compose.yml}"
service="${2:-winebot-interactive}"

fail() {
  printf 'WINE11_FAULT_DIAGNOSTIC stage=%s\n' "$1"
  exit 1
}
case "$service" in winebot-interactive) ;; *) fail invalid_service ;; esac

read_openbox_pid() {
  docker compose -f "$compose_file" --profile interactive exec -T --user winebot \
    "$service" pgrep -o -x openbox 2>/dev/null || true
}
before="$(read_openbox_pid)"
[[ "$before" =~ ^[0-9]+$ ]] || fail baseline_window_manager_missing

if ! docker compose -f "$compose_file" --profile interactive exec -T --user winebot \
  "$service" pkill -x openbox >/dev/null 2>&1; then
  fail bounded_injection_failed
fi

deadline=$((SECONDS + 75))
while ((SECONDS < deadline)); do
  after="$(read_openbox_pid)"
  if [[ "$after" =~ ^[0-9]+$ ]] && [ "$after" != "$before" ]; then
    echo 'WINE11_FAULT_DIAGNOSTIC stage=window_manager_recovered'
    exit 0
  fi
  sleep 2
done
fail window_manager_recovery_timeout
