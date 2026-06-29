#!/usr/bin/env bash
# ── Automated Garage S3 Deployment on TrueNAS via API ────────────────────────
# Deploys Garage as a TrueNAS Custom App via the midclt REST API.
# Fully automated — prompts only for admin token with good defaults.
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
APP_NAME="garage-dataset-registry"

# Storage paths
GARAGE_DATA_DIR="${GARAGE_DATA_DIR:-/mnt/Storage/models/garage/data}"
GARAGE_META_DIR="${GARAGE_META_DIR:-/mnt/Storage/models/garage/meta}"
GARAGE_SNAPSHOT_DIR="${GARAGE_SNAPSHOT_DIR:-/mnt/Storage/models/garage/snapshots}"
GARAGE_CONFIG_DIR="${GARAGE_CONFIG_DIR:-/mnt/Storage/models/garage/config}"

# Network ports
GARAGE_S3_PORT="${GARAGE_S3_PORT:-30188}"
GARAGE_ADMIN_PORT="${GARAGE_ADMIN_PORT:-30190}"
GARAGE_WEB_PORT="${GARAGE_WEB_PORT:-30186}"
GARAGE_RPC_PORT="${GARAGE_RPC_PORT:-30187}"
GARAGE_S3_WEB_PORT="${GARAGE_S3_WEB_PORT:-30189}"

# ── Colors ───────────────────────────────────────────────────────────────────
RED='\033[0;31m'; GREEN='\033[0;32m'; YELLOW='\033[1;33m'; CYAN='\033[0;36m'; NC='\033[0m'
info()  { echo -e "${GREEN}[INFO]${NC} $*"; }
warn()  { echo -e "${YELLOW}[WARN]${NC} $*"; }
error() { echo -e "${RED}[ERROR]${NC} $*"; }
prompt() { echo -e "${CYAN}[INPUT]${NC} $*"; }

echo ""
echo "╔═══════════════════════════════════════════════════════════════════╗"
echo "║   TrueNAS Dataset Registry — Garage Automated Deployment         ║"
echo "╚═══════════════════════════════════════════════════════════════════╝"
echo ""
echo "  Note: Garage is an OFFICIAL community app."
echo "  For a simpler install, use:"
echo "    TrueNAS Web UI → Apps → Available Apps → Garage → Install"
echo ""
echo "  This script deploys via the TrueNAS API as a Custom App."
echo "  It requires the Garage Docker image spec."
echo ""

# ── Step 1: Verify connectivity ──────────────────────────────────────────────
info "Testing connectivity to ${TRUENAS_HOST}..."
if ! ssh -o ConnectTimeout=5 -o BatchMode=yes "root@${TRUENAS_HOST}" "echo OK" 2>/dev/null; then
    warn "SSH key authentication failed."
    prompt "SSH to ${TRUENAS_HOST} as which user?"
    read -r -p "  Username [root]: " SSH_USER
    SSH_USER="${SSH_USER:-root}"
    if ! ssh -o ConnectTimeout=5 "${SSH_USER}@${TRUENAS_HOST}" "echo OK" 2>/dev/null; then
        error "Cannot connect to ${TRUENAS_HOST}. Verify:"
        echo "   1. The hostname resolves correctly"
        echo "   2. SSH is enabled on TrueNAS (Services → SSH)"
        echo "   3. Your SSH key is added or you have the password"
        exit 1
    fi
else
    SSH_USER="root"
fi
info "Connected to ${TRUENAS_HOST} as ${SSH_USER}"

