# Disposable WineBot/OpenTTD software graphics layer; no production promotion.
ARG BASE_IMAGE=winebot:openttd-rdte
FROM ${BASE_IMAGE}
USER root
ENV DEBIAN_FRONTEND=noninteractive
RUN apt-get update && apt-get install -y --no-install-recommends \
    libgl1 libgl1-mesa-dri libglx-mesa0 mesa-vulkan-drivers mesa-utils \
    && rm -rf /var/lib/apt/lists/*
ENV LIBGL_ALWAYS_SOFTWARE=1 GALLIUM_DRIVER=llvmpipe LP_NUM_THREADS=4
LABEL io.winebot.experimental.openttd_rdte="not-for-release"
