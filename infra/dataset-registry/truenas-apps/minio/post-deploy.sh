#!/usr/bin/env bash
# ── MinIO Post-Deploy: Create buckets, users, and access keys ──────────────
# Run this ONCE on TrueNAS after MinIO is deployed via the TrueNAS App UI.
#
# Usage:
#   ssh truenas.fritz.box "sudo bash -s" < truenas-apps/minio/post-deploy.sh
# ──────────────────────────────────────────────────────────────────────────────

set -euo pipefail

# ── Configuration ────────────────────────────────────────────────────────────
MINIO_API="http://127.0.0.1:9000"
MINIO_ROOT_USER="${MINIO_ROOT_USER:-winebot}"
MINIO_ROOT_PASSWORD="${MINIO_ROOT_PASSWORD:-}"

BUCKETS=(
  "winebot-models"       # Model weights, training data, checkpoints
  "winebot-annotations"  # Label files, evaluation results
  "winebot-archives"     # Old versions, experiment artifacts
)

# ── Colors ───────────────────────────────────────────────────────────────────
RED='\033[0;31m'; GREEN='\033[0;32m'; YELLOW='\033[1;33m'; NC='\033[0m'
info()  { echo -e "${GREEN}[INFO]${NC} $*"; }
error() { echo -e "${RED}[ERROR]${NC} $*"; }

# ── Check MinIO is running ────────────────────────────────────────────────────
if ! curl -sf "${MINIO_API}/minio/health/live" > /dev/null 2>&1; then
    error "MinIO is not running at ${MINIO_API}"
    error "Start the MinIO app in TrueNAS UI first."
    exit 1
fi
info "MinIO is healthy"

# ── Install mc if needed ──────────────────────────────────────────────────────
if ! command -v mc >/dev/null 2>&1; then
    info "Installing MinIO client (mc)..."
    curl -sL -o /usr/local/bin/mc https://dl.min.io/client/mc/release/linux-amd64/mc
    chmod +x /usr/local/bin/mc
fi

# ── Prompt for password if not set ────────────────────────────────────────────
if [ -z "$MINIO_ROOT_PASSWORD" ]; then
    read -r -s -p "Enter MinIO root password: " MINIO_ROOT_PASSWORD
    echo ""
fi

# ── Configure mc alias ────────────────────────────────────────────────────────
info "Configuring MinIO client..."
mc alias set truenas "$MINIO_API" "$MINIO_ROOT_USER" "$MINIO_ROOT_PASSWORD" > /dev/null 2>&1

# ── Create Buckets ────────────────────────────────────────────────────────────
info "Creating buckets..."
for bucket in "${BUCKETS[@]}"; do
    if mc ls "truenas/${bucket}" > /dev/null 2>&1; then
        info "  Bucket '${bucket}' already exists"
    else
        mc mb "truenas/${bucket}" > /dev/null 2>&1
        info "  Created bucket '${bucket}'"
    fi
done

# ── Create DVC User ───────────────────────────────────────────────────────────
DVC_ACCESS_KEY="winebot-dvc"
DVC_SECRET_KEY=$(openssl rand -base64 32 | tr -dc 'a-zA-Z0-9' | head -c 32)

info "Creating DVC user credentials..."

cat > /tmp/minio-dvc-policy.json << 'POLICY'
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

mc admin policy create truenas winebot-user /tmp/minio-dvc-policy.json > /dev/null 2>&1 || true
mc admin user add truenas "$DVC_ACCESS_KEY" "$DVC_SECRET_KEY" > /dev/null 2>&1 || true
mc admin policy set truenas winebot-user user="$DVC_ACCESS_KEY" > /dev/null 2>&1

rm -f /tmp/minio-dvc-policy.json

# ── Summary ────────────────────────────────────────────────────────────────────
echo ""
echo "╔═══════════════════════════════════════════════════════════════════╗"
echo "║           MINIO SETUP COMPLETE                                  ║"
echo "╚═══════════════════════════════════════════════════════════════════╝"
echo ""
echo "  MinIO Console:  http://truenas.fritz.box:9001"
echo "  S3 API:         http://truenas.fritz.box:9000"
echo ""
echo "  Admin User:     ${MINIO_ROOT_USER}"
echo "  Admin Password: ${MINIO_ROOT_PASSWORD}"
echo ""
echo "  ── DVC Credentials (for client machines) ──"
echo ""
echo "  export INFRA_MINIO_ACCESS_KEY=${DVC_ACCESS_KEY}"
echo "  export INFRA_MINIO_SECRET_KEY=${DVC_SECRET_KEY}"
echo ""
echo "  ── DVC Remote Setup (on each client) ──"
echo ""
echo "  dvc remote add truenas s3://winebot-models"
echo "  dvc remote modify truenas endpointurl http://truenas.fritz.box:9000"
echo "  dvc remote modify truenas access_key_id ${DVC_ACCESS_KEY}"
echo "  dvc remote modify truenas --local secret_access_key \"${DVC_SECRET_KEY}\""
echo ""
echo "  ── Quick Test ──"
echo ""
echo "  mc ls truenas/"
echo ""
