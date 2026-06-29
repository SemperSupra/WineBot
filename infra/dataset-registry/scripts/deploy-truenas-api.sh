#!/usr/bin/env bash
# ── Automated TrueNAS MinIO Deployment via API ─────────────────────────────
# Deploys MinIO as a TrueNAS Custom App using the TrueNAS midclt API.
# Fully automated — prompts only for the root password with good defaults.
#
# Usage:
#   bash deploy-truenas-api.sh
#
# Prerequisites:
#   - SSH access to TrueNAS at truenas.fritz.box
#   - Root or sudo on TrueNAS
#   - API key for TrueNAS (auto-generated if not provided)
# ──────────────────────────────────────────────────────────────────────────────

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "${SCRIPT_DIR}/.." && pwd)"

# ── Configuration ────────────────────────────────────────────────────────────
TRUENAS_HOST="${INFRA_TRUENAS_HOST:-truenas.fritz.box}"
TRUENAS_PORT="${INFRA_TRUENAS_PORT:-443}"
TRUENAS_API_KEY="${INFRA_TRUENAS_API_KEY:-}"
APP_NAME="minio-dataset-registry"
MINIO_DATA_DIR="/mnt/Storage/models/minio"
MINIO_ROOT_USER="${MINIO_ROOT_USER:-winebot}"

# ── Colors ───────────────────────────────────────────────────────────────────
RED='\033[0;31m'; GREEN='\033[0;32m'; YELLOW='\033[1;33m'; CYAN='\033[0;36m'; NC='\033[0m'
info()  { echo -e "${GREEN}[INFO]${NC} $*"; }
warn()  { echo -e "${YELLOW}[WARN]${NC} $*"; }
error() { echo -e "${RED}[ERROR]${NC} $*"; }
prompt() { echo -e "${CYAN}[INPUT]${NC} $*"; }

# ── Preamble ─────────────────────────────────────────────────────────────────
echo ""
echo "╔═══════════════════════════════════════════════════════════════════╗"
echo "║      TrueNAS Dataset Registry — Automated Deployment             ║"
echo "╚═══════════════════════════════════════════════════════════════════╝"
echo ""
echo "  This will deploy MinIO on ${TRUENAS_HOST} and configure it for"
echo "  versioned dataset storage with DVC."
echo ""

# ── Step 1: Verify connectivity ─────────────────────────────────────────────
info "Testing connectivity to ${TRUENAS_HOST}..."
if ! ssh -o ConnectTimeout=5 -o BatchMode=yes "root@${TRUENAS_HOST}" "echo OK" 2>/dev/null; then
    warn "SSH key authentication failed. You may need to enter a password."
    prompt "SSH to ${TRUENAS_HOST} as which user?"
    read -r -p "  Username [root]: " SSH_USER
    SSH_USER="${SSH_USER:-root}"

    # Test with password auth
    if ! ssh -o ConnectTimeout=5 "${SSH_USER}@${TRUENAS_HOST}" "echo OK" 2>/dev/null; then
        error "Cannot connect to ${TRUENAS_HOST}. Verify:"
        echo "   1. The hostname '${TRUENAS_HOST}' resolves correctly"
        echo "   2. SSH is enabled on TrueNAS (Services → SSH)"
        echo "   3. Your SSH key is added or you have the password"
        exit 1
    fi
else
    SSH_USER="root"
fi
info "Connected to ${TRUENAS_HOST} as ${SSH_USER}"

# ── Step 2: Get or generate API key ─────────────────────────────────────────
if [ -z "$TRUENAS_API_KEY" ]; then
    prompt "TrueNAS API key not found."
    echo ""
    echo "  Generate one at: TrueNAS Web UI → Settings → API Keys → Add"
    echo "  Or enter one now, or leave blank to auto-generate via SSH."
    echo ""
    read -r -p "  API Key (or press Enter to auto-generate): " TRUENAS_API_KEY

    if [ -z "$TRUENAS_API_KEY" ]; then
        info "Auto-generating API key via SSH..."
        TRUENAS_API_KEY=$(ssh "${SSH_USER}@${TRUENAS_HOST}" \
          "midclt call api_key.create '{\"name\": \"dataset-registry-deploy\"}' | python3 -c 'import sys,json; print(json.load(sys.stdin)[\"key\"])'" 2>/dev/null || echo "")

        if [ -n "$TRUENAS_API_KEY" ]; then
            info "API key generated successfully."
        else
            error "Could not auto-generate API key."
            echo "  Generate one manually at: TrueNAS Web UI → Settings → API Keys → Add"
            exit 1
        fi
    fi
fi

# Store for API calls
API_HEADER="Authorization: Bearer ${TRUENAS_API_KEY}"
API_BASE="https://${TRUENAS_HOST}/api/v2.0"

