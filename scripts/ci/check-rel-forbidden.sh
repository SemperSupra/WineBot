#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
PATTERNS_FILE="${ROOT_DIR}/policy/rel_forbidden_patterns.txt"
TARGET_INTENT="${TARGET_INTENT:-rel}"
IMAGE_TAG="${IMAGE_TAG:-winebot:${TARGET_INTENT}-check}"
DOCKERFILE="${DOCKERFILE:-docker/Dockerfile}"
BASE_IMAGE="${BASE_IMAGE:-ghcr.io/mark-e-deyoung/winebot-base:base-2026-02-13}"

if ! command -v docker >/dev/null 2>&1; then
  echo "docker command not found" >&2
  exit 1
fi

if [ ! -f "$PATTERNS_FILE" ]; then
  echo "Missing patterns file: $PATTERNS_FILE" >&2
  exit 1
fi

case "${TARGET_INTENT}" in
  rel|rel-runner) ;;
  *)
    echo "TARGET_INTENT must be rel or rel-runner (got: ${TARGET_INTENT})" >&2
    exit 1
    ;;
esac

echo "[rel-check] Building ${TARGET_INTENT} image: ${IMAGE_TAG}"
docker build \
  --target "intent-${TARGET_INTENT}" \
  --build-arg BASE_IMAGE="${BASE_IMAGE}" \
  --build-arg BUILD_INTENT="${TARGET_INTENT}" \
  --tag "${IMAGE_TAG}" \
  --file "${ROOT_DIR}/${DOCKERFILE}" \
  "${ROOT_DIR}"

echo "[rel-check] Verifying BUILD_INTENT=${TARGET_INTENT} in image environment"
if ! docker inspect "${IMAGE_TAG}" --format '{{range .Config.Env}}{{println .}}{{end}}' | grep -q "^BUILD_INTENT=${TARGET_INTENT}$"; then
  echo "${TARGET_INTENT} image missing BUILD_INTENT=${TARGET_INTENT} environment" >&2
  exit 1
fi

failures=0
while IFS= read -r pattern; do
  pattern="${pattern%%#*}"
  pattern="$(echo "$pattern" | xargs)"
  [ -z "$pattern" ] && continue
  if docker run --rm --entrypoint bash "${IMAGE_TAG}" -lc "[ -e '${pattern}' ]"; then
    echo "[rel-check] Forbidden path exists: ${pattern}" >&2
    failures=1
  fi
done < "$PATTERNS_FILE"

echo "[rel-check] Verifying test-only API route markers are absent"
if docker run --rm --entrypoint bash "${IMAGE_TAG}" -lc "grep -R -n -E '/test|test-only|debug-backdoor' /api 2>/dev/null"; then
  echo "[rel-check] Potential test-only route marker found in /api" >&2
  failures=1
fi

if [ "$failures" -ne 0 ]; then
  echo "[rel-check] FAILED" >&2
  exit 1
fi

echo "[rel-check] PASSED"
