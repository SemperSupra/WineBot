# SPDX-License-Identifier: MIT
# Disposable local Wine observer (synthetic fixture only); not production.
FROM ghcr.io/sempersupra/winebot-base:base-2026-05-04
USER root
ENV DEBIAN_FRONTEND=noninteractive
RUN apt-get update && apt-get install -y --no-install-recommends gcc-mingw-w64-x86-64 python3 \
    && rm -rf /var/lib/apt/lists/*
COPY rdte/wine11/win_event_observer.c /tmp/win_event_observer.c
COPY rdte/wine11/win_event_fixture.c /tmp/win_event_fixture.c
RUN mkdir -p /opt/winebot/rdte \
    && x86_64-w64-mingw32-gcc -std=c11 -O2 -Wall -Wextra -Werror \
      -o /opt/winebot/rdte/win_event_observer.exe /tmp/win_event_observer.c -luser32 \
    && x86_64-w64-mingw32-gcc -std=c11 -O2 -Wall -Wextra -Werror \
      -o /opt/winebot/rdte/win_event_fixture.exe /tmp/win_event_fixture.c -luser32 \
    && rm /tmp/win_event_observer.c /tmp/win_event_fixture.c
COPY api/core/wine_events_rdte.py /api/core/wine_events_rdte.py
COPY api/core/wine_events_source_rdte.py /api/core/wine_events_source_rdte.py
COPY api/core/wine_events_process_rdte.py /api/core/wine_events_process_rdte.py
COPY rdte/wine11/event_bridge.py /rdte/wine11/event_bridge.py
COPY scripts/ci/wine-events-owned-process-smoke.sh /usr/local/bin/wine-events-owned-process-smoke
COPY scripts/ci/wine-events-owned-process-smoke.py /scripts/ci/wine-events-owned-process-smoke.py
RUN chmod 0755 /usr/local/bin/wine-events-owned-process-smoke \
    && python3 -m compileall -q /api /rdte /scripts/ci/wine-events-owned-process-smoke.py
USER winebot
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1 WINEARCH=win64 WINEDEBUG=-all PYTHONPATH=/
WORKDIR /
CMD ["/usr/local/bin/wine-events-owned-process-smoke"]
