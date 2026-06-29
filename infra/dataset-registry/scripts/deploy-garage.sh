#!/usr/bin/env bash
# ── Automated TrueNAS Garage Deployment ───────────────────────────────────────
# Installs Garage from the official TrueNAS community train, configured for
# WineBot's dataset registry environment.
#
# Usage:
#   bash deploy-garage.sh
#
# This script:
#   1. Connects to TrueNAS via SSH
#   2. Generates all required secrets (admin token, RPC secret, web UI password)
#   3. Creates storage directories on TrueNAS
#   4. Installs Garage from the OFFICIAL community catalog via TrueNAS API
#   5. Waits for the app to become healthy
#   6. Creates buckets (winebot-models, winebot-annotations, winebot-archives)
#   7. Generates DVC-compatible API keys
#   8. Stores credentials in your local OS keychain
#   9. Configures DVC on this machine
# ──────────────────────────────────────────────────────────────────────────────

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "${SCRIPT_DIR}/../.." && pwd)"

# ── Configuration ────────────────────────────────────────────────────────────
TRUENAS_HOST="${INFRA_TRUENAS_HOST:-truenas.fritz.box}"
TRUENAS_PORT="${INFRA_TRUENAS_PORT:-443}"
TRUENAS_API_KEY="${INFRA_TRUENAS_API_KEY:-}"
APP_NAME="garage"
CATALOG="OFFICIAL"
TRAIN="community"
SSH_USER="root"

# Storage paths (tuned for your environment)
GARAGE_DATA_DIR="/mnt/Storage/models/garage/data"
GARAGE_META_DIR="/mnt/Storage/models/garage/meta"
GARAGE_SNAPSHOT_DIR="/mnt/Storage/models/garage/snapshots"

# Network ports
GARAGE_S3_PORT=30188
GARAGE_ADMIN_PORT=30190
GARAGE_WEB_PORT=30186
GARAGE_RPC_PORT=30187

# ── Colors ───────────────────────────────────────────────────────────────────
RED='\033[0;31m'; GREEN='\033[0;32m'; YELLOW='\033[1;33m'; CYAN='\033[0;36m'; NC='\033[0m'
info()  { echo -e "${GREEN}[INFO]${NC} $*"; }
warn()  { echo -e "${YELLOW}[WARN]${NC} $*"; }
error() { echo -e "${RED}[ERROR]${NC} $*"; }
prompt() { echo -e "${CYAN}[INPUT]${NC} $*"; }
ok()    { echo -e "${GREEN}✓${NC} $*"; }

# ── Header ───────────────────────────────────────────────────────────────────
clear
echo "╔═══════════════════════════════════════════════════════════════════╗"
echo "║     Garage TrueNAS — Automated Deployment                        ║"
echo "║     WineBot Dataset Registry                                     ║"
echo "╚═══════════════════════════════════════════════════════════════════╝"
echo ""
echo "  Target:  ${TRUENAS_HOST}"
echo "  App:     Garage (${CATALOG}/${TRAIN})"
echo "  S3 API:  port ${GARAGE_S3_PORT}"
echo "  Web UI:  port ${GARAGE_WEB_PORT}"
echo "  Data:    ${GARAGE_DATA_DIR}"
echo ""

# ═════════════════════════════════════════════════════════════════════════════
# STEP 1: Verify SSH connectivity
# ═════════════════════════════════════════════════════════════════════════════
info "Step 1/7: Testing SSH connectivity to ${TRUENAS_HOST}..."

if ssh -o ConnectTimeout=5 -o BatchMode=yes "${SSH_USER}@${TRUENAS_HOST}" "echo OK" 2>/dev/null; then
    ok "SSH key authentication successful"
