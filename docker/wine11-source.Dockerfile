# SPDX-License-Identifier: LGPL-2.1-or-later
# EXPERIMENT ONLY: pinned, unmodified Wine 11.0 source, new WoW64 layout.
# This is deliberately not wired into docker/base.Dockerfile or production images.
ARG DEBIAN_IMAGE=debian@sha256:cedb1ef40439206b673ee8b33a46a03a0c9fa90bf3732f54704f99cb061d2c5a
FROM ${DEBIAN_IMAGE} AS wine11-runtime
SHELL ["/bin/bash", "-euo", "pipefail", "-c"]
ENV DEBIAN_FRONTEND=noninteractive

# Generic x86-64 cloud runner. No private hosts, input assets or secrets.
RUN apt-get update && apt-get install -y --no-install-recommends \
    ca-certificates curl xz-utils \
    gcc g++ make pkg-config flex bison nasm \
    gcc-mingw-w64-x86-64 gcc-mingw-w64-i686 \
    g++-mingw-w64-x86-64 g++-mingw-w64-i686 \
    libx11-dev libxext-dev libxrender-dev libxrandr-dev libxcursor-dev \
    libxi-dev libxinerama-dev libxcomposite-dev libxfixes-dev libxxf86vm-dev \
    libfreetype-dev libfontconfig-dev libgnutls28-dev libasound2-dev \
    libpulse-dev libudev-dev libdbus-1-dev libvulkan-dev \
    libgl-dev libglu1-mesa-dev libgstreamer1.0-dev \
    libgstreamer-plugins-base1.0-dev libxml2-dev libxslt1-dev \
    xvfb xauth xdotool fonts-liberation mesa-utils libgl1-mesa-dri \
    && rm -rf /var/lib/apt/lists/*

# Source artifact is from official WineHQ release announcement.
# SHA256 is a constant, deliberately not a caller-controlled build argument.
RUN mkdir -p /tmp/wine-source /tmp/wine-build \
    && curl --fail --location --show-error --silent --retry 4 \
         --output /tmp/wine-source/wine-11.0.tar.xz \
         https://dl.winehq.org/wine/source/11.0/wine-11.0.tar.xz \
    && echo 'c07a6857933c1fc60dff5448d79f39c92481c1e9db5aa628db9d0358446e0701  /tmp/wine-source/wine-11.0.tar.xz' | sha256sum --check --status \
    && tar --extract --xz --file /tmp/wine-source/wine-11.0.tar.xz --directory /tmp/wine-source

# Build both PE architectures with the new WoW64 mode (no i386 Linux userspace).
# No Wine source patches in the first falsification build.
RUN cd /tmp/wine-build \
    && /tmp/wine-source/wine-11.0/configure \
         --prefix=/opt/winebot-wine/11.0 \
         --enable-archs=x86_64,i386 \
         --disable-tests \
    && make --jobs=2 \
    && make install \
    && rm -rf /tmp/wine-source /tmp/wine-build

ENV PATH="/opt/winebot-wine/11.0/bin:${PATH}" \
    WINEDEBUG=-all \
    WINEDLLOVERRIDES="mscoree,mshtml=" \
    DISPLAY=:99
RUN useradd --create-home --uid 1000 --shell /bin/bash winebot \
    && mkdir -p /tmp/.X11-unix \
    && chmod 1777 /tmp/.X11-unix
COPY scripts/ci/wine11-source-smoke.sh /usr/local/bin/wine11-source-smoke
RUN chmod 0755 /usr/local/bin/wine11-source-smoke \
    && /opt/winebot-wine/11.0/bin/wine --version | grep -Fx 'wine-11.0'
USER winebot
WORKDIR /home/winebot
CMD ["/usr/local/bin/wine11-source-smoke"]

# RDTE-only semantic event qualification. Win32 API observer (no Wine patch);
# synthetic Windows fixture and fail-closed Python schema validator.
# This image is never published or promoted as a WineBot base.
USER root
RUN apt-get update && apt-get install -y --no-install-recommends python3 \
    && rm -rf /var/lib/apt/lists/*
COPY rdte/wine11/win_event_observer.c /tmp/win_event_observer.c
COPY rdte/wine11/win_event_fixture.c /tmp/win_event_fixture.c
RUN mkdir -p /opt/winebot-wine/rdte \
    && x86_64-w64-mingw32-gcc -std=c11 -O2 -Wall -Wextra -Werror \
       -o /opt/winebot-wine/rdte/win_event_observer.exe \
       /tmp/win_event_observer.c -luser32 \
    && x86_64-w64-mingw32-gcc -std=c11 -O2 -Wall -Wextra -Werror \
       -o /opt/winebot-wine/rdte/win_event_fixture.exe \
       /tmp/win_event_fixture.c -luser32 \
    && rm -f /tmp/win_event_observer.c /tmp/win_event_fixture.c
COPY scripts/ci/verify-wine11-events.py /usr/local/bin/verify-wine11-events
COPY scripts/ci/wine11-event-smoke.sh /usr/local/bin/wine11-event-smoke
RUN chmod 0755 /usr/local/bin/verify-wine11-events /usr/local/bin/wine11-event-smoke \
    && python3 /usr/local/bin/verify-wine11-events --self-test
# Synthetic-only session-local adapter with byte-bounded readback.
COPY rdte/wine11/event_bridge.py /usr/local/lib/winebot-rdte/event_bridge.py
COPY scripts/ci/verify-wine-event-roundtrip.py /usr/local/bin/verify-wine-event-roundtrip
RUN chmod 0755 /usr/local/bin/verify-wine-event-roundtrip \
    && python3 -m py_compile /usr/local/lib/winebot-rdte/event_bridge.py /usr/local/bin/verify-wine-event-roundtrip
ENV PYTHONPATH=/usr/local/lib/winebot-rdte
USER winebot
CMD ["/usr/local/bin/wine11-event-smoke"]
