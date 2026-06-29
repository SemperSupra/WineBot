#!/usr/bin/env bash
# ── Dataset Registry Client Setup (Linux/macOS/WSL) ─────────────────────────
# Run this on any machine that needs to interact with the dataset registry.
#
# Usage:
#   bash scripts/setup-client.sh
#
# This will:
#   1. Install DVC if not present
#   2. Configure the TrueNAS MinIO remote
#   3. Create a .env file for credentials
#   4. Test the connection
# ──────────────────────────────────────────────────────────────────────────────

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "${SCRIPT_DIR}/.." && pwd)"
ENV_FILE="${PROJECT_ROOT}/.env.registry"

# ── Configuration (override via environment variables) ───────────────────────
TRUENAS_HOST="${INFRA_TRUENAS_HOST:-truenas.fritz.box}"
MINIO_PORT_API="${INFRA_MINIO_PORT:-9000}"
MINIO_BUCKET="${INFRA_MINIO_BUCKET:-winebot-models}"
MINIO_ACCESS_KEY="${INFRA_MINIO_ACCESS_KEY:-}"
MINIO_SECRET_KEY="${INFRA_MINIO_SECRET_KEY:-}"
MINIO_ENDPOINT="http://${TRUENAS_HOST}:${MINIO_PORT_API}"

# ── Colors ───────────────────────────────────────────────────────────────────
RED='\033[0;31m'; GREEN='\033[0;32m'; YELLOW='\033[1;33m'; NC='\033[0m'
info()  { echo -e "${GREEN}[INFO]${NC} $*"; }
warn()  { echo -e "${YELLOW}[WARN]${NC} $*"; }
error() { echo -e "${RED}[ERROR]${NC} $*"; }

# ── Check Prerequisites ──────────────────────────────────────────────────────
info "Checking prerequisites..."

if ! command -v python3 >/dev/null 2>&1; then
    error "Python 3 is required"
    exit 1
fi

# ── Install DVC ──────────────────────────────────────────────────────────────
if command -v dvc >/dev/null 2>&1; then
    info "DVC already installed: $(dvc --version)"
else
    info "Installing DVC..."
    pip install dvc[s3] 2>&1 | tail -5
    info "DVC installed: $(dvc --version)"
fi

# ── Configure Remote ─────────────────────────────────────────────────────────
if [ -n "$MINIO_ACCESS_KEY" ] && [ -n "$MINIO_SECRET_KEY" ]; then
    info "Configuring DVC remote for TrueNAS MinIO..."

    # Check if we're in a DVC repo
    if [ -f "${PROJECT_ROOT}/.dvc/config" ]; then
        cd "$PROJECT_ROOT"
    else
        warn "No DVC repository found at ${PROJECT_ROOT}"
        warn "Run 'dvc init' first, or set up DVC in an existing git repo."
        echo ""
        echo "Quick start:"
        echo "  cd /path/to/your/project"
        echo "  git init && dvc init"
        echo "  bash ${SCRIPT_DIR}/setup-client.sh"
        echo ""
    fi

    # Add or update the truenas remote
    dvc remote add truenas "s3://${MINIO_BUCKET}" 2>/dev/null || \
        dvc remote modify truenas "s3://${MINIO_BUCKET}" 2>/dev/null || true

    dvc remote modify truenas endpointurl "${MINIO_ENDPOINT}" 2>/dev/null || true
    dvc remote modify truenas access_key_id "${MINIO_ACCESS_KEY}" 2>/dev/null || true
    dvc remote modify truenas --local secret_access_key "${MINIO_SECRET_KEY}" 2>/dev/null || true

    info "DVC remote configured!"
    echo ""
    echo "  Remote:  truenas"
    echo "  Bucket:  ${MINIO_BUCKET}"
    echo "  Endpoint: ${MINIO_ENDPOINT}"

    # ── Test Connection ──────────────────────────────────────────────────────
    echo ""
    info "Testing connection to TrueNAS MinIO..."
    if dvc status -r truenas 2>/dev/null; then
        info "Connection successful!"
    else
        # Try a direct S3 API check
        if curl -sf "${MINIO_ENDPOINT}/minio/health/live" > /dev/null 2>&1; then
            info "MinIO is reachable, but no DVC-tracked files yet."
            info "To version your first dataset:"
            echo "    dvc add your-data-directory/"
            echo "    dvc push -r truenas"
        else
            warn "Cannot reach MinIO at ${MINIO_ENDPOINT}"
            warn "Verify:"
            warn "  1. TrueNAS is running and MinIO container is up"
            warn "  2. Hostname '${TRUENAS_HOST}' resolves correctly"
            warn "  3. Port ${MINIO_PORT_API} is not firewalled"
            echo ""
            warn "Quick test:"
            echo "    curl -v ${MINIO_ENDPOINT}/minio/health/live"
        fi
    fi
else
    # ── Credential Prompt ────────────────────────────────────────────────────
    echo ""
    echo "╔═══════════════════════════════════════════════════════════════════╗"
    echo "║           DATASET REGISTRY — CLIENT SETUP                        ║"
    echo "╚═══════════════════════════════════════════════════════════════════╝"
    echo ""
    echo "No credentials found. You can:"
    echo ""
    echo "  1. Set environment variables:"
    echo "       export INFRA_TRUENAS_HOST=truenas.fritz.box"
    echo "       export INFRA_MINIO_ACCESS_KEY=your-access-key"
    echo "       export INFRA_MINIO_SECRET_KEY=your-secret-key"
    echo "       bash setup-client.sh"
    echo ""
    echo "  2. Or copy .env.registry.example to .env.registry and fill in values"
    echo "     (see below for the required format)"
    echo ""

    # Generate example env file
    cat > "${ENV_FILE}.example" << 'ENVEOF'
# ── Dataset Registry Credentials ────────────────────────────────────────────
# Copy this to .env.registry and fill in your values.
# Source: infra/dataset-registry/scripts/deploy-truenas.sh (run on TrueNAS first)

INFRA_TRUENAS_HOST=truenas.fritz.box
INFRA_MINIO_PORT=9000
INFRA_MINIO_BUCKET=winebot-models
INFRA_MINIO_ACCESS_KEY=winebot-dvc
INFRA_MINIO_SECRET_KEY=replace-with-actual-secret
ENVEOF

    echo "  Created: ${ENV_FILE}.example"
    echo ""
    echo "  Then run:"
    echo "    cp ${ENV_FILE}.example ${ENV_FILE}"
    echo "    # Edit ${ENV_FILE} with your credentials"
    echo "    set -a; source ${ENV_FILE}; set +a"
    echo "    bash ${SCRIPT_DIR}/setup-client.sh"
    echo ""
fi
