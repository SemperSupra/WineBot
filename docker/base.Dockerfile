# WineBot Base Image
# Contains: Debian Trixie + Wine 10.0 + Xvfb + Python + Pre-warmed Prefix
ARG BASE_IMAGE=debian:trixie-slim

FROM ${BASE_IMAGE} AS base-system
ENV DEBIAN_FRONTEND=noninteractive

# 1. System Dependencies (Wine, X11, Python)
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
    && curl -sL -o /usr/local/bin/winetricks https://raw.githubusercontent.com/Winetricks/winetricks/20260125/src/winetricks \
    && chmod +x /usr/local/bin/winetricks \
    && apt-get clean && rm -rf /var/lib/apt/lists/*

RUN mkdir -p /tmp/.X11-unix && chmod 1777 /tmp/.X11-unix

# 2. User Setup
RUN id -u winebot >/dev/null 2>&1 || useradd -m -u 1000 -s /bin/bash winebot \
    && mkdir -p /wineprefix /apps /automation /api /opt/winebot \
    && chmod 777 /wineprefix \
    && chown -R winebot:winebot /apps /automation /api /opt/winebot

# 3. Prefix Warming
# We do this here so it's cached in the base image registry
FROM base-system AS prefix-warmer
USER winebot
ENV WINEPREFIX=/opt/winebot/prefix-template
COPY --chown=winebot:winebot scripts/setup/install-theme.sh /scripts/setup/install-theme.sh
RUN chmod +x /scripts/setup/install-theme.sh \
    && mkdir -p /opt/winebot/prefix-template \
    && Xvfb :95 -screen 0 1280x720x24 >/dev/null 2>&1 & XVFB_PID=$! \
    && export DISPLAY=:95 \
    && wineboot -u \
    && wineserver -w \
    && /scripts/setup/install-theme.sh \
    && wineserver -w \
    && wine reg add "HKEY_CURRENT_USER\Software\Wine\X11 Driver" /v UseXInput2 /t REG_SZ /d "N" /f \
    && wine reg add "HKEY_CURRENT_USER\Software\Wine\X11 Driver" /v Managed /t REG_SZ /d "Y" /f \
    && wineserver -k \
    && wineserver -w \
    && kill $XVFB_PID || true \
    && rm -rf /tmp/.X95-lock /tmp/.X11-unix/X95

# 4. Final Base Layer
FROM base-system AS final
COPY --from=prefix-warmer --chown=winebot:winebot /opt/winebot/prefix-template /opt/winebot/prefix-template
