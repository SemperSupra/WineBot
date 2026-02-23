#!/usr/bin/env bash
set -euo pipefail

# Backward-compatible CI entrypoint expected by compose/docker-compose.yml.
exec /work/scripts/bin/smoke-test.sh
