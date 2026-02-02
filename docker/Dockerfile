FROM debian:trixie-slim

ENV DEBIAN_FRONTEND=noninteractive

RUN if [ -f /etc/apt/sources.list ]; then \
        sed -i 's/ main/ main contrib non-free non-free-firmware/' /etc/apt/sources.list; \
    elif [ -f /etc/apt/sources.list.d/debian.sources ]; then \
        sed -i 's/Components: main/Components: main contrib non-free non-free-firmware/' /etc/apt/sources.list.d/debian.sources; \
    fi \
    && dpkg --add-architecture i386 \
    && apt-get update \
    && apt-get -y upgrade \
    && apt-get install -y --no-install-recommends \
        wine wine64 wine32 winetricks cabextract \
        xvfb xauth openbox xdotool wmctrl x11vnc novnc websockify \
        python3 python3-pip python3-opencv gdb \
        imagemagick x11-utils procps \
        ca-certificates curl gosu unzip \
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

# Install Python dependencies for API and Testing
RUN pip3 install --break-system-packages --no-cache-dir --ignore-installed \
    fastapi uvicorn python-multipart httpx pytest

RUN useradd -m -u 1000 -s /bin/bash winebot \
    && mkdir -p /wineprefix /apps /automation /api \
    && chmod 777 /wineprefix \
    && chown -R winebot:winebot /apps /automation /api

ENV WINEPREFIX=/wineprefix \
    DISPLAY=:99 \
    SCREEN=1920x1080x24 \
    MODE=headless \
    INIT_PREFIX=1 \
    ENABLE_VNC=0 \
    VNC_PORT=5900 \
    NOVNC_PORT=6080

COPY automation /automation
COPY scripts /scripts
COPY api /api
COPY tests /tests
COPY docker/entrypoint.sh /entrypoint.sh
RUN chown -R winebot:winebot /automation /scripts /api /tests \
    && chmod +x /automation/*.sh /automation/*.py \
    && chmod +x /scripts/*.sh \
    && chmod +x /tests/*.sh
RUN chmod +x /entrypoint.sh

WORKDIR /
EXPOSE 8000
ENTRYPOINT ["/entrypoint.sh"]