# ── Step 2: Get or generate API key ──────────────────────────────────────────
if [ -z "$TRUENAS_API_KEY" ]; then
    prompt "TrueNAS API key not found."
    echo ""
    echo "  Generate one at: TrueNAS Web UI → Settings → API Keys → Add"
    echo "  Or leave blank to auto-generate via SSH."
    echo ""
    read -r -p "  API Key (or Enter to auto-generate): " TRUENAS_API_KEY

    if [ -z "$TRUENAS_API_KEY" ]; then
        info "Auto-generating API key via SSH..."
        TRUENAS_API_KEY=$(ssh "${SSH_USER}@${TRUENAS_HOST}" \
          "midclt call api_key.create '{\"name\": \"dataset-registry-deploy\"}' | python3 -c 'import sys,json; print(json.load(sys.stdin)[\"key\"])'" 2>/dev/null || echo "")

        if [ -n "$TRUENAS_API_KEY" ]; then
            info "API key generated successfully."
        else
            error "Could not auto-generate API key."
            echo "  Generate one at: TrueNAS Web UI → Settings → API Keys → Add"
            exit 1
        fi
    fi
fi

API_HEADER="Authorization: Bearer ${TRUENAS_API_KEY}"
API_BASE="https://${TRUENAS_HOST}/api/v2.0"

# ── Step 3: Prompt for Garage secrets ─────────────────────────────────────────
if [ -z "${GARAGE_ADMIN_TOKEN:-}" ]; then
    prompt "Set Garage admin token."
    echo "  This is the token used for bucket/user management."
    echo ""
    read -r -s -p "  Admin Token [auto-generate]: " GARAGE_ADMIN_TOKEN
    echo ""
    if [ -z "$GARAGE_ADMIN_TOKEN" ]; then
        GARAGE_ADMIN_TOKEN=$(openssl rand -base64 32 | tr -dc 'a-zA-Z0-9' | head -c 32)
        info "Auto-generated admin token: ${GARAGE_ADMIN_TOKEN}"
        prompt "  Save this token! Press Enter to continue."
        read -r
    fi
fi

if [ -z "${GARAGE_RPC_SECRET:-}" ]; then
    GARAGE_RPC_SECRET=$(openssl rand -hex 32)
    info "Auto-generated RPC secret: ${GARAGE_RPC_SECRET}"
fi

# ── Step 4: Ensure data directories exist on TrueNAS ─────────────────────────
info "Ensuring Garage data directories exist on TrueNAS..."
ssh "${SSH_USER}@${TRUENAS_HOST}" "mkdir -p '${GARAGE_DATA_DIR}' '${GARAGE_META_DIR}' '${GARAGE_SNAPSHOT_DIR}' '${GARAGE_CONFIG_DIR}'" 2>/dev/null

# ── Step 5: Deploy Garage via TrueNAS API ─────────────────────────────────────
info "Deploying Garage as TrueNAS Custom App..."
info "Note: Installing via the official community app (TrueNAS Web UI → Apps → Garage) is preferred."
info "This API method creates a Custom App with the Garage Docker image."

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
    info "App '${APP_NAME}' already exists. Skipping deployment."
    info "Use post-deploy.sh to set up buckets and keys:"
    echo "  bash ${PROJECT_ROOT}/truenas-apps/garage/post-deploy.sh"
else
    warn "Custom App deployment requires a Docker Compose spec."
    warn "Garage's official image (dxflrs/garage) needs a config.toml."
    warn ""
    warn "RECOMMENDED: Install from TrueNAS Web UI → Apps → Available Apps → Garage"
    echo ""
    info "Installing from the community train is simpler and includes:"
    echo "  - Proper config file generation via init container"
    echo "  - Permissions container for storage ownership"
    echo "  - Optional web UI container (khairul169/garage-webui)"
    echo "  - Health checks and dependency ordering"
    echo ""
    echo "After installing from the UI, run the post-deploy script:"
    echo "  bash ${PROJECT_ROOT}/truenas-apps/garage/post-deploy.sh"
    echo ""
fi

# ── Step 6: Run post-deploy setup ─────────────────────────────────────────────
if [ -n "${GARAGE_ADMIN_TOKEN:-}" ]; then
    info "Running post-deploy setup..."
    GARAGE_ADMIN_TOKEN="${GARAGE_ADMIN_TOKEN}" bash "${PROJECT_ROOT}/truenas-apps/garage/post-deploy.sh"
fi

info "Done!"
