#!/bin/bash
# Deploy KV-Ground-8B full model (with vision encoder) as Docker container on TrueNAS GPU 1
# Run on TrueNAS: ssh truenas.fritz.box "sudo bash /tmp/deploy_kv_ground_container.sh"

set -e

MODEL_DIR="/mnt/Storage/models/kv-ground/container"
CONTAINER_NAME="winebot-kv-ground"

echo "=== KV-Ground-8B Container Deployment ==="
echo "Target: GPU 1 (A5000 #1), alongside captioner"

# Create model directory
sudo mkdir -p "$MODEL_DIR"

# Check if we need to download the full model or use existing
if [ ! -f "$MODEL_DIR/model.safetensors" ]; then
    echo "Downloading KV-Ground-8B model..."
    # Use huggingface-cli or git LFS
    sudo apt-get install -y git-lfs 2>/dev/null || true
    sudo git lfs install --skip-repo 2>/dev/null || true

    # Clone with depth 1 to save time
    cd /tmp
    if [ -d "KV-Ground-8B" ]; then
        echo "Repo already cloned, updating..."
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

echo "Model files:"
ls -lh "$MODEL_DIR/" | head -10

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
sudo docker build -t winebot-kv-ground:latest -f /tmp/Dockerfile.kv-ground "$MODEL_DIR/"

# Stop existing container if running
sudo docker rm -f "$CONTAINER_NAME" 2>/dev/null || true

# Run on GPU 1
sudo docker run -d --gpus '"device=1"' --name "$CONTAINER_NAME" \
    -p 8003:8003 \
    -v "$MODEL_DIR:/app" \
    winebot-kv-ground:latest

echo ""
echo "=== KV-Ground-8B Container Deployed ==="
echo "Container: $CONTAINER_NAME (GPU 1)"
echo "Port: 8003"
echo "Check: sudo docker logs $CONTAINER_NAME"
