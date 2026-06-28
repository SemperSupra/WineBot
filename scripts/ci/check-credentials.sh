#!/usr/bin/env bash
# ── Credential/Secret Scrub Script ──────────────────────────────────────────
# Scans git history and working tree for accidentally committed secrets.
#
# Usage:
#   scripts/ci/check-credentials.sh          # scans working tree only (fast)
#   scripts/ci/check-credentials.sh --history # scans entire git history (slow)
#   scripts/ci/check-credentials.sh --fix     # interactive fix mode
#   scripts/ci/check-credentials.sh --ci      # CI gate: exits 1 on any finding
#
# SECURITY.md Section 4 applies: no secrets in committed code.
# Pattern reference: .env.example, deploy/winebot-credentials.template
# ──────────────────────────────────────────────────────────────────────────────

set -euo pipefail

SCRIPT_NAME="$(basename "$0")"
MODE="working-tree"
CI_MODE=0
FIX_MODE=0
EXIT_CODE=0

source "$(dirname "$0")/../logging_utils.sh" 2>/dev/null || true

# ── Patterns ────────────────────────────────────────────────────────────────
# These match credential patterns that should NEVER appear in committed code.

CREDENTIAL_PATTERNS=(
  # INFRA_* credential variables with actual values (not empty/placeholder)
  'INFRA_WINEBOT_API_TOKEN=[^[:space:]"]+'
  'INFRA_GHCR_TOKEN=[^[:space:]"]+'
  'INFRA_CLOUDFLARE_TOKEN=[^[:space:]"]+'
  'INFRA_UPTIMEROBOT_APIKEY=[^[:space:]"]+'
  'INFRA_HF_TOKEN=[^[:space:]"]+'
  'INFRA_VNC_PASSWORD=[^[:space:]"]+'
  'INFRA_NOVNC_PASSWORD=[^[:space:]"]+'

  # Generic secrets
  'API[_-]KEY[=:]["'"'"']?[A-Za-z0-9_\-]{16,}'
  'API[_-]TOKEN[=:]["'"'"']?[A-Za-z0-9_\-]{16,}'
  'ACCESS[_-]KEY[=:]["'"'"']?[A-Za-z0-9_\-]{16,}'
  'SECRET[=:]["'"'"']?[A-Za-z0-9_\-]{16,}'
  'PASSWORD[=:]["'"'"']?[A-Za-z0-9_\-]{8,}'
  'TOKEN[=:]["'"'"']?[A-Za-z0-9_\-]{16,}'
  'ghp_[A-Za-z0-9_]{36,}'         # GitHub personal access tokens
  'gho_[A-Za-z0-9_]{36,}'         # GitHub OAuth tokens
  'hf_[A-Za-z0-9_]{16,}'          # HuggingFace tokens
  'sk-[A-Za-z0-9_]{32,}'          # OpenAI-style API keys

  # Private keys inlined (not in authorized_keys)
  '-----BEGIN (RSA |EC |DSA |OPENSSH )?PRIVATE KEY-----'
)

# Private key files to flag (even if empty)
KEY_FILE_PATTERNS=(
  '*id_rsa'
  '*id_ecdsa'
  '*id_ed25519'
  '*.pem'
  '*.key'
  '*.p12'
  '*.pfx'
)

# Infrastructure details that should not be in committed docs
INFRA_PATTERNS=(
  # Internal IPs (RFC 1918 is OK in configs, but flag hostnames)
  '[a-z]+\.fritz\.box'
  '[a-z]+\.local'
  '[a-z]+\.lan'
)

# ── Functions ───────────────────────────────────────────────────────────────

echo_stderr() { echo "$@" >&2; }

find_in_tree() {
  local pattern="$1"
  local label="$2"
  local path="${3:-.}"
  local results

  if [ "$MODE" = "history" ]; then
    results=$(git log --all --full-history -p --diff-filter=ACM \
      -G "$pattern" -- "$path" 2>/dev/null | grep -E "$pattern" | head -20 || true)
  else
    results=$(git grep -nIE "$pattern" -- "$path" 2>/dev/null | grep -v '^.gitignore' | grep -v '^deploy/' | head -20 || true)
  fi

  if [ -n "$results" ]; then
    echo_stderr "  ⚠  $label"
    echo_stderr "$results" | sed 's/^/      /'
    echo_stderr ""
    return 0
  fi
  return 1
}

find_key_files() {
  local found=0
  for pat in "${KEY_FILE_PATTERNS[@]}"; do
    local matches
    if [ "$MODE" = "history" ]; then
      matches=$(git log --all --full-history --diff-filter=A --name-only --pretty=format: -- "$pat" 2>/dev/null | head -10 || true)
    else
      matches=$(git ls-files "$pat" 2>/dev/null | head -10 || true)
    fi
    if [ -n "$matches" ]; then
      echo_stderr "  ⚠  Private key files found matching '$pat':"
      echo_stderr "$matches" | sed 's/^/      /'
      echo_stderr ""
      found=1
    fi
  done
  return $found
}

