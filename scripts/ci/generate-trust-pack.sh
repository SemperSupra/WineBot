#!/usr/bin/env bash
set -euo pipefail

OUT_DIR="${1:-artifacts/trust-pack}"
mkdir -p "$OUT_DIR"

timestamp="$(date -u +%Y-%m-%dT%H:%M:%SZ)"
sha="$(git rev-parse --short HEAD 2>/dev/null || echo unknown)"
branch="$(git rev-parse --abbrev-ref HEAD 2>/dev/null || echo unknown)"

cat > "${OUT_DIR}/summary.md" <<EOF
# WineBot Trust Pack

- Generated: ${timestamp}
- Branch: ${branch}
- Commit: ${sha}

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
