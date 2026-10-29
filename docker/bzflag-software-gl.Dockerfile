# Disposable RDTE-only software renderer; never used in WineBot releases.
ARG BASE_IMAGE=winebot:bzflag-rdte
FROM ${BASE_IMAGE}
USER root
ENV DEBIAN_FRONTEND=noninteractive
RUN apt-get update && apt-get install -y --no-install-recommends \
    libgl1 libgl1-mesa-dri libglx-mesa0 mesa-utils \
    libgl1:i386 libgl1-mesa-dri:i386 libglx-mesa0:i386 \
    && rm -rf /var/lib/apt/lists/*
ENV LIBGL_ALWAYS_SOFTWARE=1 GALLIUM_DRIVER=llvmpipe LP_NUM_THREADS=4
LABEL io.winebot.experimental.bzflag_cpu_rdte="not-for-release"