# ── Step 3: Prompt for MinIO root password ───────────────────────────────────
if [ -z "${MINIO_ROOT_PASSWORD:-}" ]; then
    prompt "Set MinIO root password."
    echo "  This is the admin password for the MinIO web console."
    echo "  Save this in your password manager."
    echo ""
    read -r -s -p "  MinIO Password [auto-generate]: " MINIO_ROOT_PASSWORD
    echo ""
    if [ -z "$MINIO_ROOT_PASSWORD" ]; then
        MINIO_ROOT_PASSWORD=$(openssl rand -base64 24 | tr -dc 'a-zA-Z0-9' | head -c 20)
        info "Auto-generated password: ${MINIO_ROOT_PASSWORD}"
        prompt "  Save this password! Press Enter to continue."
        read -r
    fi
fi

# ── Step 4: Ensure data directory exists on TrueNAS ─────────────────────────
info "Ensuring MinIO data directory exists on TrueNAS..."
ssh "${SSH_USER}@${TRUENAS_HOST}" "mkdir -p '${MINIO_DATA_DIR}'" 2>/dev/null

# ── Step 5: Deploy MinIO via TrueNAS API ────────────────────────────────────
info "Deploying MinIO as TrueNAS Custom App..."

# Check if app already exists
EXISTING=$(curl -sk "${API_BASE}/app" \
  -H "${API_HEADER}" 2>/dev/null | python3 -c "
import json,sys
try:
    apps=json.load(sys.stdin)
    for a in apps:
        if a.get('name') == '${APP_NAME}':
            print(a['name'])
except: pass
" 2>/dev/null || echo "")

if [ -n "$EXISTING" ]; then
    warn "App '${APP_NAME}' already exists. Updating..."
    # Update existing app
    curl -sk -X PUT "${API_BASE}/app/${APP_NAME}" \
      -H "${API_HEADER}" \
      -H "Content-Type: application/json" \
      -d "$(cat << JSON
{
  "values": {
    "image": "minio/minio:latest",
    "container_args": ["server", "/data", "--console-address", ":9001"],
    "ports": [
      {"container_port": 9000, "node_port": 9000},
      {"container_port": 9001, "node_port": 9001}
    ],
    "volumes": [
      {"host_path": "${MINIO_DATA_DIR}", "mount_path": "/data"}
    ],
    "environment": [
      {"name": "MINIO_ROOT_USER", "value": "${MINIO_ROOT_USER}"},
      {"name": "MINIO_ROOT_PASSWORD", "value": "${MINIO_ROOT_PASSWORD}"}
    ]
  }
}
JSON
)" > /dev/null 2>&1
    info "MinIO app updated."
else
    # Create new app
    RESP=$(curl -sk -X POST "${API_BASE}/app" \
      -H "${API_HEADER}" \
      -H "Content-Type: application/json" \
      -d "$(cat << JSON
{
  "name": "${APP_NAME}",
  "image": "minio/minio:latest",
  "container_args": ["server", "/data", "--console-address", ":9001"],
  "ports": [
    {"container_port": 9000, "node_port": 9000},
    {"container_port": 9001, "node_port": 9001}
  ],
  "volumes": [
    {"host_path": "${MINIO_DATA_DIR}", "mount_path": "/data"}
  ],
  "environment": [
    {"name": "MINIO_ROOT_USER", "value": "${MINIO_ROOT_USER}"},
    {"name": "MINIO_ROOT_PASSWORD", "value": "${MINIO_ROOT_PASSWORD}"}
  ]
}
JSON
)" 2>/dev/null)

    if echo "$RESP" | python3 -c "import json,sys; d=json.load(sys.stdin); sys.exit(0 if d.get('name') else 1)" 2>/dev/null; then
        info "MinIO app deployed successfully!"
    else
        warn "App deployment via API may need web UI fallback."
        warn "Check TrueNAS Web UI → Apps for status."
        echo ""
        prompt "  Press Enter to continue once the app is running."
        read -r
    fi
fi

# ── Step 6: Wait for MinIO to be healthy ────────────────────────────────────
info "Waiting for MinIO to become healthy..."
for i in $(seq 1 30); do
    if curl -sf "http://${TRUENAS_HOST}:9000/minio/health/live" > /dev/null 2>&1; then
        info "MinIO is ready!"
        break
    fi
    if [ "$i" -eq 30 ]; then
        warn "MinIO did not become healthy within 60s."
        warn "Check TrueNAS Web UI → Apps for ${APP_NAME} status."
        prompt "  Press Enter to continue once MinIO is running."
        read -r
    fi
    sleep 2
done

