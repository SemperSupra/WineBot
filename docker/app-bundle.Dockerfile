# App packages are built separately from the WineBot runtime.
# The builder is pinned to an already-qualified Debian digest. No network
# downloads or unverified Windows installer execution occur during startup.
ARG APP_PACK_BUILDER_IMAGE=debian@sha256:cedb1ef40439206b673ee8b33a46a03a0c9fa90bf3732f54704f99cb061d2c5a
FROM ${APP_PACK_BUILDER_IMAGE}
COPY apps/ /opt/winebot/app-payload/
COPY scripts/layers/seed-apps.sh /usr/local/bin/winebot-seed-apps
COPY scripts/layers/prepare-state.sh /usr/local/bin/winebot-prepare-state
RUN set -eu; \
    chmod 0555 /usr/local/bin/winebot-seed-apps /usr/local/bin/winebot-prepare-state; \
    test -d /opt/winebot/app-payload; \
    test -z "$(find /opt/winebot/app-payload -type l -print -quit)"; \
    cd /opt/winebot/app-payload; \
    find . -type f -exec sha256sum {} + | LC_ALL=C sort > /opt/winebot/app-manifest.sha256; \
    test -s /opt/winebot/app-manifest.sha256
LABEL org.opencontainers.image.description="Disposable WineBot immutable application payload / seeder"
ENTRYPOINT ["/bin/sh", "/usr/local/bin/winebot-seed-apps"]
