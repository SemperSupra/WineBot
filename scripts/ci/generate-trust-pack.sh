#!/usr/bin/env bash
set -euo pipefail

OUT_DIR="${1:-artifacts/trust-pack}"

# The checkout can be a synthetic PR merge commit rather than the source head.
# Record both IDs with unambiguous names; refuse provenance-free evidence.
checkout_sha="$(git rev-parse HEAD 2>/dev/null || true)"
source_sha="${WINEBOT_SOURCE_HEAD_SHA:-$checkout_sha}"
for candidate in "$checkout_sha" "$source_sha"; do
    if [[ ! "$candidate" =~ ^[0-9a-f]{40}$ ]]; then
        echo "Trust pack requires valid full checkout/source Git SHAs" >&2
        exit 1
    fi
done
branch="$(git rev-parse --abbrev-ref HEAD 2>/dev/null || echo unknown)"
timestamp="$(date -u +%Y-%m-%dT%H:%M:%SZ)"
mkdir -p "$OUT_DIR"

cat > "${OUT_DIR}/summary.md" <<EOF
# WineBot Trust Pack

- Generated: ${timestamp}
- Checkout ref: ${branch}
- Tested checkout commit: ${checkout_sha}
- Source head commit: ${source_sha}
- Note: These may differ when GitHub Actions checks out a pull-request merge candidate.

## Included Artifacts

- Capability matrix: \`docs/test-capability-matrix.md\`
- Default profiles: \`docs/default-profiles.md\`
- Feature map: \`docs/feature-capability-commit-map.md\`
- Test inventory: \`tests/\` and \`tests/e2e/\`

## Notes

This bundle is intended as release evidence for coverage, diagnostics, and test policy compliance.
EOF

python3 <<'PY' > "${OUT_DIR}/inventory.json"
import json
from pathlib import Path

root = Path(".")
tests = sorted(str(p) for p in (root / "tests").rglob("test_*.py"))
e2e = sorted(str(p) for p in (root / "tests" / "e2e").rglob("test_*.py"))
diagnostics = sorted(str(p) for p in (root / "scripts" / "diagnostics").glob("*.sh"))
out = {
    "tests": tests,
    "e2e_tests": e2e,
    "diagnostic_scripts": diagnostics,
}
print(json.dumps(out, indent=2))
PY

echo "Trust pack written to ${OUT_DIR}"
