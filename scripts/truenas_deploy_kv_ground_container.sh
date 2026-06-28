#!/bin/bash
# Deploy KV-Ground-8B full model (with vision encoder) as Docker container on TrueNAS GPU 1
# Run on TrueNAS: ssh truenas.fritz.box "sudo bash /tmp/deploy_kv_ground_container.sh"

set -e
source "$(dirname "$0")/logging_utils.sh"

MODEL_DIR="/mnt/Storage/models/kv-ground/container"
CONTAINER_NAME="winebot-kv-ground"

log_start "KV-Ground-8B container deploy (GPU 1)"
log_step "target" "GPU 1 (A5000 #1), alongside captioner"

# Create model directory
sudo mkdir -p "$MODEL_DIR"

# Check if we need to download the full model or use existing
if [ ! -f "$MODEL_DIR/model.safetensors" ]; then
    log_step "download" "Downloading KV-Ground-8B model..."
    # Use huggingface-cli or git LFS
    sudo apt-get install -y git-lfs 2>/dev/null || true
    sudo git lfs install --skip-repo 2>/dev/null || true

    # Clone with depth 1 to save time
    cd /tmp
    if [ -d "KV-Ground-8B" ]; then
        log_step "download" "Repo already cloned, updating..."
        cd KV-Ground-8B && sudo git pull
    else
        sudo GIT_LFS_SKIP_SMUDGE=1 git clone --depth 1 \
            https://huggingface.co/vocaela/KV-Ground-8B-BaseGuiOwl1.5-0315 KV-Ground-8B
        cd KV-Ground-8B
        # Pull the actual weight files via LFS
        sudo git lfs pull --include="model.safetensors"
    fi
    sudo cp -r /tmp/KV-Ground-8B/* "$MODEL_DIR/"
fi

log_step "files" "Model directory contents:"
ls -lh "$MODEL_DIR/" | head -10 | while read -r line; do log_step "ls" "$line"; done

# Build and run container
cat > /tmp/Dockerfile.kv-ground << 'DOCKERFILE'
FROM pytorch/pytorch:2.5.1-cuda12.4-cudnn9-runtime

RUN apt-get update && apt-get install -y git && rm -rf /var/lib/apt/lists/*
RUN pip install --no-cache-dir transformers>=4.45 accelerate bitsandbytes sentencepiece pillow fastapi uvicorn

WORKDIR /app
COPY . /app/

EXPOSE 8003

CMD ["python3", "-c", "from transformers import AutoModel, AutoProcessor; import torch; m = AutoModel.from_pretrained('/app', torch_dtype=torch.float16, device_map='cuda:0'); print('Model loaded')"]
DOCKERFILE

# Build image on TrueNAS
log_step "build" "Building Docker image..."
sudo docker build -t winebot-kv-ground:latest -f /tmp/Dockerfile.kv-ground "$MODEL_DIR/"

# Stop existing container if running
sudo docker rm -f "$CONTAINER_NAME" 2>/dev/null || true

# Run on GPU 1
log_step "run" "Starting container $CONTAINER_NAME on GPU 1..."
sudo docker run -d --gpus '"device=1"' --name "$CONTAINER_NAME" \
    -p 8003:8003 \
    -v "$MODEL_DIR:/app" \
    winebot-kv-ground:latest

log_complete "KV-Ground-8B container deployed (GPU 1, port 8003)"
log_step "check" "sudo docker logs $CONTAINER_NAME"
