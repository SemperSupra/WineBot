#!/usr/bin/env bash
set -euo pipefail
echo "--- Running Linting (Ruff + Mypy) ---"
ruff check .
mypy api automation tests scripts/*.py --ignore-missing-imports

echo "--- Running Vulnerability Scan (Trivy) ---"
if command -v trivy >/dev/null 2>&1; then
    trivy fs --exit-code 1 --severity CRITICAL,HIGH --ignore-unfixed .
else
    echo "Warning: trivy not found, skipping filesystem scan."
fi
