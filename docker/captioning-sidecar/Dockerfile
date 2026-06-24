# Captioning Sidecar — dedicated Florence-2 / Qwen VL inference server
# Isolated dependency space: no ultralytics, rfdetr, onnxruntime, or tesseract.
# Deploy on any GPU host (TrueNAS A5000, RTX 3090, etc.).
#
# Build (from repo root: context = docker/captioning-sidecar/):
#   docker build -f docker/captioning-sidecar/Dockerfile -t winebot-captioner:latest docker/captioning-sidecar/
#   docker run -d --gpus all --name winebot-captioner -p 8002:8002 \
#     -v /mnt/Storage/models/captioning:/models \
#     -v /mnt/Storage/models/huggingface:/root/.cache/huggingface \
#     -e CAPTIONER_MODEL=microsoft/Florence-2-base \
#     winebot-captioner:latest

FROM nvidia/cuda:12.6.3-runtime-ubuntu24.04

ENV DEBIAN_FRONTEND=noninteractive \
    PYTHONUNBUFFERED=1

# ── System deps ───────────────────────────────────────────────────────────
RUN apt-get update && apt-get install -y --no-install-recommends \
    python3 python3-pip python3-dev \
    libglib2.0-0 \
    && rm -rf /var/lib/apt/lists/*
# opencv-python-headless doesn't need libGL — skip it for smaller image

# ── PyTorch (CUDA 12.6) ───────────────────────────────────────────────────
RUN pip3 install --no-cache-dir --break-system-packages \
    torch torchvision --index-url https://download.pytorch.org/whl/cu126

# ── Vision + inference stack ──────────────────────────────────────────────
RUN pip3 install --no-cache-dir --break-system-packages \
    opencv-python-headless \
    numpy \
    pillow

# ── HuggingFace transformers + Florence-2 ──────────────────────────────────
# Pin transformers version that works with Florence-2's remote code config.
# timm + einops required by Florence-2's modeling code.
RUN pip3 install --no-cache-dir --break-system-packages \
    "transformers>=4.45.0,<4.50.0" \
    accelerate \
    peft \
    bitsandbytes \
    timm \
    einops

# ── FastAPI server ────────────────────────────────────────────────────────
RUN pip3 install --no-cache-dir --break-system-packages \
    fastapi \
    uvicorn

# Florence-2-base is downloaded on first run (via HuggingFace cache mount).
# Pre-download during build isn't practical because Florence-2's dynamic
# modules need a GPU to validate — the download happens transparently
# when the container starts with --gpus and a mounted HF cache.

# ── Copy server ───────────────────────────────────────────────────────────
COPY server.py /server.py

WORKDIR /work
EXPOSE 8002
ENTRYPOINT ["python3", "/server.py"]
CMD ["--serve", "--host", "0.0.0.0", "--port", "8002"]
