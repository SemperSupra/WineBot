#!/usr/bin/env bash
set -euo pipefail

# diagnose-wine-registry.sh: Verify integrity of core WineBot settings

LOG_DIR="${1:-/tmp/winebot_diagnostics}"
mkdir -p "$LOG_DIR"

log() {
    printf '[%s] [REGISTRY] %s
' "$(date -u +%Y-%m-%dT%H:%M:%SZ)" "$*"
}

ERRORS=0

check_key() {
    local key="$1"
    local value="$2"
    local expected="$3"
    
    log "Checking ${key}\${value}..."
    actual=$(wine reg query "$key" /v "$value" 2>/dev/null | grep "$value" | awk '{print $NF}' | tr -d '' || echo "MISSING")
    
    if [[ "$actual" == *"$expected"* ]]; then
        log "  [OK] Found expected value: $expected"
    else
        log "  [ERROR] Mismatch! Expected: $expected, Actual: $actual"
        ERRORS=$((ERRORS + 1))
    fi
}

log "Starting Wine Registry Integrity Audit..."

# 1. Verify Theme (Custom key added in install-theme.sh)
check_key "HKEY_CURRENT_USER\Software\WineBot" "ThemeApplied" "1"

# 2. Verify Performance/Input Tweaks
check_key "HKEY_CURRENT_USER\Software\Wine\X11 Driver" "UseXInput2" "N"
check_key "HKEY_CURRENT_USER\Software\Wine\X11 Driver" "Managed" "Y"

if [ $ERRORS -eq 0 ]; then
    log "Registry Audit: PASSED"
    exit 0
else
    log "Registry Audit: FAILED ($ERRORS errors found)"
    exit 1
fi