find_placeholders() {
  # Check that .env.example or deploy/*.template haven't been filled with real values
  local results
  results=$(grep -nE 'change-me|your-|YOUR_|placeholder|example' \
    .env.example deploy/winebot-credentials.template 2>/dev/null || true)

  if [ -n "$results" ]; then
    # This is GOOD — it means placeholders are still placeholders
    return 0
  fi
}

# ── Main ────────────────────────────────────────────────────────────────────

while [ $# -gt 0 ]; do
  case "$1" in
    --history) MODE="history"; shift ;;
    --ci)      CI_MODE=1; shift ;;
    --fix)     FIX_MODE=1; shift ;;
    --help|-h)
      echo "Usage: $SCRIPT_NAME [--history|--ci|--fix]"
      echo "  (no flag)  Scan working tree for credential leakage"
      echo "  --history  Scan entire git history (slow, thorough)"
      echo "  --ci       CI gate: exit 1 on any finding"
      echo "  --fix      Interactive BFG/git-filter-branch fix mode"
      exit 0
      ;;
    *) echo "Unknown option: $1"; exit 1 ;;
  esac
done

# ── Fix Mode: Remove secrets from git history ──────────────────────────
if [ "$FIX_MODE" = "1" ]; then
  echo "━━━ Credential Scrub: FIX MODE ━━━━━━━━━━━━━━━━━━━━━━━━━━━"
  echo ""
  echo "This will rewrite git history to remove credential patterns."
  echo "Run '$0' first to identify what needs removal."
  echo ""
  echo "Options:"
  echo "  1) git filter-branch (native, works everywhere)"
  echo "  2) BFG Repo-Cleaner (faster, requires Java)"
  echo "  q) Cancel"
  echo ""
  read -r -p "Select option [1/2/q]: " fix_choice

  case "$fix_choice" in
    1)
      echo "Running git filter-branch to scrub INFRA_* patterns..."
      git filter-branch --force --tree-filter '
        for f in $(git ls-files); do
          sed -i "s/INFRA_[A-Z_]*=[^ ]*/INFRA_&=/g" "$f" 2>/dev/null || true
        done
      ' -- --all
      echo ""
      echo "Done. Verify with '$0 --history' then force-push:"
      echo "  git push origin --force --all"
      ;;
    2)
      if command -v java >/dev/null 2>&1; then
        echo "BFG: https://rtyley.github.io/bfg-repo-cleaner/"
        echo "  java -jar bfg.jar --delete-files .env --no-blob-protection"
      else
        echo "Java not found. Use option 1 (git filter-branch) instead."
      fi
      ;;
    *)
      echo "Cancelled."
      exit 0
      ;;
  esac
  exit 0
fi

echo_stderr "━━━ Credential Scrub: ${MODE} mode ━━━━━━━━━━━━━━━━━━━━━━━━━"
echo_stderr ""

hits=0

# Section 1: Credential patterns
echo_stderr "▸ Checking credential patterns..."
for pat in "${CREDENTIAL_PATTERNS[@]}"; do
  if find_in_tree "$pat" "Matched: $pat"; then
    hits=$((hits + 1))
  fi
done

# Section 2: Key files
echo_stderr "▸ Checking for private key files..."
if find_key_files; then
  hits=$((hits + 1))
fi

# Section 3: Infrastructure details
echo_stderr "▸ Checking infrastructure exposure..."
for pat in "${INFRA_PATTERNS[@]}"; do
  if find_in_tree "$pat" "Matched: $pat"; then
    hits=$((hits + 1))
  fi
done

# Section 4: Verify placeholders still safe
echo_stderr "▸ Verifying template placeholders..."
find_placeholders

# Section 5: Check .gitignore includes credential files
echo_stderr "▸ Checking .gitignore coverage..."
if grep -q '\.env' .gitignore 2>/dev/null; then
  : # good
else
  echo_stderr "  ⚠  .gitignore does not contain .env"
  hits=$((hits + 1))
fi

echo_stderr ""
if [ "$hits" -eq 0 ]; then
  echo_stderr "✅ No credential leakage detected."
  exit 0
else
  echo_stderr "❌ $hits credential risk(s) detected."
  echo_stderr ""
  echo_stderr "Recommended actions:"
  echo_stderr "  1. Remove secrets from files and re-commit"
  echo_stderr "  2. For history cleanup: $0 --fix"
  echo_stderr "  3. Update .gitignore if needed"
  echo_stderr ""
  echo_stderr "See SECURITY.md Section 4 (Credential Management Policy)."
  [ "$CI_MODE" = "1" ] && exit 1 || exit 0
fi