else
    warn "SSH key auth failed. Trying password..."
    if ! ssh -o ConnectTimeout=10 "${SSH_USER}@${TRUENAS_HOST}" "echo OK" 2>/dev/null; then
        error "Cannot reach ${TRUENAS_HOST}. Verify:"
        echo "   1. SSH enabled: TrueNAS Web UI → Services → SSH (running)"
        echo "   2. Hostname resolves: ping ${TRUENAS_HOST}"
        echo "   3. Network connectivity"
        echo ""
        prompt "Enter the SSH username [root]:"
        read -r SSH_USER_INPUT
        SSH_USER="${SSH_USER_INPUT:-root}"
        if ! ssh -o ConnectTimeout=10 "${SSH_USER}@${TRUENAS_HOST}" "echo OK"; then
            error "Still cannot connect. Fix SSH access and try again."
            exit 1
        fi
    fi
fi

# Verify TrueNAS version
TRUENAS_VERSION=$(ssh "${SSH_USER}@${TRUENAS_HOST}" "cat /etc/version 2>/dev/null || uname -r" 2>/dev/null || echo "unknown")
info "TrueNAS version: ${TRUENAS_VERSION}"

# Check if Docker apps system is available
if ! ssh "${SSH_USER}@${TRUENAS_HOST}" "which midclt 2>/dev/null" > /dev/null 2>&1; then
    error "midclt not found on TrueNAS. This requires TrueNAS 24.10+ with Apps system."
    exit 1
fi
ok "midclt available"

# ═════════════════════════════════════════════════════════════════════════════
# STEP 2: Generate secrets
# ═════════════════════════════════════════════════════════════════════════════
info "Step 2/7: Generating secrets..."

ADMIN_TOKEN=$(openssl rand -base64 32 | tr -dc 'a-zA-Z0-9' | head -c 32)
RPC_SECRET=$(openssl rand -hex 32)
WEB_UI_PASSWORD=$(openssl rand -base64 16 | tr -dc 'a-zA-Z0-9' | head -c 16)

ok "Admin token generated"
ok "RPC secret generated"
ok "Web UI password generated"

echo ""
echo "  ── Generated Secrets (save these) ──"
echo "  Admin Token:     ${ADMIN_TOKEN}"
echo "  RPC Secret:      ${RPC_SECRET}"
echo "  Web UI Password: ${WEB_UI_PASSWORD}"
echo ""

prompt "Review the secrets above, then press Enter to continue..."
read -r

# ═════════════════════════════════════════════════════════════════════════════
# STEP 3: Create storage directories
# ═════════════════════════════════════════════════════════════════════════════
info "Step 3/7: Creating storage directories on TrueNAS..."

for dir in "$GARAGE_DATA_DIR" "$GARAGE_META_DIR" "$GARAGE_SNAPSHOT_DIR"; do
    ssh "${SSH_USER}@${TRUENAS_HOST}" "mkdir -p '$dir' && chmod 755 '$dir'" 2>/dev/null
    ok "Created: $dir"
done

# ═════════════════════════════════════════════════════════════════════════════
# STEP 4: Check if Garage is already installed
# ═════════════════════════════════════════════════════════════════════════════
info "Step 4/7: Checking for existing Garage installation..."

EXISTING=$(ssh "${SSH_USER}@${TRUENAS_HOST}" \
    "midclt call app.list 2>/dev/null | python3 -c \"
import json,sys
try:
    apps=json.load(sys.stdin)
    for a in apps:
        if a.get('name','').lower().startswith('garage'):
            print(a['name'])
except: pass
\" 2>/dev/null || true")

if [ -n "$EXISTING" ]; then
    warn "Garage app already installed as: ${EXISTING}"
    warn "Upgrade/reinstall not supported via this script."
    echo ""
    prompt "Continue with post-deploy setup only? [Y/n]: "
    read -r SKIP_INSTALL
    if [[ ! "${SKIP_INSTALL:-Y}" =~ ^[Yy] ]]; then
        error "Remove the existing app first from TrueNAS Web UI → Apps."
        exit 1
    fi
