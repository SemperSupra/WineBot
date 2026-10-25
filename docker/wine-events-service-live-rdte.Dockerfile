# SPDX-License-Identifier: MIT
# Full Python API + fixed synthetic observer under public Debian Wine.
# Disposable RDTE only; no production image mutation.
FROM ghcr.io/sempersupra/winebot-base:base-2026-05-04
USER root
ENV DEBIAN_FRONTEND=noninteractive
RUN apt-get update && apt-get install -y --no-install-recommends gcc-mingw-w64-x86-64 \
    && rm -rf /var/lib/apt/lists/*
COPY requirements/requirements-rel.txt /tmp/winebot-api-reqs.txt
RUN pip3 install --break-system-packages --disable-pip-version-check \
    --no-cache-dir -r /tmp/winebot-api-reqs.txt \
    && rm /tmp/winebot-api-reqs.txt
COPY rdte/wine11/win_event_observer.c /tmp/win_event_observer.c
COPY rdte/wine11/win_event_fixture.c /tmp/win_event_fixture.c
COPY rdte/wine11/win_event_burst_fixture.c /tmp/win_event_burst_fixture.c
RUN mkdir -p /opt/winebot/rdte \
    && x86_64-w64-mingw32-gcc -std=c11 -O2 -Wall -Wextra -Werror \
      -o /opt/winebot/rdte/win_event_observer.exe /tmp/win_event_observer.c -luser32 \
    && x86_64-w64-mingw32-gcc -std=c11 -O2 -Wall -Wextra -Werror \
      -o /opt/winebot/rdte/win_event_fixture.exe /tmp/win_event_fixture.c -luser32 \
    && x86_64-w64-mingw32-gcc -std=c11 -O2 -Wall -Wextra -Werror \
      -o /opt/winebot/rdte/win_event_burst_fixture.exe /tmp/win_event_burst_fixture.c -luser32 \
    && rm /tmp/win_event_observer.c /tmp/win_event_fixture.c /tmp/win_event_burst_fixture.c
COPY api /api
COPY rdte/wine11/event_bridge.py /rdte/wine11/event_bridge.py
COPY api/core/wine_events_process_rdte.py /api/core/wine_events_process_rdte.py
COPY api/core/wine_events_service_rdte.py /api/core/wine_events_service_rdte.py
COPY scripts/ci/wine-events-owned-process-smoke.sh /tmp/old-smoke.sh
COPY scripts/ci/wine-events-service-live-smoke.sh /usr/local/bin/wine-events-service-live-smoke
COPY scripts/ci/wine-events-service-live-smoke.py /scripts/ci/wine-events-service-live-smoke.py
COPY scripts/ci/wine-events-overflow-live-smoke.py /scripts/ci/wine-events-overflow-live-smoke.py
RUN chmod 0755 /usr/local/bin/wine-events-service-live-smoke \
    && python3 -m compileall -q /api /rdte /scripts/ci/wine-events-service-live-smoke.py /scripts/ci/wine-events-overflow-live-smoke.py
ENV PYTHONPATH=/ PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1 WINEARCH=win64 WINEDEBUG=-all
WORKDIR /
USER winebot
CMD ["/usr/local/bin/wine-events-service-live-smoke"]
