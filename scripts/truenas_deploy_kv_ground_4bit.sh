#!/bin/bash
# Deploy KV-Ground-8B 4-bit server on TrueNAS GPU 0
# Source repo: github.com/SemperSupra/kv-ground-server
# ~5GB VRAM, fits alongside Ollama on A5000 (24GB)
set -e
source "$(dirname "$0")/logging_utils.sh"

CONTAINER_NAME="winebot-kv-ground"
PORT=8004
REPO="https://github.com/SemperSupra/kv-ground-server.git"
REF="${KV_GROUND_SERVER_REF:-v0.1.0}"

log_start "KV-Ground-8B 4-bit deploy (GPU 0)"
log_step "target" "GPU 0 (A5000 #0), alongside Ollama"
log_step "source" "${REPO}@${REF}"

# Stop existing container
sudo docker rm -f "$CONTAINER_NAME" 2>/dev/null || true

# Build from repo (uses Dockerfile.4bit for quantized inference)
BUILD_DIR=$(mktemp -d)
git clone --depth 1 --branch "$REF" "$REPO" "$BUILD_DIR" 2>&1 | sed 's/^/    /'

log_step "build" "Building 4-bit Docker image..."
sudo docker build -t "kv-ground-server:${REF}" \
    -f "$BUILD_DIR/docker/Dockerfile.4bit" "$BUILD_DIR"

# Run on GPU 0
log_step "run" "Starting $CONTAINER_NAME on GPU 0..."
sudo docker run -d --gpus '"device=0"' --name "$CONTAINER_NAME" \
    -p $PORT:$PORT \
    -v /mnt/Storage:/mnt/Storage \
    "kv-ground-server:${REF}"

rm -rf "$BUILD_DIR"
log_complete "KV-Ground-8B 4-bit deployed (GPU 0, port $PORT)"
log_step "check" "sudo docker logs -f $CONTAINER_NAME"
log_step "test" "curl http://truenas.fritz.box:$PORT/health"
