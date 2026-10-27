# SPDX-License-Identifier: MIT
# Disposable overlay on already-qualified synthetic WineBot observer image.
# The base is built locally in the same CI job; never pushed or published.
FROM winebot-api-owned-observer:rdte
COPY rdte/wine11/generation_cursor_rdte.py /rdte/wine11/generation_cursor_rdte.py
COPY scripts/ci/wine-events-generation-handover.py /scripts/ci/wine-events-generation-handover.py
COPY scripts/ci/wine-events-generation-handover.sh /scripts/ci/wine-events-generation-handover.sh
CMD ["/bin/bash", "/scripts/ci/wine-events-generation-handover.sh"]
