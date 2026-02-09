# Pinned to debian:trixie-slim as of 2026-02-08
ARG BASE_IMAGE=debian@sha256:f6e2cfac5cf956ea044b4bd75e6397b4372ad88fe00908045e9a0d21712ae3ba
ARG VCS_REF=unknown
ARG BUILD_DATE=unknown
ARG SOURCE_REPO="https://github.com/mark-e-deyoung/WineBot"

FROM ${BASE_IMAGE} AS base-runtime
ARG BASE_IMAGE

ENV DEBIAN_FRONTEND=noninteractive

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
        xvfb xauth openbox xdotool wmctrl x11vnc novnc websockify xinput \
        libxcomposite1 libxinerama1 libxrandr2 libxrender1 libxcursor1 libxi6 libxtst6 libxfixes3 libvulkan1 \
        fonts-liberation x11-xserver-utils tint2 \
        python3 python3-pip python3-opencv gdb \
        imagemagick x11-utils procps ffmpeg \
        ca-certificates curl gosu unzip \
    && curl -sL -o /usr/local/bin/winetricks https://raw.githubusercontent.com/Winetricks/winetricks/20250102/src/winetricks \
    && chmod +x /usr/local/bin/winetricks \
    && rm -rf /var/lib/apt/lists/*

RUN mkdir -p /tmp/.X11-unix \
    && chmod 1777 /tmp/.X11-unix

# --- Windows Automation Tools ---
COPY windows-tools /tmp/windows-tools
RUN bash /tmp/windows-tools/download_tools.sh \
    && cp /tmp/windows-tools/wrappers/* /usr/local/bin/ \
    && chmod +x /usr/local/bin/autoit /usr/local/bin/ahk /usr/local/bin/winpy \
    && rm -rf /tmp/windows-tools

# Bootstrap pip for Windows Python
RUN curl -sL -o /tmp/get-pip.py https://bootstrap.pypa.io/get-pip.py \
    && wine /opt/winebot/windows-tools/Python/python.exe /tmp/get-pip.py --no-warn-script-location \
    && wine /opt/winebot/windows-tools/Python/python.exe -m pip install --upgrade pip setuptools wheel \
    && rm /tmp/get-pip.py
# --------------------------------

# Install runtime Python dependencies shared by release-like intents.
COPY requirements-rel.txt /tmp/requirements-rel.txt
RUN pip3 install --break-system-packages --no-cache-dir --ignore-installed -r /tmp/requirements-rel.txt \
    && rm /tmp/requirements-rel.txt

RUN useradd -m -u 1000 -s /bin/bash winebot \
    && mkdir -p /wineprefix /apps /automation /api \
    && chmod 777 /wineprefix \
    && chown -R winebot:winebot /apps /automation /api

ENV WINEPREFIX=/wineprefix \
    DISPLAY=:99 \
    SCREEN=1280x720x24 \
    MODE=headless \
    INIT_PREFIX=1 \
    ENABLE_VNC=0 \
    VNC_PORT=5900 \
    NOVNC_PORT=6080

COPY automation /automation
COPY docker/openbox/ /etc/xdg/openbox/
COPY docker/tint2/tint2rc /etc/xdg/tint2/tint2rc
COPY scripts /scripts
COPY api /api
COPY VERSION /VERSION
COPY docker/entrypoint.sh /entrypoint.sh
RUN chown -R winebot:winebot /automation /scripts /api \
    && find /automation /scripts -name "*.sh" -exec chmod +x {} + \
    && find /automation /scripts -name "*.py" -exec chmod +x {} +
RUN chmod +x /entrypoint.sh

WORKDIR /
EXPOSE 8000

FROM base-runtime AS intent-dev
ARG VCS_REF
ARG BUILD_DATE
ARG SOURCE_REPO
RUN apt-get update && apt-get install -y --no-install-recommends strace lsof nano && rm -rf /var/lib/apt/lists/*
COPY requirements-devtest.txt /tmp/requirements-devtest.txt
RUN pip3 install --break-system-packages --no-cache-dir --ignore-installed -r /tmp/requirements-devtest.txt \
    && rm /tmp/requirements-devtest.txt
COPY tests /tests
RUN chown -R winebot:winebot /tests \
    && find /tests -name "*.sh" -exec chmod +x {} + \
    && find /tests -name "*.py" -exec chmod +x {} +
ENV BUILD_INTENT=dev
LABEL io.winebot.build_intent="dev" \
      org.opencontainers.image.revision="${VCS_REF}" \
      org.opencontainers.image.created="${BUILD_DATE}" \
      org.opencontainers.image.source="${SOURCE_REPO}"
ENTRYPOINT ["/entrypoint.sh"]

FROM base-runtime AS intent-test
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
LABEL io.winebot.build_intent="test" \
      org.opencontainers.image.revision="${VCS_REF}" \
      org.opencontainers.image.created="${BUILD_DATE}" \
      org.opencontainers.image.source="${SOURCE_REPO}"
ENTRYPOINT ["/entrypoint.sh"]

FROM base-runtime AS intent-rel
ARG VCS_REF
ARG BUILD_DATE
ARG SOURCE_REPO
ENV BUILD_INTENT=rel
LABEL io.winebot.build_intent="rel" \
      org.opencontainers.image.revision="${VCS_REF}" \
      org.opencontainers.image.created="${BUILD_DATE}" \
      org.opencontainers.image.source="${SOURCE_REPO}"
ENTRYPOINT ["/entrypoint.sh"]

FROM base-runtime AS intent-rel-runner
ARG VCS_REF
ARG BUILD_DATE
ARG SOURCE_REPO
RUN apt-get update \
    && apt-get purge -y --auto-remove x11vnc novnc websockify \
    && rm -rf /var/lib/apt/lists/*
ENV BUILD_INTENT=rel-runner \
    MODE=headless \
    ENABLE_VNC=0
LABEL io.winebot.build_intent="rel-runner" \
      org.opencontainers.image.revision="${VCS_REF}" \
      org.opencontainers.image.created="${BUILD_DATE}" \
      org.opencontainers.image.source="${SOURCE_REPO}"
ENTRYPOINT ["/entrypoint.sh"]

# Compose and workflows should build target: intent-${BUILD_INTENT}.
# Cache bust: Mon Feb 09 2026
