# SPDX-License-Identifier: MIT
# RDTE-only overlay: pristine pinned Wine11 base plus fixture-scoped comparator.
# Never publish this image or the generated Windows executables.
ARG BASE=winebot-wine11-target-base:rdte
FROM ${BASE}
USER root
COPY rdte/wine11/win_event_target_probe.c /tmp/win_event_target_probe.c
RUN x86_64-w64-mingw32-gcc -std=c11 -O2 -Wall -Wextra -Werror \
      -o /opt/winebot-wine/rdte/win_event_target_probe.exe \
      /tmp/win_event_target_probe.c -luser32 \
    && rm -f /tmp/win_event_target_probe.c
USER winebot
