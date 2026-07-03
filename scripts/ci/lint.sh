#!/usr/bin/env bash
set -euo pipefail
echo "--- Running Linting (Ruff + Mypy + ShellCheck) ---"
ruff check .
mypy api --ignore-missing-imports --platform linux

# ShellCheck: lint all shell scripts for common bugs and portability issues
echo "--- ShellCheck ---"
if command -v shellcheck >/dev/null 2>&1; then
    # Find all .sh files, excluding .git and __pycache__
    SHELL_SCRIPTS=$(find . -name "*.sh" -not -path "./.git/*" -not -path "*/__pycache__/*" 2>/dev/null || true)
    if [ -n "$SHELL_SCRIPTS" ]; then
        # shellcheck disable=SC2086
        shellcheck -S warning $SHELL_SCRIPTS || true
        echo "ShellCheck: $(echo "$SHELL_SCRIPTS" | wc -w) scripts checked"
    fi
else
    echo "Warning: shellcheck not found, skipping shell script linting."
fi

python3 scripts/ci/verify-capability-matrix.py
python3 scripts/ci/generate-python-sbom.py --output artifacts/ci/python-sbom.cdx.json
python3 scripts/ci/validate-sbom.py --input artifacts/ci/python-sbom.cdx.json
python3 scripts/ci/check-license-policy.py --input artifacts/ci/python-sbom.cdx.json
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
