#!/usr/bin/env bash
# ── Deploy MinIO + DVC Remote on TrueNAS ──────────────────────────────────
# Run this ONCE on TrueNAS to set up the dataset registry infrastructure.
#
# Usage:
#   ssh truenas.fritz.box "sudo bash -s" < deploy-truenas.sh
#   # OR copy it over first:
#   scp infra/dataset-registry/scripts/deploy-truenas.sh truenas.fritz.box:/tmp/
#   ssh truenas.fritz.box "sudo bash /tmp/deploy-truenas.sh"
#
# This will:
#   1. Deploy MinIO as a Docker container with persistent storage
#   2. Create the winebot-models bucket
#   3. Generate access credentials
#   4. Print the configuration for client machines
# ──────────────────────────────────────────────────────────────────────────────

set -euo pipefail

# ── Configuration ────────────────────────────────────────────────────────────
MINIO_CONTAINER_NAME="minio"
MINIO_DATA_DIR="/mnt/Storage/models/minio"
MINIO_PORT_API=9000      # S3-compatible API
MINIO_PORT_CONSOLE=9001  # Web UI
MINIO_ROOT_USER="winebot"

# Generate a strong random password if not provided
MINIO_ROOT_PASSWORD="${MINIO_ROOT_PASSWORD:-$(openssl rand -base64 32 | tr -dc 'a-zA-Z0-9' | head -c 32)}"

# Buckets to create
BUCKETS=(
  "winebot-models"       # Model weights, training data, checkpoints
  "winebot-annotations"  # Label files, evaluation results
  "winebot-archives"     # Old dataset versions, experiment artifacts
)

# ── Colors ───────────────────────────────────────────────────────────────────
RED='\033[0;31m'; GREEN='\033[0;32m'; YELLOW='\033[1;33m'; NC='\033[0m'
info()  { echo -e "${GREEN}[INFO]${NC} $*"; }
warn()  { echo -e "${YELLOW}[WARN]${NC} $*"; }
error() { echo -e "${RED}[ERROR]${NC} $*"; }

# ── Prerequisites ────────────────────────────────────────────────────────────
info "Checking prerequisites..."
command -v docker >/dev/null 2>&1 || { error "Docker not found"; exit 1; }
command -v openssl >/dev/null 2>&1 || { warn "openssl not found, using fixed password"; MINIO_ROOT_PASSWORD="ChangeMe123!"; }

# Create data directory if it doesn't exist
if [ ! -d "$MINIO_DATA_DIR" ]; then
    info "Creating MinIO data directory at $MINIO_DATA_DIR..."
    mkdir -p "$MINIO_DATA_DIR"
else
    info "MinIO data directory already exists at $MINIO_DATA_DIR"
fi

# ── Deploy MinIO Container ───────────────────────────────────────────────────
info "Stopping any existing MinIO container..."
docker stop "$MINIO_CONTAINER_NAME" 2>/dev/null || true
docker rm "$MINIO_CONTAINER_NAME" 2>/dev/null || true

info "Starting MinIO container..."
docker run -d \
    --name "$MINIO_CONTAINER_NAME" \
    --restart unless-stopped \
    -p ${MINIO_PORT_API}:9000 \
    -p ${MINIO_PORT_CONSOLE}:9001 \
    -v "$MINIO_DATA_DIR:/data" \
    -e "MINIO_ROOT_USER=${MINIO_ROOT_USER}" \
    -e "MINIO_ROOT_PASSWORD=${MINIO_ROOT_PASSWORD}" \
    minio/minio server /data --console-address ":9001"

info "Waiting for MinIO to become ready..."
for i in $(seq 1 30); do
    if curl -sf "http://127.0.0.1:${MINIO_PORT_API}/minio/health/live" > /dev/null 2>&1; then
        info "MinIO is ready!"
        break
    fi
    sleep 2
done

