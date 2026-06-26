#!/bin/bash
# Deploy KV-Ground-8B as 4-bit vision container on TrueNAS GPU 0
# Uses huggingface_hub (not git LFS) + bitsandbytes 4-bit quantization
# ~5GB VRAM, fits alongside Ollama on A5000 (24GB)
set -e

CONTAINER_NAME="winebot-kv-ground"
MODEL_ID="vocaela/KV-Ground-8B-BaseGuiOwl1.5-0315"
PORT=8004

echo "=== KV-Ground-8B 4-bit Container Deployment ==="
echo "Target: GPU 0 (A5000 #0), alongside Ollama"

# Stop existing container
sudo docker rm -f "$CONTAINER_NAME" 2>/dev/null || true

# Build and run container
cat > /tmp/Dockerfile.kv-ground-4bit << 'DOCKERFILE'
FROM pytorch/pytorch:2.5.1-cuda12.4-cudnn9-runtime

RUN apt-get update && apt-get install -y git && rm -rf /var/lib/apt/lists/*

# Install deps
RUN pip install --no-cache-dir \
    transformers>=4.45 \
    accelerate \
    bitsandbytes \
    sentencepiece \
    pillow \
    fastapi \
    uvicorn \
    huggingface_hub \
    einops

WORKDIR /app

# Server script
COPY server.py /app/server.py

EXPOSE 8004

CMD ["python3", "/app/server.py"]
DOCKERFILE

cat > /tmp/server.py << 'SERVER'
#!/usr/bin/env python3
"""KV-Ground-8B 4-bit vision API server."""
import os, torch, json, time
from PIL import Image
from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse
import huggingface_hub

app = FastAPI()
model = None
processor = None
MODEL_ID = "vocaela/KV-Ground-8B-BaseGuiOwl1.5-0315"
DEVICE = "cuda:0"

class ModelContainer:
    def __init__(self):
        self.model = None
        self.processor = None

container = ModelContainer()

def load_model():
    if container.model is not None:
        return

    print(f"Loading KV-Ground-8B in 4-bit on {DEVICE}...")

    from transformers import AutoModelForCausalLM, AutoProcessor

    # Load processor
    processor = AutoProcessor.from_pretrained(
        MODEL_ID, trust_remote_code=True
    )
    container.processor = processor

    # Load model in 4-bit (NF4) — downloads safetensors on first run (~16GB)
    # After caching, subsequent loads use the cached files
    print("Downloading KV-Ground-8B (first run: ~16GB, then cached)...")
    model = AutoModelForCausalLM.from_pretrained(
        MODEL_ID,
        trust_remote_code=True,
        torch_dtype=torch.float16,
        device_map="auto",
        load_in_4bit=True,
        bnb_4bit_compute_dtype=torch.float16,
        bnb_4bit_quant_type="nf4",
    )
    container.model = model
    print(f"Model loaded. VRAM: {torch.cuda.memory_allocated()/1024**3:.1f}GB")

@app.post("/ground")
async def ground(request: Request):
    """Ground a text query on an image.

    Request: {"image_path": "/path/to/img.png", "query": "the save button"}
    Returns: {"bbox": [x1, y1, x2, y2], "confidence": 0.95, "label": "save button"}
    """
    load_model()

    data = await request.json()
    image_path = data.get("image_path", "")
    query = data.get("query", "")

    if not image_path or not os.path.exists(image_path):
        return JSONResponse({"error": "image_path required"}, status_code=400)
    if not query:
        return JSONResponse({"error": "query required"}, status_code=400)

    image = Image.open(image_path).convert("RGB")

    t0 = time.time()
    inputs = container.processor(
        text=query, images=image, return_tensors="pt"
    ).to(DEVICE)

    with torch.no_grad():
        outputs = container.model.generate(
            **inputs, max_new_tokens=128, do_sample=False
        )

    result = container.processor.decode(outputs[0], skip_special_tokens=True)
    elapsed = (time.time() - t0) * 1000

    return JSONResponse({
        "query": query,
        "result": result,
        "time_ms": round(elapsed, 1),
        "model": "KV-Ground-8B-4bit",
    })

@app.get("/health")
async def health():
    return {"status": "healthy", "model": "KV-Ground-8B-4bit", "loaded": container.model is not None}

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8004)
SERVER

# Build
sudo docker build -t winebot-kv-ground:4bit -f /tmp/Dockerfile.kv-ground-4bit /tmp/

# Run on GPU 0
sudo docker run -d --gpus '"device=0"' --name "$CONTAINER_NAME" \
    -p $PORT:$PORT \
    -v /mnt/Storage:/mnt/Storage \
    winebot-kv-ground:4bit

echo ""
echo "=== KV-Ground-8B 4-bit Deployed ==="
echo "Container: $CONTAINER_NAME (GPU 0)"
echo "Port: $PORT"
echo "Check: sudo docker logs -f $CONTAINER_NAME"
echo "Test: curl http://truenas.fritz.box:$PORT/health"
