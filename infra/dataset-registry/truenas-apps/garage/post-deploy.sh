#!/usr/bin/env bash
# ── Garage Post-Deploy Setup ──────────────────────────────────────────────────
# Run this AFTER installing Garage from the TrueNAS community train.
# Creates S3 buckets and generates DVC-compatible API keys.
#
# Usage:
#   bash truenas-apps/garage/post-deploy.sh
#
# Prerequisites:
#   - Garage app installed and running on TrueNAS
#   - SSH access to TrueNAS at truenas.fritz.box
#   - Garage admin token from installation
# ──────────────────────────────────────────────────────────────────────────────

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "${SCRIPT_DIR}/../.." && pwd)"

# ── Configuration ────────────────────────────────────────────────────────────
TRUENAS_HOST="${INFRA_TRUENAS_HOST:-truenas.fritz.box}"
GARAGE_CONTAINER="${GARAGE_CONTAINER:-garage}"
GARAGE_S3_PORT="${GARAGE_S3_PORT:-30188}"
GARAGE_ADMIN_PORT="${GARAGE_ADMIN_PORT:-30190}"
GARAGE_ADMIN_TOKEN="${GARAGE_ADMIN_TOKEN:-}"

# Buckets mirroring our MinIO structure
BUCKETS=("winebot-models" "winebot-annotations" "winebot-archives")

# ── Colors ───────────────────────────────────────────────────────────────────
RED='\033[0;31m'; GREEN='\033[0;32m'; YELLOW='\033[1;33m'; CYAN='\033[0;36m'; NC='\033[0m'
info()  { echo -e "${GREEN}[INFO]${NC} $*"; }
warn()  { echo -e "${YELLOW}[WARN]${NC} $*"; }
error() { echo -e "${RED}[ERROR]${NC} $*"; }
prompt() { echo -e "${CYAN}[INPUT]${NC} $*"; }

# ── Check connectivity ───────────────────────────────────────────────────────
info "Testing SSH connectivity to ${TRUENAS_HOST}..."
if ! ssh -o ConnectTimeout=5 -o BatchMode=yes "root@${TRUENAS_HOST}" "echo OK" 2>/dev/null; then
    prompt "SSH to ${TRUENAS_HOST} as which user?"
    read -r -p "  Username [root]: " SSH_USER
    SSH_USER="${SSH_USER:-root}"
    if ! ssh -o ConnectTimeout=5 "${SSH_USER}@${TRUENAS_HOST}" "echo OK" 2>/dev/null; then
        error "Cannot connect to ${TRUENAS_HOST}"
        exit 1
    fi
else
    SSH_USER="root"
fi
info "Connected to ${TRUENAS_HOST} as ${SSH_USER}"

# ── Get admin token ───────────────────────────────────────────────────────────
if [ -z "$GARAGE_ADMIN_TOKEN" ]; then
    prompt "Enter Garage admin token (from your installation):"
    read -r -s GARAGE_ADMIN_TOKEN
    echo ""
    if [ -z "$GARAGE_ADMIN_TOKEN" ]; then
        error "Admin token is required"
        exit 1
    fi
fi

# ── Verify Garage is running ──────────────────────────────────────────────────
info "Verifying Garage container is running..."
if ! ssh "${SSH_USER}@${TRUENAS_HOST}" \
    "docker ps --filter name=${GARAGE_CONTAINER} --format '{{.Names}}' | grep -q ${GARAGE_CONTAINER}" 2>/dev/null; then
    error "Garage container '${GARAGE_CONTAINER}' not found on ${TRUENAS_HOST}"
    info "Available containers:"
    ssh "${SSH_USER}@${TRUENAS_HOST}" "docker ps --format 'table {{.Names}}\t{{.Status}}'" 2>/dev/null || true
    exit 1
fi
info "Garage container is running."

# ── Verify Garage health via admin API ────────────────────────────────────────
info "Checking Garage health via admin API..."
if ! ssh "${SSH_USER}@${TRUENAS_HOST}" \
    "docker exec ${GARAGE_CONTAINER} /garage status" 2>/dev/null; then
    warn "Could not query Garage status directly."
    warn "Will proceed with bucket creation anyway."
fi

# ── Create buckets via Garage CLI ────────────────────────────────────────────
info "Creating buckets..."
for bucket in "${BUCKETS[@]}"; do
    if ssh "${SSH_USER}@${TRUENAS_HOST}" \
        "docker exec ${GARAGE_CONTAINER} garage bucket info ${bucket}" 2>/dev/null; then
        info "  Bucket already exists: ${bucket}"
    else
        info "  Creating bucket: ${bucket}"
        ssh "${SSH_USER}@${TRUENAS_HOST}" \
            "docker exec ${GARAGE_CONTAINER} garage bucket create ${bucket}" 2>/dev/null || \
        warn "  Could not create bucket ${bucket} (may already exist)"
    fi
done

# ── Create DVC API key ────────────────────────────────────────────────────────
DVC_KEY_NAME="winebot-dvc"
info "Creating DVC API key: ${DVC_KEY_NAME}..."

# Generate a strong secret key
DVC_SECRET_KEY=$(openssl rand -base64 32 | tr -dc 'a-zA-Z0-9' | head -c 32)