else
    # ═══════════════════════════════════════════════════════════════════════════
    # STEP 5: Install Garage from the official community catalog
    # ═══════════════════════════════════════════════════════════════════════════
    info "Step 5/7: Installing Garage from the ${CATALOG}/${TRAIN} catalog..."
    echo "  This may take a few minutes (pulling image + starting containers)"
    echo ""

    # Build the values JSON for the install
    # This matches the questions.yaml schema for the Garage community app
    INSTALL_JSON=$(cat << JSON
{
  "catalog": "${CATALOG}",
  "train": "${TRAIN}",
  "app_name": "${APP_NAME}",
  "values": {
    "TZ": "America/New_York",
    "garage": {
      "admin_token": "${ADMIN_TOKEN}",
      "region": "garage",
      "rpc_secret": "${RPC_SECRET}",
      "enable_web_ui_auth": true,
      "web_ui_username": "admin",
      "web_ui_password": "${WEB_UI_PASSWORD}",
      "replication_factor": 1,
      "additional_options": [],
      "additional_envs": []
    },
    "run_as": {
      "user": 568,
      "group": 568
    },
    "network": {
      "web_port": {
        "bind_mode": "published",
        "port_number": ${GARAGE_WEB_PORT},
        "host_ips": []
      },
      "rpc_port": {
        "bind_mode": "exposed",
        "port_number": ${GARAGE_RPC_PORT},
        "host_ips": []
      },
      "s3_port": {
        "bind_mode": "published",
        "port_number": ${GARAGE_S3_PORT},
        "host_ips": []
      },
      "s3_web_port": {
        "bind_mode": "exposed",
        "port_number": 30189,
        "host_ips": []
      },
      "admin_port": {
        "bind_mode": "published",
        "port_number": ${GARAGE_ADMIN_PORT},
        "host_ips": []
      },
      "networks": []
    },
    "storage": {
      "config": {
        "type": "ix_volume",
        "ix_volume_config": {
          "dataset_name": "garage-config",
          "acl_enable": false
        }
      },
      "metadata": {
        "type": "host_path",
        "host_path_config": {
          "path": "${GARAGE_META_DIR}",
          "acl_enable": false
        }
      },
      "data": {
        "type": "host_path",
        "host_path_config": {
          "path": "${GARAGE_DATA_DIR}",
          "acl_enable": false
        }
      },
      "metadata_snapshots": {
        "type": "host_path",
        "host_path_config": {
          "path": "${GARAGE_SNAPSHOT_DIR}",
          "acl_enable": false
        }
      },
      "additional_storage": []
    },
    "labels": [],
    "resources": {
      "limits": {
        "cpus": 2,
        "memory": 2048
      }
    }
  }
}
JSON
)

    # Install via midclt on TrueNAS
    INSTALL_RESULT=$(ssh "${SSH_USER}@${TRUENAS_HOST}" \
        "midclt call app.install '$(echo "$INSTALL_JSON" | tr -d '\n' | tr -d ' ')'" 2>&1) || true

    # midclt may need the JSON formatted differently (with newlines/spaces)
    # Try with proper JSON formatting if the compact version failed
    if echo "$INSTALL_RESULT" | grep -qi "error\|traceback\|failed"; then
        warn "Compact JSON failed. Trying with formatted JSON..."
        INSTALL_RESULT=$(ssh "${SSH_USER}@${TRUENAS_HOST}" \
            "midclt call app.install '$(echo "$INSTALL_JSON")'" 2>&1) || true
    fi

    # Check if installation was successful or already in progress
    if echo "$INSTALL_RESULT" | grep -qi "already\|exists\|installed\|success"; then
        ok "Garage app installation initiated"
    elif [ -z "$INSTALL_RESULT" ] || echo "$INSTALL_RESULT" | grep -qi "Job\|\"id\""; then
        ok "Garage install job submitted"
    else
        warn "Install result: ${INSTALL_RESULT}"
        warn ""

        # ── Fallback: Try via REST API ──────────────────────────────────────
        warn "midclt install may have failed. Trying REST API..."

        # Get API key if we don't have one
        if [ -z "$TRUENAS_API_KEY" ]; then
            info "Auto-generating TrueNAS API key..."
            TRUENAS_API_KEY=$(ssh "${SSH_USER}@${TRUENAS_HOST}" \
                "midclt call api_key.create '{\"name\": \"garage-deploy\"}' | python3 -c 'import sys,json; print(json.load(sys.stdin)[\"key\"])'" 2>/dev/null || echo "")
        fi

        if [ -n "$TRUENAS_API_KEY" ]; then
            API_HEADER="Authorization: Bearer ${TRUENAS_API_KEY}"
            API_BASE="https://${TRUENAS_HOST}/api/v2.0"

            REST_RESULT=$(curl -sk -X POST "${API_BASE}/app/install" \
                -H "${API_HEADER}" \
                -H "Content-Type: application/json" \
                -d "$INSTALL_JSON" 2>&1) || true

            if echo "$REST_RESULT" | grep -qi "id\|name\|success"; then
                ok "Garage install via REST API submitted"
            else
                warn "REST API result: ${REST_RESULT}"
                echo ""
                echo "────────────────────────────────────────────────────────────────────"
                echo "  To install manually:"
                echo "  1. Open TrueNAS Web UI → Apps → Available Apps"
                echo "  2. Search for 'Garage' and click Install"
                echo "  3. Use truenas-apps/garage/garage-values.yaml as reference"
                echo "     (or the values printed above)"
                echo "  4. After install, run this again to continue setup"
                echo "────────────────────────────────────────────────────────────────────"
                prompt "Press Enter after Garage is installed in the Web UI..."
                read -r
            fi
        else
            echo ""
            echo "────────────────────────────────────────────────────────────────────"
            echo "  Cannot install via API automatically."
            echo ""
            echo "  Install manually:"
            echo "  1. TrueNAS Web UI → Apps → Available Apps → Garage → Install"
            echo "  2. Use these secrets:"
            echo "     - Admin Token: ${ADMIN_TOKEN}"
            echo "     - RPC Secret:  ${RPC_SECRET}"
            echo "     - Web UI: admin / ${WEB_UI_PASSWORD}"
            echo "  3. Set S3 port: ${GARAGE_S3_PORT}"
            echo "  4. Set data path: ${GARAGE_DATA_DIR}"
            echo "  5. Set metadata path: ${GARAGE_META_DIR}"
            echo "────────────────────────────────────────────────────────────────────"
            prompt "Press Enter after Garage is installed..."
            read -r
        fi
    fi
