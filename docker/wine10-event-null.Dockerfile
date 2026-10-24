# SPDX-License-Identifier: MIT
# Synthetic event null/control lane against WineBot's established Debian Wine base.
# This is not a release, source patch or production Dockerfile modification.
FROM ghcr.io/sempersupra/winebot-base:base-2026-05-04
USER root
ENV DEBIAN_FRONTEND=noninteractive
RUN apt-get update && apt-get install -y --no-install-recommends \
    gcc-mingw-w64-x86-64 python3 \
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
COPY rdte/wine11/event_bridge.py /usr/local/lib/winebot-rdte/event_bridge.py
COPY scripts/ci/verify-wine-event-roundtrip.py /usr/local/bin/verify-wine-event-roundtrip
COPY scripts/ci/wine11-event-smoke.sh /usr/local/bin/wine-event-smoke
RUN chmod 0755 /usr/local/bin/verify-wine11-events /usr/local/bin/wine-event-smoke \
    && chmod 0755 /usr/local/bin/verify-wine-event-roundtrip \
    && PYTHONPATH=/usr/local/lib/winebot-rdte python3 -m py_compile /usr/local/lib/winebot-rdte/event_bridge.py /usr/local/bin/verify-wine-event-roundtrip \
    && python3 /usr/local/bin/verify-wine11-events --self-test
USER winebot
ENV WINEARCH=win64 PYTHONPATH=/usr/local/lib/winebot-rdte
CMD ["/usr/local/bin/wine-event-smoke"]
