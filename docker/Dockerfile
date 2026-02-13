# Pinned to debian:trixie-slim as of 2026-02-08
ARG BASE_IMAGE=debian@sha256:f6e2cfac5cf956ea044b4bd75e6397b4372ad88fe00908045e9a0d21712ae3ba
ARG VCS_REF=unknown
ARG BUILD_DATE=unknown
ARG SOURCE_REPO="https://github.com/mark-e-deyoung/WineBot"

# --- Stage 1: Tool Builder ---
FROM debian:trixie-slim AS tools-builder
RUN apt-get update && apt-get install -y --no-install-recommends \
    curl unzip ca-certificates \
    && rm -rf /var/lib/apt/lists/*
COPY windows-tools /tmp/windows-tools
RUN bash /tmp/windows-tools/download_tools.sh \
    && rm -rf /opt/winebot/windows-tools/AutoIt/Examples \
    && rm -rf /opt/winebot/windows-tools/AutoIt/Extras \
    && find /opt/winebot/windows-tools -name "*.chm" -delete \
    && find /opt/winebot/windows-tools -name "*.txt" -delete

# --- Stage 2: Base Runtime (The stable system layer) ---
FROM ${BASE_IMAGE} AS base-runtime
ARG BASE_IMAGE
ENV DEBIAN_FRONTEND=noninteractive

# Combine all system dependencies into a single stable layer
RUN if [ -f /etc/apt/sources.list ]; then \
        sed -i 's/ main/ main contrib non-free non-free-firmware/' /etc/apt/sources.list; \
    elif [ -f /etc/apt/sources.d/debian.sources ]; then \
        sed -i 's/Components: main/Components: main contrib non-free non-free-firmware/' /etc/apt/sources.d/debian.sources; \
    fi \
    && dpkg --add-architecture i386 \
    && apt-get update \
    && apt-get -y upgrade \
    && apt-get install -y --no-install-recommends \
        wine wine64 wine32 cabextract \
        xvfb xauth xdotool wmctrl xinput \
        libxcomposite1 libxinerama1 libxrandr2 libxrender1 libxcursor1 libxi6 libxtst6 libxfixes3 libvulkan1 \
        fonts-liberation \
        imagemagick x11-utils procps ffmpeg \
        ca-certificates curl gosu unzip \
        python3 python3-pip gdb \
    && curl -sL -o /usr/local/bin/winetricks https://raw.githubusercontent.com/Winetricks/winetricks/20250102/src/winetricks \
    && chmod +x /usr/local/bin/winetricks \
    && apt-get clean && rm -rf /var/lib/apt/lists/*

RUN mkdir -p /tmp/.X11-unix && chmod 1777 /tmp/.X11-unix

# Common Setup (Structure & User)
RUN id -u winebot >/dev/null 2>&1 || useradd -m -u 1000 -s /bin/bash winebot \
    && mkdir -p /wineprefix /apps /automation /api /opt/winebot \
    && chmod 777 /wineprefix \
    && chown -R winebot:winebot /apps /automation /api /opt/winebot

# --- Stage 2.2: Base Core (Adds project-specific tools) ---
FROM base-runtime AS base-core
# Copy tools from builder
COPY --from=tools-builder /opt/winebot/windows-tools /opt/winebot/windows-tools
COPY windows-tools/wrappers/ /usr/local/bin/
RUN chmod +x /usr/local/bin/autoit /usr/local/bin/ahk /usr/local/bin/winpy

# Bootstrap pip for Windows Python (using a temp prefix to avoid image bloat)
RUN mkdir -p /tmp/wine-bootstrap \
    && curl -sL -o /tmp/get-pip.py https://bootstrap.pypa.io/get-pip.py \
    && WINEPREFIX=/tmp/wine-bootstrap wine /opt/winebot/windows-tools/Python/python.exe /tmp/get-pip.py --no-warn-script-location \
    && WINEPREFIX=/tmp/wine-bootstrap wine /opt/winebot/windows-tools/Python/python.exe -m pip install --upgrade pip setuptools wheel \
    && rm -rf /tmp/get-pip.py /tmp/wine-bootstrap

# Install runtime Python dependencies (Linux)
COPY requirements-rel.txt /tmp/requirements-rel.txt
RUN pip3 install --break-system-packages --no-cache-dir --ignore-installed -r /tmp/requirements-rel.txt \
    && rm /tmp/requirements-rel.txt

# --- Stage 2.5: Prefix Warm-up ---
FROM base-core AS prefix-warmer
USER winebot
ENV WINEPREFIX=/opt/winebot/prefix-template
COPY --chown=winebot:winebot scripts/install-theme.sh /scripts/install-theme.sh
RUN mkdir -p /opt/winebot/prefix-template \
    && Xvfb :95 -screen 0 1280x720x24 >/dev/null 2>&1 & XVFB_PID=$! \
    && export DISPLAY=:95 \
    && wineboot -u \
    && wineserver -w \
    && /scripts/install-theme.sh \
    && wine reg add "HKEY_CURRENT_USER\Software\Wine\X11 Driver" /v UseXInput2 /t REG_SZ /d "N" /f \
    && wine reg add "HKEY_CURRENT_USER\Software\Wine\X11 Driver" /v Managed /t REG_SZ /d "Y" /f \
    && wineserver -k \
    && wineserver -w \
    && kill $XVFB_PID || true \
    && rm -rf /tmp/.X95-lock /tmp/.X11-unix/X95

# --- Stage 2.6: Base Ready (The fully-initialized foundation) ---
FROM base-core AS base-ready
# Copy the template first
COPY --from=prefix-warmer --chown=winebot:winebot /opt/winebot/prefix-template /opt/winebot/prefix-template

# Copy application code
COPY automation /automation
COPY scripts /scripts
COPY api /api
COPY VERSION /VERSION
COPY docker/entrypoint.sh /entrypoint.sh

RUN chown -R winebot:winebot /automation /scripts /api \
    && find /automation /scripts -name "*.sh" -exec chmod +x {} + \
    && find /automation /scripts -name "*.py" -exec chmod +x {} + \
    && chmod +x /entrypoint.sh

ENV WINEPREFIX=/wineprefix \
    DISPLAY=:99 \
    SCREEN=1280x720x24 \
    MODE=headless \
    INIT_PREFIX=1 \
    ENABLE_VNC=0 \
    VNC_PORT=5900 \
    NOVNC_PORT=6080

WORKDIR /
EXPOSE 8000

# --- Stage 3: Base Interactive ---
FROM base-ready AS base-interactive
RUN apt-get update && apt-get install -y --no-install-recommends \
    openbox x11vnc novnc websockify tint2 x11-xserver-utils \
    && apt-get clean && rm -rf /var/lib/apt/lists/*
COPY docker/openbox/ /etc/xdg/openbox/
COPY docker/tint2/tint2rc /etc/xdg/tint2/tint2rc

# --- Final Intents ---

FROM base-ready AS intent-rel-runner
ARG VCS_REF
ARG BUILD_DATE
ARG SOURCE_REPO
ENV BUILD_INTENT=rel-runner
LABEL io.winebot.version="0.9.3" \
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
LABEL io.winebot.version="0.9.3" \
      io.winebot.build_intent="rel" \
      org.opencontainers.image.revision="${VCS_REF}" \
      org.opencontainers.image.created="${BUILD_DATE}" \
      org.opencontainers.image.source="${SOURCE_REPO}"
ENTRYPOINT ["/entrypoint.sh"]

FROM base-interactive AS intent-test
ARG VCS_REF
ARG BUILD_DATE
ARG SOURCE_REPO
COPY requirements-devtest.txt /tmp/requirements-devtest.txt
RUN pip3 install --break-system-packages --no-cache-dir --ignore-installed -r /tmp/requirements-devtest.txt \
    && rm /tmp/requirements-devtest.txt
COPY tests /tests
RUN chown -R winebot:winebot /tests \
    && find /tests -name "*.sh" -exec chmod +x {} + \
    && find /tests -name "*.py" -exec chmod +x {} +
ENV BUILD_INTENT=test
LABEL io.winebot.version="0.9.3" \
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
LABEL io.winebot.version="0.9.3" \
      io.winebot.build_intent="dev" \
      org.opencontainers.image.revision="${VCS_REF}" \
      org.opencontainers.image.created="${BUILD_DATE}" \
      org.opencontainers.image.source="${SOURCE_REPO}"
ENTRYPOINT ["/entrypoint.sh"]

# Cache bust: Fri Feb 13 2026