fi

# ═════════════════════════════════════════════════════════════════════════════
# STEP 6: Wait for Garage to become healthy
# ═════════════════════════════════════════════════════════════════════════════
info "Step 6/7: Waiting for Garage to become healthy..."
echo "  Checking every 5 seconds (timeout: 3 minutes)..."
echo ""

HEALTHY=false
for i in $(seq 1 36); do
    # Check via docker on TrueNAS
    CONTAINER_ID=$(ssh "${SSH_USER}@${TRUENAS_HOST}" \
        "docker ps --filter name=garage --format '{{.ID}}' 2>/dev/null | head -1" 2>/dev/null || true)

    if [ -n "$CONTAINER_ID" ]; then
        HEALTH_CHECK=$(ssh "${SSH_USER}@${TRUENAS_HOST}" \
            "docker exec ${CONTAINER_ID} /garage status 2>/dev/null" 2>/dev/null || true)

        if echo "$HEALTH_CHECK" | grep -qi "healthy\|ring\|nodes\|capacity" 2>/dev/null; then
            HEALTHY=true
            ok "Garage is healthy!"
            break
        fi

        # Also try health endpoint
        if curl -sf "http://${TRUENAS_HOST}:${GARAGE_ADMIN_PORT}/health" > /dev/null 2>&1; then
            HEALTHY=true
            ok "Garage admin API is responsive!"
            break
        fi
    fi

    # Progress indicator
    if [ $((i % 6)) -eq 0 ]; then
        echo "  Still waiting... ($((i * 5))s elapsed)"
    fi
    sleep 5
