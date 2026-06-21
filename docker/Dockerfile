# Pinned to digest-based Debian Trixie base published by .github/workflows/base-image.yml.
ARG BASE_IMAGE=ghcr.io/sempersupra/winebot-base:base-2026-05-04
ARG VCS_REF=unknown
ARG BUILD_DATE=unknown
ARG SOURCE_REPO="https://github.com/SemperSupra/WineBot"

# --- Stage 1: Tool Builders (Parallel) ---
FROM debian:trixie-slim AS tool-base
RUN apt-get update && apt-get install -y --no-install-recommends curl unzip ca-certificates && rm -rf /var/lib/apt/lists/*
COPY windows-tools/download_tool.sh /download_tool.sh

FROM tool-base AS builder-autoit
RUN bash /download_tool.sh "AutoIt" \
    "https://www.autoitscript.com/autoit3/files/archive/autoit/autoit-v3.3.18.0.zip" \
    "ceb666a993a9f62621c3a0d4ee602774b2e7f543de1f08ec0380632ee3f89beb" \
    "/opt/winebot/windows-tools/AutoIt" \
    && rm -rf /opt/winebot/windows-tools/AutoIt/Examples \
    && rm -rf /opt/winebot/windows-tools/AutoIt/Extras \
    && find /opt/winebot/windows-tools -name "*.chm" -delete

FROM tool-base AS builder-ahk
RUN bash /download_tool.sh "AutoHotkey" \
    "https://github.com/AutoHotkey/AutoHotkey/releases/download/v1.1.37.02/AutoHotkey_1.1.37.02.zip" \
    "6f3663f7cdd25063c8c8728f5d9b07813ced8780522fd1f124ba539e2854215f" \
    "/opt/winebot/windows-tools/AutoHotkey" \
    && find /opt/winebot/windows-tools -name "*.chm" -delete

FROM tool-base AS builder-python
RUN bash /download_tool.sh "Python" \
    "https://www.python.org/ftp/python/3.13.13/python-3.13.13-embed-amd64.zip" \
    "8766a8775746235e23cf5aee5027ab1060bb981d93110577adcf3508aa0cbd55" \
    "/opt/winebot/windows-tools/Python" \
    && find /opt/winebot/windows-tools -name "*.txt" -delete

FROM tool-base AS builder-winspy
# WinInspect v0.1.1 — UIA-enabled window inspection tool
# Replaces original strobejb/winspy v1.8.4 (no UIA support, 2022 vintage)
RUN bash /download_tool.sh "WinInspect" \
    "https://github.com/SemperSupra/WinInspect/releases/download/v0.1.1/WinInspectPortable-v0.1.1.zip" \
    "6120b204f49636f8d407cc8fbced5ee78402c49fb20c664609ba01fe8d944036" \
    "/opt/winebot/windows-tools/WinSpy" \
    && find /opt/winebot/windows-tools -name "*.txt" -delete

# --- Stage 2: Base System (From pre-built base) ---
FROM ${BASE_IMAGE} AS base-system
ARG BASE_IMAGE
ENV DEBIAN_FRONTEND=noninteractive

# Common Setup (Structure & User) - Ensure winebot user exists with correct UID
RUN id -u winebot >/dev/null 2>&1 || useradd -m -u 1000 -s /bin/bash winebot \
    && mkdir -p /wineprefix /apps /automation /api /opt/winebot \
    && chmod 777 /wineprefix \
    && chown -R winebot:winebot /apps /automation /api /opt/winebot

# Keep base OS packages at patched security levels for release gates.
RUN apt-get update \
    && apt-get install -y --no-install-recommends --only-upgrade \
      imagemagick \
      imagemagick-7-common \
      imagemagick-7.q16 \
      libmagickcore-7.q16-10 \
      libmagickwand-7.q16-10 \
      libngtcp2-16 \
      libpng16-16t64 \
      libssl3t64 \
      libtiff6 \
      libvpx9 \
      openssl \
      openssl-provider-legacy \
      tesseract-ocr \
      tesseract-ocr-eng \
    && apt-get clean \
    && rm -rf /var/lib/apt/lists/*

# --- Stage 2.2: Base Core (Adds project-specific tools) ---
FROM base-system AS base-core
# Copy tools from parallel builders
COPY --from=builder-autoit /opt/winebot/windows-tools /opt/winebot/windows-tools
COPY --from=builder-ahk /opt/winebot/windows-tools /opt/winebot/windows-tools
COPY --from=builder-python /opt/winebot/windows-tools /opt/winebot/windows-tools
COPY --from=builder-winspy /opt/winebot/windows-tools /opt/winebot/windows-tools
COPY windows-tools/wrappers/ /usr/local/bin/
RUN chmod +x /usr/local/bin/autoit /usr/local/bin/ahk /usr/local/bin/winpy

# Install runtime Python dependencies (Linux)
COPY requirements/requirements-rel.txt /tmp/requirements-rel.txt
RUN pip3 install --break-system-packages --no-cache-dir -r /tmp/requirements-rel.txt \
    && rm /tmp/requirements-rel.txt

# --- Stage 2.6: Base Logic (Code Foundation) ---
FROM base-core AS base-logic
# Copy application code
COPY automation /automation
COPY scripts /scripts
COPY api /api
COPY docker/entrypoint.sh /entrypoint.sh

# Optimize caching: Copy frequent changes last
COPY VERSION /VERSION

RUN chown -R winebot:winebot /automation /scripts /api \
    && find /automation /scripts -type f -name "*.sh" -exec chmod +x {} + \
    && find /automation /scripts -type f -name "*.py" -exec chmod +x {} + \
    && chmod +x /entrypoint.sh

ENV WINEPREFIX=/wineprefix \
    DISPLAY=:99 \
    SCREEN=1280x720x24 \
    MODE=headless \
    INIT_PREFIX=1 \
    ENABLE_VNC=0 \
    VNC_PORT=5900 \
    NOVNC_PORT=6080 \
    WINEBOT_COMMAND_TIMEOUT=5

WORKDIR /
EXPOSE 8000

# --- Stage 2.6a: API Hook DLL Builder ---
# Builds IAT-based winebot_hook.dll (single DLL, no system DLL conflicts)
# Also builds per-DLL replacement hooks for advanced use cases
FROM base-system AS hook-dll-builder
RUN apt-get update && apt-get install -y --no-install-recommends \
    gcc-mingw-w64-x86-64 gcc-mingw-w64-i686 \
    && apt-get clean && rm -rf /var/lib/apt/lists/*
COPY automation/core/winebot_hook.c /tmp/
COPY automation/core/comdlg32_hook.c /tmp/
COPY automation/core/user32_hook.c /tmp/
COPY automation/core/shell32_hook.c /tmp/
RUN mkdir -p /opt/winebot/hooks && \
    x86_64-w64-mingw32-gcc -shared -o /opt/winebot/hooks/winebot_hook_64.dll /tmp/winebot_hook.c -nostartfiles -lkernel32 -luser32 -lshell32 -lole32 -lcomdlg32 && \
    i686-w64-mingw32-gcc -shared -o /opt/winebot/hooks/winebot_hook_32.dll /tmp/winebot_hook.c -nostartfiles -lkernel32 -luser32 -lshell32 -lole32 -lcomdlg32 && \
    x86_64-w64-mingw32-gcc -shared -o /opt/winebot/hooks/comdlg32_64.dll /tmp/comdlg32_hook.c -nostartfiles -lkernel32 -luser32 -lmsvcrt && \
    i686-w64-mingw32-gcc -shared -o /opt/winebot/hooks/comdlg32_32.dll /tmp/comdlg32_hook.c -nostartfiles -lkernel32 -luser32 -lmsvcrt && \
    x86_64-w64-mingw32-gcc -shared -o /opt/winebot/hooks/user32_64.dll /tmp/user32_hook.c -nostartfiles -lkernel32 && \
    i686-w64-mingw32-gcc -shared -o /opt/winebot/hooks/user32_32.dll /tmp/user32_hook.c -nostartfiles -lkernel32 && \
    x86_64-w64-mingw32-gcc -shared -o /opt/winebot/hooks/shell32_64.dll /tmp/shell32_hook.c -nostartfiles -lkernel32 -luser32 -lshell32 -lole32 && \
    i686-w64-mingw32-gcc -shared -o /opt/winebot/hooks/shell32_32.dll /tmp/shell32_hook.c -nostartfiles -lkernel32 -luser32 -lshell32 -lole32

# --- Stage 2.7: Base Ready (Standard foundation with prefix) ---
FROM base-logic AS base-ready
# Prefix template is already present in /opt/winebot/prefix-template from the BASE_IMAGE
COPY --from=hook-dll-builder /opt/winebot/hooks /opt/winebot/hooks

# --- Stage 3: Base Interactive ---
FROM base-ready AS base-interactive
RUN apt-get update && apt-get install -y --no-install-recommends \
    openbox x11vnc novnc websockify tint2 x11-xserver-utils \
    && apt-get clean && rm -rf /var/lib/apt/lists/*
COPY docker/openbox/ /etc/xdg/openbox/
COPY docker/tint2/tint2rc /etc/xdg/tint2/tint2rc

# --- Final Intents ---

# SLIM: No pre-warmed prefix, saves 1.4GB. Minimal production-hardened intent.
FROM base-logic AS intent-slim
COPY --from=hook-dll-builder /opt/winebot/hooks /opt/winebot/hooks
ARG VCS_REF
ARG BUILD_DATE
ARG SOURCE_REPO
ENV BUILD_INTENT=slim
# Purge build-time cache and temporary files to further reduce size
RUN rm -rf /root/.cache /tmp/* /var/tmp/*
LABEL io.winebot.version="0.9.7" \
      io.winebot.build_intent="slim" \
      org.opencontainers.image.revision="${VCS_REF}" \
      org.opencontainers.image.created="${BUILD_DATE}" \
      org.opencontainers.image.source="${SOURCE_REPO}"
ENTRYPOINT ["/entrypoint.sh"]

FROM base-ready AS intent-rel-runner
ARG VCS_REF
ARG BUILD_DATE
ARG SOURCE_REPO
ENV BUILD_INTENT=rel-runner
LABEL io.winebot.version="0.9.7" \
      io.winebot.build_intent="rel-runner" \
      org.opencontainers.image.revision="${VCS_REF}" \
      org.opencontainers.image.created="${BUILD_DATE}" \
      org.opencontainers.image.source="${SOURCE_REPO}"
ENTRYPOINT ["/entrypoint.sh"]

FROM base-interactive AS intent-rel
ARG VCS_REF
ARG BUILD_DATE
ARG SOURCE_REPO
ENV BUILD_INTENT=rel
LABEL io.winebot.version="0.9.7" \
      io.winebot.build_intent="rel" \
      org.opencontainers.image.revision="${VCS_REF}" \
      org.opencontainers.image.created="${BUILD_DATE}" \
      org.opencontainers.image.source="${SOURCE_REPO}"
ENTRYPOINT ["/entrypoint.sh"]

FROM base-interactive AS intent-test
ARG VCS_REF
ARG BUILD_DATE
ARG SOURCE_REPO
COPY requirements/requirements-devtest.txt /tmp/requirements-devtest.txt
RUN pip3 install --break-system-packages --no-cache-dir -r /tmp/requirements-devtest.txt \
    && rm /tmp/requirements-devtest.txt
COPY tests /tests
COPY docker/Dockerfile /docker/Dockerfile
COPY compose/docker-compose.yml /compose/docker-compose.yml
RUN chown -R winebot:winebot /tests /docker /compose \
    && find /tests -name "*.sh" -exec chmod +x {} + \
    && find /tests -name "*.py" -exec chmod +x {} +
ENV BUILD_INTENT=test
LABEL io.winebot.version="0.9.7" \
      io.winebot.build_intent="test" \
      org.opencontainers.image.revision="${VCS_REF}" \
      org.opencontainers.image.created="${BUILD_DATE}" \
      org.opencontainers.image.source="${SOURCE_REPO}"
ENTRYPOINT ["/entrypoint.sh"]

FROM intent-test AS intent-dev
ARG VCS_REF
ARG BUILD_DATE
ARG SOURCE_REPO
RUN apt-get update && apt-get install -y --no-install-recommends strace lsof nano && rm -rf /var/lib/apt/lists/*
ENV BUILD_INTENT=dev
LABEL io.winebot.version="0.9.7" \
      io.winebot.build_intent="dev" \
      org.opencontainers.image.revision="${VCS_REF}" \
      org.opencontainers.image.created="${BUILD_DATE}" \
      org.opencontainers.image.source="${SOURCE_REPO}"
ENTRYPOINT ["/entrypoint.sh"]

# Cache bust: Sun Feb 15 2026 14:00:00
