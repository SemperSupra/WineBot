#!/usr/bin/env bash
set -euo pipefail
echo "--- Running Linting (Ruff + Mypy) ---"
ruff check .
mypy api automation tests scripts/*.py --ignore-missing-imports
python3 scripts/ci/verify-capability-matrix.py
python3 scripts/ci/generate-python-sbom.py --output artifacts/ci/python-sbom.cdx.json
python3 scripts/ci/validate-sbom.py --input artifacts/ci/python-sbom.cdx.json
python3 scripts/ci/check-license-policy.py --input artifacts/ci/python-sbom.cdx.json

echo "--- Running Vulnerability Scan (Trivy) ---"
if command -v trivy >/dev/null 2>&1; then
    trivy fs --exit-code 1 --severity CRITICAL,HIGH --ignore-unfixed .
else
    echo "Warning: trivy not found, skipping filesystem scan."
fi
