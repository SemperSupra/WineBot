#!/usr/bin/env bash
set -euo pipefail

compose_file="${1:-compose/docker-compose.yml}"
profile="${2:-interactive}"
service="${3:-winebot-interactive}"
max_attempts="${4:-120}"
sleep_seconds="${5:-2}"

if ! [[ "$max_attempts" =~ ^[0-9]+$ ]] || [ "$max_attempts" -lt 1 ]; then
  echo "ERROR: max_attempts must be a positive integer" >&2
  exit 2
fi

if ! [[ "$sleep_seconds" =~ ^[0-9]+$ ]] || [ "$sleep_seconds" -lt 1 ]; then
  echo "ERROR: sleep_seconds must be a positive integer" >&2
  exit 2
fi

container_id="$(docker compose -f "$compose_file" --profile "$profile" ps -q "$service" | head -n1)"
if [ -z "${container_id}" ]; then
  echo "ERROR: no container found for service=${service} profile=${profile}" >&2
  exit 1
fi

for ((i=1; i<=max_attempts; i++)); do
  status="$(docker inspect --format='{{if .State.Health}}{{.State.Health.Status}}{{else}}none{{end}}' "$container_id" 2>/dev/null || echo unknown)"
  case "$status" in
    healthy)
      echo "Service ${service} is healthy (${container_id})"
      exit 0
      ;;
    unhealthy)
      echo "ERROR: service ${service} became unhealthy (${container_id})" >&2
      docker compose -f "$compose_file" --profile "$profile" logs --tail 200 "$service" || true
      exit 1
      ;;
    *)
      echo "Waiting for ${service} health (${i}/${max_attempts}) status=${status}"
      ;;
  esac
  sleep "$sleep_seconds"
done

echo "ERROR: service ${service} did not become healthy after ${max_attempts} attempts" >&2
docker compose -f "$compose_file" --profile "$profile" logs --tail 200 "$service" || true
exit 1
