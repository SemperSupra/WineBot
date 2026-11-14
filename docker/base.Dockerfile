# WineBot Base Image
# Contains: digest-pinned Debian Trixie slim + Wine/X11/Python runtime + pre-warmed prefix.
ARG BASE_IMAGE=debian@sha256:cedb1ef40439206b673ee8b33a46a03a0c9fa90bf3732f54704f99cb061d2c5a

FROM ${BASE_IMAGE} AS base-system
ENV DEBIAN_FRONTEND=noninteractive

# 1. Minimal runtime dependencies (Wine, X11 automation, recording, diagnostics).
RUN if [ -f /etc/apt/sources.list ]; then \
        sed -i 's/ main/ main contrib non-free non-free-firmware/' /etc/apt/sources.list; \
    elif [ -f /etc/apt/sources.d/debian.sources ]; then \
        sed -i 's/Components: main/Components: main contrib non-free non-free-firmware/' /etc/apt/sources.d/debian.sources; \
    fi \
    && dpkg --add-architecture i386 \
    && apt-get update \
    && apt-get -y --with-new-pkgs upgrade \
    && apt-get install -y --no-install-recommends \
        cabextract \
        xvfb xauth xdotool wmctrl xinput \
        libxcomposite1 libxinerama1 libxrandr2 libxrender1 libxcursor1 libxi6 libxtst6 libxfixes3 libvulkan1 \
        fonts-liberation \
        imagemagick x11-utils procps ffmpeg \
        ca-certificates curl gnupg gosu unzip \
        python3 python3-pip gdb \
    && apt-get -y --with-new-pkgs upgrade \
    && curl -sL -o /usr/local/bin/winetricks https://raw.githubusercontent.com/Winetricks/winetricks/20260125/src/winetricks \
    && chmod +x /usr/local/bin/winetricks \
    && apt-get clean && rm -rf /var/lib/apt/lists/*

# Wine 11 stable requires the upstream WineHQ packaging track. Do not mix
# Debian Trixie's Wine 10 wrappers with WineHQ's wine-stable packages.
# Pin both the primary signing-key fingerprint and WineHQ's Wine 11.0
# package version; signed-by confines the key to this source alone.
RUN install -d -m 0755 /etc/apt/keyrings \
    && curl -fsSLo /tmp/winehq.key --retry 3 --connect-timeout 10 \
      https://dl.winehq.org/wine-builds/winehq.key \
    && fingerprint="$(gpg --batch --with-colons --show-keys /tmp/winehq.key 2>/dev/null | awk -F: '$1=="fpr" {print $10; exit}')" \
    && if [ "$fingerprint" != "D43F640145369C51D786DDEA76F1A20FF987672F" ]; then \
         echo "WINEHQ_CUSTODY stage=signing_key_mismatch" >&2; exit 1; \
       fi \
    && gpg --batch --yes --dearmor -o /etc/apt/keyrings/winehq-archive.gpg /tmp/winehq.key \
    && printf 'Types: deb\nURIs: https://dl.winehq.org/wine-builds/debian\nSuites: trixie\nComponents: main\nArchitectures: amd64 i386\nSigned-By: /etc/apt/keyrings/winehq-archive.gpg\n' \
      > /etc/apt/sources.list.d/winehq-trixie.sources \
    && apt-get update \
    && apt-get install -y --install-recommends 'winehq-stable=11.0.0.0~trixie-1' \
    && wine --version | grep -Eq '^wine-11([.]|$)' \
    && rm -f /tmp/winehq.key \
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
# Preserve failure causality: an &&/background/||-true chain can mask
# wineboot failure while Docker reports a successful prewarmed layer.
RUN set -eu; \
    chmod +x /scripts/setup/install-theme.sh; \
    mkdir -p /opt/winebot/prefix-template; \
    export DISPLAY=:95; \
    Xvfb "$DISPLAY" -screen 0 1280x720x24 -noreset >/dev/null 2>&1 & \
    XVFB_PID=$!; \
    trap 'kill "$XVFB_PID" >/dev/null 2>&1 || :; wait "$XVFB_PID" 2>/dev/null || :' EXIT; \
    ready=0; \
    for attempt in $(seq 1 40); do \
        if xdpyinfo -display "$DISPLAY" >/dev/null 2>&1; then ready=1; break; fi; \
        sleep 0.25; \
    done; \
    if [ "$ready" -ne 1 ]; then \
        echo 'WINE_BASE_PREFIX_DIAGNOSTIC stage=xvfb_unready' >&2; exit 1; \
    fi; \
    if ! timeout -k 5s 120s wineboot -i >/dev/null 2>&1; then \
        echo 'WINE_BASE_PREFIX_DIAGNOSTIC stage=wineboot_failed' >&2; exit 1; \
    fi; \
    if ! timeout -k 5s 60s wineserver -w >/dev/null 2>&1; then \
        echo 'WINE_BASE_PREFIX_DIAGNOSTIC stage=wineserver_wait_failed' >&2; exit 1; \
    fi; \
    if [ ! -s "$WINEPREFIX/system.reg" ]; then \
        echo 'WINE_BASE_PREFIX_DIAGNOSTIC stage=registry_missing' >&2; exit 1; \
    fi; \
    if ! /scripts/setup/install-theme.sh >/dev/null 2>&1; then \
        echo 'WINE_BASE_PREFIX_DIAGNOSTIC stage=theme_failed' >&2; exit 1; \
    fi; \
    if ! wine reg add "HKEY_CURRENT_USER\Software\Wine\X11 Driver" /v UseXInput2 /t REG_SZ /d "N" /f >/dev/null 2>&1; then \
        echo 'WINE_BASE_PREFIX_DIAGNOSTIC stage=registry_tune_failed' >&2; exit 1; \
    fi; \
    if ! wine reg add "HKEY_CURRENT_USER\Software\Wine\X11 Driver" /v Managed /t REG_SZ /d "Y" /f >/dev/null 2>&1; then \
        echo 'WINE_BASE_PREFIX_DIAGNOSTIC stage=registry_tune_failed' >&2; exit 1; \
    fi; \
    if ! timeout -k 5s 30s wineserver -k >/dev/null 2>&1; then \
        echo 'WINE_BASE_PREFIX_DIAGNOSTIC stage=wineserver_stop_failed' >&2; exit 1; \
    fi

# 4. Final Base Layer
FROM base-system AS final
COPY --from=prefix-warmer --chown=winebot:winebot /opt/winebot/prefix-template /opt/winebot/prefix-template
