#!/usr/bin/env bash
set -euo pipefail

# diagnose-wine-registry.sh: Verify integrity of core WineBot settings

LOG_DIR="${1:-/tmp/winebot_diagnostics}"
mkdir -p "$LOG_DIR"

log() {
    printf '[%s] [REGISTRY] %s\n' "$(date -u +%Y-%m-%dT%H:%M:%SZ)" "$*"
}

ERRORS=0

check_key() {
    local key="$1"
    local value="$2"
    local expected="$3"
    
    log "Checking ${key}\\\\${value}..."
    # We use a temp file to avoid pipe issues with non-zero exit codes from grep
    local actual="MISSING"
    if wine reg query "$key" /v "$value" > /tmp/reg_out 2>&1; then
        actual=$(grep "$value" /tmp/reg_out | awk '{print $NF}' | tr -d '\r' || echo "MISSING")
    fi
    
    if [[ "$actual" == *"$expected"* ]]; then
        log "  [OK] Found expected value: $expected"
    else
        log "  [ERROR] Mismatch! Expected: $expected, Actual: $actual"
        ERRORS=$((ERRORS + 1))
    fi
}

log "Starting Wine Registry Integrity Audit..."

# 1. Verify Theme (Custom key added in install-theme.sh)
check_key "HKEY_CURRENT_USER\\Software\\WineBot" "ThemeApplied" "1"

# 2. Verify Performance/Input Tweaks
check_key "HKEY_CURRENT_USER\\Software\\Wine\\X11 Driver" "UseXInput2" "N"
check_key "HKEY_CURRENT_USER\\Software\\Wine\\X11 Driver" "Managed" "Y"

if [ $ERRORS -eq 0 ]; then
    log "Registry Audit: PASSED"
    exit 0
else
    log "Registry Audit: FAILED ($ERRORS errors found)"
    exit 1
fi