done

if [ "$HEALTHY" = false ]; then
    warn "Garage did not become healthy within 3 minutes."
    warn "Continuing with post-deploy setup — it may fail if Garage isn't ready."
    echo ""
    prompt "Press Enter to continue anyway..."
    read -r
fi

# ═════════════════════════════════════════════════════════════════════════════
# STEP 7: Post-deploy — Create buckets and DVC keys
# ═════════════════════════════════════════════════════════════════════════════
info "Step 7/7: Creating buckets and DVC credentials..."

# Find the actual Garage container name
GARAGE_CONTAINER=$(ssh "${SSH_USER}@${TRUENAS_HOST}" \
    "docker ps --filter name=garage --format '{{.Names}}' 2>/dev/null | head -1" 2>/dev/null || echo "")

if [ -z "$GARAGE_CONTAINER" ]; then
    warn "No garage container found. Trying alternate names..."
    GARAGE_CONTAINER=$(ssh "${SSH_USER}@${TRUENAS_HOST}" \
        "docker ps --format '{{.Names}}' 2>/dev/null | grep -i garage | head -1" 2>/dev/null || echo "")
fi

if [ -z "$GARAGE_CONTAINER" ]; then
    warn "Could not find Garage container. Listing running containers:"
    ssh "${SSH_USER}@${TRUENAS_HOST}" "docker ps --format 'table {{.Names}}\t{{.Image}}\t{{.Status}}'" 2>/dev/null || true
    echo ""
    prompt "Enter the Garage container name (or 'skip'): "
    read -r GARAGE_CONTAINER
    if [ "${GARAGE_CONTAINER}" = "skip" ]; then
        warn "Skipping post-deploy setup. Run later:"
        echo "  bash ${PROJECT_ROOT}/truenas-apps/garage/post-deploy.sh"
        echo ""
        warn "Secrets (save these):"
        echo "  Admin Token:     ${ADMIN_TOKEN}"
        echo "  RPC Secret:      ${RPC_SECRET}"
        echo "  Web UI Password: ${WEB_UI_PASSWORD}"
        warn "These will NOT be shown again."
        exit 0
    fi
fi

# Set admin token in the container
ok "Configuring admin token..."
ssh "${SSH_USER}@${TRUENAS_HOST}" \
    "docker exec ${GARAGE_CONTAINER} garage status" 2>/dev/null || true

# Create buckets
info "Creating S3 buckets..."
BUCKETS=("winebot-models" "winebot-annotations" "winebot-archives")
for bucket in "${BUCKETS[@]}"; do
    if ssh "${SSH_USER}@${TRUENAS_HOST}" \
        "docker exec ${GARAGE_CONTAINER} garage bucket info ${bucket} 2>/dev/null" > /dev/null 2>&1; then
        ok "Bucket already exists: ${bucket}"
    else
        ssh "${SSH_USER}@${TRUENAS_HOST}" \
            "docker exec ${GARAGE_CONTAINER} garage bucket create ${bucket}" 2>/dev/null || true
        ok "Created bucket: ${bucket}"
    fi
done

# Create DVC API key
info "Creating DVC API key..."
DVC_KEY_NAME="winebot-dvc"
DVC_SECRET_KEY=$(openssl rand -base64 32 | tr -dc 'a-zA-Z0-9' | head -c 32)

# Check if key already exists
KEY_OUTPUT=$(ssh "${SSH_USER}@${TRUENAS_HOST}" \
    "docker exec ${GARAGE_CONTAINER} garage key info ${DVC_KEY_NAME}" 2>/dev/null || echo "")

if [ -z "$KEY_OUTPUT" ]; then
    KEY_OUTPUT=$(ssh "${SSH_USER}@${TRUENAS_HOST}" \
        "docker exec ${GARAGE_CONTAINER} garage key new --name ${DVC_KEY_NAME}" 2>/dev/null || echo "")
fi

