#!/usr/bin/env bash
# ── Dataset Registry — OS Credential Store (Linux/macOS) ─────────────────────
# Stores and retrieves DVC/Garage credentials in the OS keychain.
#
# Linux:  uses secret-tool (libsecret) — works with GNOME Keyring, KDE Wallet
# macOS:  uses security (Keychain)
#
# Usage:
#   # Store credentials (run after receiving them from post-deploy.sh)
#   bash scripts/setup-credential-store.sh \
#     --access-key "GKxxxx" \
#     --secret-key "your-secret-key" \
#     --host "truenas.fritz.box" \
#     --port 30188
#
#   # Retrieve credentials (for use in other scripts)
#   eval "$(bash scripts/setup-credential-store.sh --export)"
#
#   # Verify credentials are stored
#   bash scripts/setup-credential-store.sh --status
# ──────────────────────────────────────────────────────────────────────────────

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "${SCRIPT_DIR}/.." && pwd)"

# ── Key identifiers (used for keyring lookups) ───────────────────────────────
KEYRING_ACCESS_KEY="winebot-dataset-registry-access-key"
KEYRING_SECRET_KEY="winebot-dataset-registry-secret-key"
KEYRING_HOST="winebot-dataset-registry-host"
KEYRING_PORT="winebot-dataset-registry-port"

# ── Usage ────────────────────────────────────────────────────────────────────
usage() {
    cat <<EOF
Usage: $(basename "$0") [OPTIONS]

Store, retrieve, or verify dataset registry credentials in the OS keychain.

Options:
  --access-key KEY    S3 access key ID to store
  --secret-key KEY    S3 secret access key to store
  --host HOST         S3 endpoint hostname
  --port PORT         S3 endpoint port
  --export            Print credentials as env vars for eval
  --status            Show whether credentials are stored
  --help              Show this message

Examples:
  $(basename "$0") --access-key "GKxxxx" --secret-key "s3cr3t" \\
    --host "truenas.fritz.box" --port 30188

  eval "\$($(basename "$0") --export)"
  $(basename "$0") --status
EOF
    exit 0
}

# ── Detect OS and credential tool ────────────────────────────────────────────
detect_tool() {
    case "$(uname -s)" in
        Linux*)
            if command -v secret-tool >/dev/null 2>&1; then
                echo "secret-tool"
            elif command -v security >/dev/null 2>&1 && \
                 security -h 2>&1 | grep -q generic-password; then
                # macOS security command is available, but we're on Linux with
                # the same-named tool? Unlikely, but check.
                echo "security"
            else
                echo ""
            fi
            ;;
        Darwin*)
            if command -v security >/dev/null 2>&1; then
                echo "security"
            elif command -v secret-tool >/dev/null 2>&1; then
                echo "secret-tool"
            else
                echo ""
            fi
            ;;
        MINGW*|MSYS*|CYGWIN*)
            # These are Git Bash on Windows — use cmdkey via PowerShell
            echo "wincred"
            ;;
        *)
            echo ""
            ;;
    esac
}

# ── Credential operations ───────────────────────────────────────────────────

# secret-tool (Linux/libsecret)
store_secret_tool() {
    local key="$1" value="$2" label="$3"
    echo "$value" | secret-tool store \
        --label="$label" \
        application "winebot-dataset-registry" \
        key "$key" > /dev/null 2>&1
}

get_secret_tool() {
    local key="$1"
    secret-tool lookup application "winebot-dataset-registry" key "$key" 2>/dev/null || true
}

has_secret_tool() {
    local key="$1"
    secret-tool lookup application "winebot-dataset-registry" key "$key" 2>/dev/null | grep -q . || return 1
}

# security (macOS Keychain)
store_security() {
    local key="$1" value="$2" label="$3"
    security add-generic-password \
        -a "$key" \
        -s "com.winebot.dataset-registry.$key" \
        -l "$label" \
        -w "$value" \
        -U > /dev/null 2>&1 || true
}

get_security() {
    local key="$1"
    security find-generic-password \
        -a "$key" \
        -s "com.winebot.dataset-registry.$key" \
        -w 2>/dev/null || true
}

has_security() {
    local key="$1"
    security find-generic-password \
        -a "$key" \
        -s "com.winebot.dataset-registry.$key" \
        -w 2>/dev/null | grep -q . || return 1
}

# ── Main ─────────────────────────────────────────────────────────────────────
TOOL=$(detect_tool)

# Parse args
ACCESS_KEY=""
SECRET_KEY=""
HOST=""
PORT=""
MODE="store"

while [[ $# -gt 0 ]]; do
    case "$1" in
        --access-key)  ACCESS_KEY="$2"; shift 2 ;;
        --secret-key)  SECRET_KEY="$2"; shift 2 ;;
        --host)        HOST="$2"; shift 2 ;;
        --port)        PORT="$2"; shift 2 ;;
        --export)      MODE="export"; shift ;;
        --status)      MODE="status"; shift ;;
        --help|-h)     usage ;;
        *)             echo "Unknown option: $1"; usage ;;
    esac
done