# Create the key in Garage
KEY_OUTPUT=$(ssh "${SSH_USER}@${TRUENAS_HOST}" \
    "docker exec ${GARAGE_CONTAINER} garage key new --name ${DVC_KEY_NAME}" 2>/dev/null || true)

if [ -z "$KEY_OUTPUT" ]; then
    # Key may already exist — retrieve its info
    KEY_OUTPUT=$(ssh "${SSH_USER}@${TRUENAS_HOST}" \
        "docker exec ${GARAGE_CONTAINER} garage key info ${DVC_KEY_NAME}" 2>/dev/null || echo "")
fi

# Extract Access Key ID from output
# Garage outputs: "Key ID: GK..."
DVC_ACCESS_KEY=$(echo "$KEY_OUTPUT" | grep -oP 'Key ID:\s+\K\S+' | head -1)

if [ -z "$DVC_ACCESS_KEY" ]; then
    warn "Could not extract access key from output."
    warn "Output was: ${KEY_OUTPUT}"
    prompt "Enter the Access Key ID from the output above:"
    read -r DVC_ACCESS_KEY
fi

# ── Grant key access to buckets ───────────────────────────────────────────────
info "Granting ${DVC_KEY_NAME} access to buckets..."
for bucket in "${BUCKETS[@]}"; do
    ssh "${SSH_USER}@${TRUENAS_HOST}" \
        "docker exec ${GARAGE_CONTAINER} garage bucket allow \\
            --read --write --owner ${bucket} \\
            --key ${DVC_KEY_NAME}" 2>/dev/null || true
    info "  Granted access to: ${bucket}"
done

# ── Output credentials ────────────────────────────────────────────────────────
echo ""
echo "╔═══════════════════════════════════════════════════════════════════╗"
echo "║           DATASET REGISTRY — GARAGE DEPLOYED                     ║"
echo "╚═══════════════════════════════════════════════════════════════════╝"
echo ""
echo "  Garage Web UI:  http://${TRUENAS_HOST}:30186"
echo "  S3 API:         http://${TRUENAS_HOST}:30188"
echo "  Admin API:      http://${TRUENAS_HOST}:30190"
echo "  Region:         garage"
echo ""
echo "  ── DVC Credentials ──"
echo "  Endpoint: http://${TRUENAS_HOST}:30188"
echo "  Access Key: ${DVC_ACCESS_KEY:-winebot-dvc}"
echo "  Secret Key: ${DVC_SECRET_KEY}"
echo ""
echo "  Buckets: ${BUCKETS[*]}"
echo ""
echo "  ── Client Setup (recommended: use OS credential manager) ──"
echo "  Linux/WSL:"
echo "    1. bash ${PROJECT_ROOT}/scripts/setup-credential-store.sh \\"
echo "         --access-key '${DVC_ACCESS_KEY:-winebot-dvc}' \\"
echo "         --secret-key '${DVC_SECRET_KEY}' \\"
echo "         --host '${TRUENAS_HOST}' --port ${GARAGE_S3_PORT}"
echo "    2. bash ${PROJECT_ROOT}/scripts/setup-client.sh"
echo ""
echo "  Windows:"
echo "    1. powershell ${PROJECT_ROOT}/scripts/setup-credential-store.ps1 \\"
echo "         -AccessKey '${DVC_ACCESS_KEY:-winebot-dvc}' \\"
echo "         -SecretKey '${DVC_SECRET_KEY}'"
echo "    2. powershell ${PROJECT_ROOT}/scripts/setup-client.ps1"
echo ""
echo "  Or export as env vars (for CI/CD):"
echo "    export INFRA_TRUENAS_HOST=truenas.fritz.box"
echo "    export INFRA_MINIO_PORT=${GARAGE_S3_PORT}"
echo "    export INFRA_MINIO_BUCKET=winebot-models"
echo "    export INFRA_MINIO_ACCESS_KEY=${DVC_ACCESS_KEY:-winebot-dvc}"
echo "    export INFRA_MINIO_SECRET_KEY=${DVC_SECRET_KEY}"
echo ""

# ── Offer to run credential store + client setup ──────────────────────────────
prompt "Store credentials in OS keychain and run client setup now?"
read -r -p "  [Y/n]: " RUN_CLIENT
if [[ "${RUN_CLIENT:-Y}" =~ ^[Yy] ]]; then
    # Store in OS keychain
    if [ -f "${PROJECT_ROOT}/scripts/setup-credential-store.sh" ]; then
        bash "${PROJECT_ROOT}/scripts/setup-credential-store.sh" \
            --access-key "${DVC_ACCESS_KEY:-winebot-dvc}" \
            --secret-key "${DVC_SECRET_KEY}" \
            --host "${TRUENAS_HOST}" \
            --port "${GARAGE_S3_PORT}" 2>/dev/null || true
    fi

    # Export env vars and run client setup
    export INFRA_MINIO_ACCESS_KEY="${DVC_ACCESS_KEY:-winebot-dvc}"
    export INFRA_MINIO_SECRET_KEY="${DVC_SECRET_KEY}"
    export INFRA_MINIO_PORT="${GARAGE_S3_PORT}"
    bash "${PROJECT_ROOT}/scripts/setup-client.sh"
fi

info "Done!"