# ── Install MinIO Client (mc) ────────────────────────────────────────────────
info "Installing MinIO client (mc)..."
if command -v mc >/dev/null 2>&1; then
    info "mc already installed"
else
    curl -sL -o /usr/local/bin/mc https://dl.min.io/client/mc/release/linux-amd64/mc
    chmod +x /usr/local/bin/mc
    info "mc installed"
fi

# ── Configure mc and Create Buckets ──────────────────────────────────────────
info "Configuring MinIO client..."
mc alias set truenas "http://127.0.0.1:${MINIO_PORT_API}" "$MINIO_ROOT_USER" "$MINIO_ROOT_PASSWORD" > /dev/null 2>&1

for bucket in "${BUCKETS[@]}"; do
    if mc ls truenas/"$bucket" > /dev/null 2>&1; then
        info "Bucket '$bucket' already exists"
    else
        mc mb truenas/"$bucket" > /dev/null 2>&1
        info "Created bucket '$bucket'"
    fi
done

# Make winebot-models publicly readable (for DVC pull without auth)
mc anonymous set download truenas/winebot-models > /dev/null 2>&1 || true

# ── Create dedicated access key for DVC ──────────────────────────────────────
info "Generating DVC access credentials..."
ACCESS_KEY="winebot-dvc"
SECRET_KEY=$(openssl rand -base64 32 | tr -dc 'a-zA-Z0-9' | head -c 32 2>/dev/null || echo "dvc-secret-key-change-me")

# Create user policy for bucket access
cat > /tmp/minio-user-policy.json << 'POLICY'
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

mc admin policy create truenas winebot-user /tmp/minio-user-policy.json > /dev/null 2>&1 || true
mc admin user add truenas "$ACCESS_KEY" "$SECRET_KEY" > /dev/null 2>&1 || true
mc admin policy set truenas winebot-user user="$ACCESS_KEY" > /dev/null 2>&1

rm -f /tmp/minio-user-policy.json

# ── Summary ──────────────────────────────────────────────────────────────────
HOSTNAME=$(hostname -f 2>/dev/null || hostname)
IP=$(curl -s http://checkip.amazonaws.com 2>/dev/null || echo "localhost")

echo ""
echo "╔═══════════════════════════════════════════════════════════════════╗"
echo "║           DATASET REGISTRY — DEPLOYMENT COMPLETE                ║"
echo "╚═══════════════════════════════════════════════════════════════════╝"
echo ""
echo "  MinIO Console:  http://${HOSTNAME}:${MINIO_PORT_CONSOLE}"
echo "  S3 API:         http://${HOSTNAME}:${MINIO_PORT_API}"
echo ""
echo "  Root User:      ${MINIO_ROOT_USER}"
echo "  Root Password:  ${MINIO_ROOT_PASSWORD}"
echo ""
echo "  DVC Access Key: ${ACCESS_KEY}"
echo "  DVC Secret Key: ${SECRET_KEY}"
echo ""
echo "  Buckets:"
for bucket in "${BUCKETS[@]}"; do
    echo "    s3://${bucket}/"
done
echo ""
echo "  ── Save these credentials securely ──"
echo "  Store the root password and DVC secret key in your password manager."
echo "  The DVC remote config command for client machines:"
echo ""
echo "  dvc remote add truenas s3://winebot-models"
echo "  dvc remote modify truenas endpointurl http://${HOSTNAME}:${MINIO_PORT_API}"
echo "  dvc remote modify truenas access_key_id ${ACCESS_KEY}"
echo "  dvc remote modify truenas --local secret_access_key \"${SECRET_KEY}\""
echo ""
echo "  MinIO Console:  http://${HOSTNAME}:${MINIO_PORT_CONSOLE}"
echo "    Login: ${MINIO_ROOT_USER} / ${MINIO_ROOT_PASSWORD}"
echo ""
echo "  Setup script for client machines:"
echo "    infra/dataset-registry/scripts/setup-client.sh"
echo ""