# ── Mode: Export ─────────────────────────────────────────────────────────────
if [ "$MODE" = "export" ]; then
    if [ -z "$TOOL" ]; then
        echo "ERROR: No credential manager found." >&2
        echo "# Install libsecret-tools (Linux) or use macOS Keychain." >&2
        exit 1
    fi

    case "$TOOL" in
        secret-tool)
            AK=$(get_secret_tool "$KEYRING_ACCESS_KEY")
            SK=$(get_secret_tool "$KEYRING_SECRET_KEY")
            H=$(get_secret_tool "$KEYRING_HOST")
            P=$(get_secret_tool "$KEYRING_PORT")
            ;;
        security)
            AK=$(get_security "$KEYRING_ACCESS_KEY")
            SK=$(get_security "$KEYRING_SECRET_KEY")
            H=$(get_security "$KEYRING_HOST")
            P=$(get_security "$KEYRING_PORT")
            ;;
    esac

    if [ -z "$AK" ] || [ -z "$SK" ]; then
        echo "ERROR: Credentials not found in OS keychain." >&2
        echo "# Run with --access-key and --secret-key to store them first." >&2
        exit 1
    fi

    echo "export INFRA_MINIO_ACCESS_KEY='${AK}'"
    echo "export INFRA_MINIO_SECRET_KEY='${SK}'"
    echo "export INFRA_TRUENAS_HOST='${H:-truenas.fritz.box}'"
    echo "export INFRA_MINIO_PORT='${P:-30188}'"
    exit 0
fi

# ── Mode: Status ─────────────────────────────────────────────────────────────
if [ "$MODE" = "status" ]; then
    echo "Credential manager: ${TOOL:-NONE}"
    echo ""

    if [ -z "$TOOL" ]; then
        echo "✗ No supported credential manager found."
        echo "  Linux: sudo apt install libsecret-tools"
        echo "  macOS: Keychain (built-in)"
        exit 1
    fi

    for entry in "$KEYRING_ACCESS_KEY:$KEYRING_SECRET_KEY:$KEYRING_HOST:$KEYRING_PORT"; do
        IFS=: read -r k1 k2 k3 k4 <<< "$entry"
    done

    case "$TOOL" in
        secret-tool)
            AK=$(get_secret_tool "$KEYRING_ACCESS_KEY")
            SK=$(get_secret_tool "$KEYRING_SECRET_KEY")
            H=$(get_secret_tool "$KEYRING_HOST")
            P=$(get_secret_tool "$KEYRING_PORT")
            ;;
        security)
            AK=$(get_security "$KEYRING_ACCESS_KEY")
            SK=$(get_security "$KEYRING_SECRET_KEY")
            H=$(get_security "$KEYRING_HOST")
            P=$(get_security "$KEYRING_PORT")
            ;;
    esac

    echo "Access Key:  ${AK:+✓ stored}${AK:-✗ missing}"
    echo "Secret Key:  ${SK:+✓ stored}${SK:-✗ missing}"
    echo "Host:        ${H:-${H:+✓ }${H:-truenas.fritz.box}}"
    echo "Port:        ${P:-${P:+✓ }${P:-30188}}"

    if [ -n "$AK" ] && [ -n "$SK" ]; then
        echo ""
        echo "Credentials present. To export:"
        echo "  eval \"\$($0 --export)\""
        return 0
    else
        return 1
    fi
fi

# ── Mode: Store ──────────────────────────────────────────────────────────────
if [ -z "$ACCESS_KEY" ] || [ -z "$SECRET_KEY" ]; then
    echo "ERROR: --access-key and --secret-key are required." >&2
    usage
fi

if [ -z "$TOOL" ]; then
    echo "ERROR: No supported credential manager found." >&2
    echo ""
    echo "  Linux:  sudo apt install libsecret-tools"
    echo "  macOS:  Keychain (built-in, should be available)"
    echo ""
    echo "  Alternatively, set environment variables:"
    echo "    export INFRA_MINIO_ACCESS_KEY='${ACCESS_KEY}'"
    echo "    export INFRA_MINIO_SECRET_KEY='${SECRET_KEY}'"
    echo ""
    exit 1
fi

case "$TOOL" in
    secret-tool)
        store_secret_tool "$KEYRING_ACCESS_KEY" "$ACCESS_KEY" "WineBot Dataset Registry — S3 Access Key"
        store_secret_tool "$KEYRING_SECRET_KEY" "$SECRET_KEY" "WineBot Dataset Registry — S3 Secret Key"
        store_secret_tool "$KEYRING_HOST" "${HOST:-truenas.fritz.box}" "WineBot Dataset Registry — S3 Host"
        store_secret_tool "$KEYRING_PORT" "${PORT:-30188}" "WineBot Dataset Registry — S3 Port"
        ;;
    security)
        store_security "$KEYRING_ACCESS_KEY" "$ACCESS_KEY" "WineBot Dataset Registry — S3 Access Key"
        store_security "$KEYRING_SECRET_KEY" "$SECRET_KEY" "WineBot Dataset Registry — S3 Secret Key"
        store_security "$KEYRING_HOST" "${HOST:-truenas.fritz.box}" "WineBot Dataset Registry — S3 Host"
        store_security "$KEYRING_PORT" "${PORT:-30188}" "WineBot Dataset Registry — S3 Port"
        ;;
esac

echo "✓ Credentials stored in ${TOOL} (OS keychain)"
echo ""
echo "To export:  eval \"\$($0 --export)\""
echo "To verify:  $0 --status"

# If setup-client scripts exist, offer to run them
if [ -f "${SCRIPT_DIR}/setup-client.sh" ]; then
    echo ""
    echo "You can now run client setup:"
    echo "  eval \"\$($0 --export)\""
    echo "  bash ${SCRIPT_DIR}/setup-client.sh"
fi
