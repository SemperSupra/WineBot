# Opt-in synthetic research-only CPU OpenGL layer, not a product image.
ARG BASE_IMAGE=winebot:stk15-rdte
FROM ${BASE_IMAGE}
USER root
ENV DEBIAN_FRONTEND=noninteractive
RUN apt-get update && apt-get install -y --no-install-recommends \
    libgl1 libgl1-mesa-dri libglx-mesa0 mesa-utils \
    && rm -rf /var/lib/apt/lists/*
ENV LIBGL_ALWAYS_SOFTWARE=1 GALLIUM_DRIVER=llvmpipe LP_NUM_THREADS=4
LABEL io.winebot.experimental.stk15_cpu_rdte="not-for-release"
