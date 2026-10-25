# SPDX-License-Identifier: MIT
# Synthetic RDTE: validate WineBot's real Python API imports inside a disposable
# image derived from the existing public WineBot base. NOT the production image.
FROM ghcr.io/sempersupra/winebot-base:base-2026-05-04
USER root
COPY requirements/requirements-rel.txt /tmp/wine-events-requirements.txt
RUN pip3 install --break-system-packages --disable-pip-version-check \
    --no-cache-dir -r /tmp/wine-events-requirements.txt \
    && rm /tmp/wine-events-requirements.txt
COPY api /api
COPY rdte/wine11/event_bridge.py /rdte/wine11/event_bridge.py
COPY tests/test_wine_event_server_mount.py /rdte/tests/test_wine_event_server_mount.py
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1
WORKDIR /
USER winebot
CMD ["python3", "-m", "unittest", "discover", "-s", "/rdte/tests", "-p", "test_wine_event_server_mount.py", "-v"]
