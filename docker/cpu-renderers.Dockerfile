# Optional RDTE software-rendering layer. Default FROM is a minimal synthetic
# Debian substrate for public $0 CI; for WineBot pass an already-built WineBot image.
ARG BASE_IMAGE=debian:trixie-slim
FROM ${BASE_IMAGE}
USER root
ENV DEBIAN_FRONTEND=noninteractive
RUN apt-get update && apt-get install -y --no-install-recommends \
    python3 xvfb xauth x11-utils mesa-utils libgl1-mesa-dri \
    mesa-vulkan-drivers vulkan-tools libvulkan1 \
    && rm -rf /var/lib/apt/lists/*
COPY scripts/cpu_renderer.py /opt/winebot/cpu_renderer.py
LABEL io.winebot.experimental.cpu_renderers="llvmpipe,lavapipe,swiftshader-external"
