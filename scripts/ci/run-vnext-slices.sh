#!/usr/bin/env bash
# Public evidence is counts-only; raw classified test data never leaves runner.
set -euo pipefail
: "$API_URL"
compose="winebot/compose/docker-compose.yml"
for label in portable_core_candidate capability_extension_candidate implementation_specific obsolete_contract unresolved; do
  raw="vnext-internal-$label.json"
  local_log="vnext-internal-$label.log"
  health_log="vnext-internal-$label-health.log"
  # Diagnose runner-local failure logs through the fixed stage allowlist only.
  # Never echo untrusted Docker/Wine stdout, paths or runtime identifiers.
  emit_stage() {
    if ! python3 winebot/scripts/ci/classify-startup-logs.py < "$health_log"; then
      echo "STARTUP_DIAGNOSTIC stage=classifier_failed"
    fi
  }
  if ! timeout 30s docker compose -f "$compose" --profile headless restart winebot > "$health_log" 2>&1; then
    echo "VNEXT_STATUS slice=$label state=restart_failed"
    emit_stage
    continue
  fi
  # Docker health checks have a 30s grace period; 25s prematurely labels
  # still-starting Wine restarts as unhealthy. Reuse the qualified initial
  # conformance gate's bounded 120s readiness allowance.
  if ! winebot/scripts/ci/wait-for-container-health.sh "$compose" headless winebot 60 2 >> "$health_log" 2>&1; then
    echo "VNEXT_STATUS slice=$label state=unhealthy"
    emit_stage
    continue
  fi
  token="$(docker compose -f "$compose" exec -T winebot cat /tmp/winebot_api_token 2>/dev/null || true)"
  if [[ ! "$token" =~ ^[A-Za-z0-9._~-]{16,512}$ ]]; then
    echo "VNEXT_STATUS slice=$label state=credential_unavailable"
    continue
  fi
  printf '::add-mask::%s\n' "$token"
  rc=0
  timeout 75s python3 -m pytest contracts/tests/conformance/ \
    --api-url "$API_URL" --api-token "$token" -m "vnext_$label" \
    --results-file "$raw" -q --tb=no --show-capture=no -rN > "$local_log" 2>&1 || rc=$?
  if [ "$rc" -eq 0 ]; then
    echo "VNEXT_STATUS slice=$label state=passed exit=0"
  else
    echo "VNEXT_STATUS slice=$label state=nonpassing exit=$rc"
  fi
done
