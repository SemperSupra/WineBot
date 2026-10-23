# Test-only child image; all source inputs are public synthetic fixtures.
# The toolchain is the already-built WineBot hook DLL builder stage.
ARG TOOLCHAIN_IMAGE=winebot:rdte-mingw
ARG RUNTIME_IMAGE=winebot:rdte-cpu
FROM ${TOOLCHAIN_IMAGE} AS fixture-compiler
COPY tests/fixtures/cpu_gl_smoke.c /tmp/cpu_gl_smoke.c
RUN x86_64-w64-mingw32-gcc -O2 -o /tmp/cpu_gl_smoke.exe /tmp/cpu_gl_smoke.c \
    -lopengl32 -lgdi32 -luser32

FROM ${RUNTIME_IMAGE}
COPY --from=fixture-compiler /tmp/cpu_gl_smoke.exe /opt/winebot/cpu_gl_smoke.exe
COPY scripts/ci/cpu_wine_suite.py /opt/winebot/cpu_wine_suite.py
LABEL io.winebot.experimental.win32_cpu_rdte="not-for-release"