# ── Step 7: Post-deploy — Create buckets and DVC user ───────────────────────
info "Running post-deploy configuration via TrueNAS CLI..."
ssh "${SSH_USER}@${TRUENAS_HOST}" "bash -s" << 'POSTDEPLOY'
    set -euo pipefail

    # Install mc if missing
    if ! command -v mc >/dev/null 2>&1; then
        curl -sL -o /usr/local/bin/mc https://dl.min.io/client/mc/release/linux-amd64/mc
        chmod +x /usr/local/bin/mc
    fi

    MINIO_ROOT_USER="${1}"
    MINIO_ROOT_PASSWORD="${2}"
    MINIO_API="http://127.0.0.1:9000"

    mc alias set truenas "${MINIO_API}" "${MINIO_ROOT_USER}" "${MINIO_ROOT_PASSWORD}" > /dev/null 2>&1

    # Create buckets
    for bucket in winebot-models winebot-annotations winebot-archives; do
        if ! mc ls "truenas/${bucket}" > /dev/null 2>&1; then
            mc mb "truenas/${bucket}" > /dev/null 2>&1
            echo "  Created bucket: ${bucket}"
        else
            echo "  Bucket exists: ${bucket}"
        fi
    done

    # Create DVC user policy
    cat > /tmp/minio-policy.json << 'POLICY'
{
  "Version": "2012-10-17",
  "Statement": [
    {
      "Effect": "Allow",
      "Action": ["s3:ListBucket", "s3:GetObject", "s3:PutObject", "s3:DeleteObject"],
      "Resource": ["arn:aws:s3:::winebot-models/*", "arn:aws:s3:::winebot-models"]
    },
    {
      "Effect": "Allow",
      "Action": ["s3:ListBucket", "s3:GetObject", "s3:PutObject"],
      "Resource": ["arn:aws:s3:::winebot-annotations/*", "arn:aws:s3:::winebot-annotations"]
    }
  ]
}
POLICY

    mc admin policy create truenas winebot-user /tmp/minio-policy.json > /dev/null 2>&1 || true

    # Generate DVC access key
    DVC_ACCESS_KEY="winebot-dvc"
    DVC_SECRET_KEY=$(openssl rand -base64 32 | tr -dc 'a-zA-Z0-9' | head -c 32)
    mc admin user add truenas "${DVC_ACCESS_KEY}" "${DVC_SECRET_KEY}" > /dev/null 2>&1 || true
    mc admin policy set truenas winebot-user user="${DVC_ACCESS_KEY}" > /dev/null 2>&1
    rm -f /tmp/minio-policy.json

    # Output credentials
    echo "DVC_ACCESS_KEY=${DVC_ACCESS_KEY}"
    echo "DVC_SECRET_KEY=${DVC_SECRET_KEY}"
POSTDEPLOY "$MINIO_ROOT_USER" "$MINIO_ROOT_PASSWORD"

# Capture DVC credentials from output
DVC_ACCESS_KEY="winebot-dvc"
DVC_SECRET_KEY=$(ssh "${SSH_USER}@${TRUENAS_HOST}" "mc admin user info truenas winebot-dvc 2>/dev/null | head -1" || echo "")

# ── Final Summary ────────────────────────────────────────────────────────────
echo ""
echo "╔═══════════════════════════════════════════════════════════════════╗"
echo "║           DEPLOYMENT COMPLETE                                    ║"
echo "╚═══════════════════════════════════════════════════════════════════╝"
echo ""
echo "  MinIO Console:  http://${TRUENAS_HOST}:9001"
echo "  S3 API:         http://${TRUENAS_HOST}:9000"
echo "  Admin User:     ${MINIO_ROOT_USER}"
echo ""
echo "  ── DVC Credentials ──"
echo "  Access Key: ${DVC_ACCESS_KEY}"
echo "  Secret Key: ${DVC_SECRET_KEY}"
echo ""
echo "  ── Client Setup ──"
echo "  Linux/WSL: ${PROJECT_ROOT}/scripts/setup-client.sh"
echo "  Windows:   ${PROJECT_ROOT}/scripts/setup-client.ps1"
echo ""

# ── Offer to run client setup ───────────────────────────────────────────────
prompt "Run client setup on this machine now?"
read -r -p "  [Y/n]: " RUN_CLIENT
if [[ "${RUN_CLIENT:-Y}" =~ ^[Yy] ]]; then
    export INFRA_MINIO_ACCESS_KEY="${DVC_ACCESS_KEY}"
    export INFRA_MINIO_SECRET_KEY="${DVC_SECRET_KEY}"
    bash "${PROJECT_ROOT}/scripts/setup-client.sh"
fi

info "Done! To version your first dataset:"
echo "    cd /path/to/your/data"
echo "    dvc add your-dataset/"
echo "    dvc push -r truenas"
echo ""