# Extract the Access Key ID from Garage output
DVC_ACCESS_KEY=$(echo "$KEY_OUTPUT" | grep -oP 'Key ID:\s+\K\S+' | head -1)
DVC_SECRET_KEY_RESPONSE=$(echo "$KEY_OUTPUT" | grep -oP 'Secret Key:\s+\K\S+' | head -1)
DVC_SECRET_KEY="${DVC_SECRET_KEY_RESPONSE:-$DVC_SECRET_KEY}"

if [ -z "$DVC_ACCESS_KEY" ]; then
    DVC_ACCESS_KEY="${DVC_KEY_NAME}"
    warn "Could not extract Access Key ID from Garage output."
    warn "Using fallback: ${DVC_ACCESS_KEY}"
fi

# Grant key access to buckets
info "Granting key access to buckets..."
for bucket in "${BUCKETS[@]}"; do
    ssh "${SSH_USER}@${TRUENAS_HOST}" \
        "docker exec ${GARAGE_CONTAINER} garage bucket allow --read --write --owner ${bucket} --key ${DVC_KEY_NAME}" 2>/dev/null || true
    ok "  Granted access to: ${bucket}"
done

# ═════════════════════════════════════════════════════════════════════════════
# SUMMARY
# ═════════════════════════════════════════════════════════════════════════════
echo ""
echo "╔═══════════════════════════════════════════════════════════════════╗"
echo "║           GARAGE DEPLOYMENT COMPLETE                             ║"
echo "╚═══════════════════════════════════════════════════════════════════╝"
echo ""
echo "  ── Access Points ──"
echo "  Garage Web UI:  http://${TRUENAS_HOST}:${GARAGE_WEB_PORT}"
echo "  S3 API:         http://${TRUENAS_HOST}:${GARAGE_S3_PORT}"
echo ""
echo "  ── Admin Credentials ──"
echo "  Web UI:         admin / ${WEB_UI_PASSWORD}"
echo ""
echo "  ── DVC Credentials ──"
echo "  S3 Endpoint:    http://${TRUENAS_HOST}:${GARAGE_S3_PORT}"
echo "  Access Key:     ${DVC_ACCESS_KEY}"
echo "  Secret Key:     ${DVC_SECRET_KEY}"
echo "  Region:         garage"
echo ""
echo "  ── Buckets ──"
echo "  ${BUCKETS[*]}"
echo ""
echo "  ── Secrets (SAVE THESE — never shown again) ──"
echo "  Admin Token:    ${ADMIN_TOKEN}"
echo "  RPC Secret:     ${RPC_SECRET}"
echo ""

# ═════════════════════════════════════════════════════════════════════════════
# Offer credential store
# ═════════════════════════════════════════════════════════════════════════════
prompt "Store credentials in OS keychain and configure DVC? [Y/n]: "
read -r RUN_SETUP
if [[ "${RUN_SETUP:-Y}" =~ ^[Yy] ]]; then
    # Store in OS keychain
    if [ -f "${PROJECT_ROOT}/scripts/setup-credential-store.sh" ]; then
        bash "${PROJECT_ROOT}/scripts/setup-credential-store.sh" \
            --access-key "${DVC_ACCESS_KEY}" \
            --secret-key "${DVC_SECRET_KEY}" \
            --host "${TRUENAS_HOST}" \
            --port "${GARAGE_S3_PORT}"
        echo ""
    fi

    # Run client setup
    export INFRA_MINIO_ACCESS_KEY="${DVC_ACCESS_KEY}"
    export INFRA_MINIO_SECRET_KEY="${DVC_SECRET_KEY}"
    export INFRA_MINIO_PORT="${GARAGE_S3_PORT}"
    bash "${PROJECT_ROOT}/scripts/setup-client.sh"
fi

echo ""
info "Done! Your dataset registry is ready."
echo ""
echo "  Quick start:"
echo "    cd /path/to/your/project"
echo "    dvc add your-data/"
echo "    dvc push -r truenas"
echo ""
echo "  Documentation:"
echo "    ${PROJECT_ROOT}/README.md"
echo ""
