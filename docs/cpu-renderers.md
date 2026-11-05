# CPU software-renderer RDTE (experimental — NOT RELEASED)

Goal: qualify CPU-only OpenGL and Vulkan rendering in public generic cloud
fixtures without a GPU or private/specific host facts.

## Profiles
- `cpu-opengl-llvmpipe` — forced Mesa OpenGL LLVMpipe; probe with glxinfo, bounded glxgears smoke.
- `cpu-vulkan-lavapipe` — explicit Mesa Lavapipe ICD; probe with vulkaninfo, bounded vkcube draw.
- `cpu-vulkan-swiftshader` — optional external pinned SwiftShader ICD. NOT installed by default, and must fail closed when absent.

All execution is optional and separate from the existing WineBot base and
default behavior. The Python launcher `scripts/cpu_renderer.py` sets
`LIBGL_ALWAYS_SOFTWARE=1`, `GALLIUM_DRIVER=llvmpipe`, and
`LP_NUM_THREADS=4` (override 1..32). Vulkan profiles select exactly one
approved ICD and scrub inherited Vulkan driver selections.

## Commands

```sh
python3 scripts/cpu_renderer.py profiles
# On Debian with Mesa, xvfb, vulkan-tools and mesa-utils installed:
xvfb-run -a python3 scripts/cpu_renderer.py probe --profile cpu-opengl-llvmpipe
xvfb-run -a python3 scripts/cpu_renderer.py benchmark --profile cpu-opengl-llvmpipe --seconds 7
xvfb-run -a python3 scripts/cpu_renderer.py probe --profile cpu-vulkan-lavapipe
xvfb-run -a python3 scripts/cpu_renderer.py benchmark --profile cpu-vulkan-lavapipe --frames 20 --timeout 45
# Explicitly launch a Windows game under Wine with LLVMpipe:
xvfb-run -a python3 scripts/cpu_renderer.py exec --profile cpu-opengl-llvmpipe -- wine /apps/test.exe
```

Optional Docker RDTE image, isolated from normal WineBot release:

```sh
docker build -f docker/cpu-renderers.Dockerfile -t winebot-cpu-rdte:synthetic .
docker run --rm --network none --entrypoint /usr/bin/xvfb-run winebot-cpu-rdte:synthetic -a \
  python3 /opt/winebot/cpu_renderer.py probe --profile cpu-opengl-llvmpipe
```

For an opt-in WineBot overlay, first build an existing WineBot image and then
supply its exact local tag as `BASE_IMAGE`:

```sh
docker build -f docker/cpu-renderers.Dockerfile --build-arg BASE_IMAGE=winebot:local-rel \
  -t winebot:cpu-rdte .
```

This is a child image with the same WineBot entrypoint, **not** an
automatically activated service-wide renderer. A per-command `exec` wrapper
selects the software backend for the launched process and descendants;
normal WineBot services remain unchanged until separate integrated-soak
qualification is complete.

SwiftShader: build/obtain an authorized, version-pinned Vulkan ICD with its
license/provenance reviewed, and set `WINEBOT_SWIFTSHADER_ICD` to its
`vk_swiftshader_icd.json` path, or pass `--icd`. Never silently fall back
to hardware or claim a comparison if SwiftShader is not installed.

## Benchmark interpretation

- glxgears FPS is a GLX render smoke, not a game benchmark.
- vkcube frame-budget / elapsed estimate includes startup and does not
  establish steady-state FPS.
- Do not compare glxgears throughput against vkcube across graphics APIs.
- A valid Lavapipe-versus-SwiftShader comparison needs the **same** Vulkan
  application, resolution, render configuration, frame budget, host and run
  sequence, repeated measurements and first-frame/warm-up separation.
- These results cannot establish Wine game compatibility or DXVK/VKD3D feature support.
- Reproducible, versioned screenshots and visual correctness measurements are
  a subsequent gate.

## Security / qualification

- Public workflow runs **synthetic Debian/Mesa only**, on free public runners,
  with `--network none` at runtime, no HIL, secrets, artifacts or telemetry
  uploads, and no host/gpu identity in the structured report.
- No private/sovereign workload, paths, topology, screenshot, or CPU identity
  belongs in public workflow output or its PR discussion.
- Do not merge this RDTE branch. WineBot public-artifact, source provenance,
  contractual conformance and release gates remain governed by independent
  security issue `SemperSupra/agent-dispatch-private#515`.
- The legacy v1 conformance aggregate is expected red independently of this work.
- First qualification is purely software-renderer capability; native Wine
  application integration, actual 3D game rendering, CV labels and graphics
  correctness are NOT established by this synthetic gate.

## Next baton

Observe exact Actions run/job IDs, generic probe and smoke results, and
any first failure. If passes, separately qualify the child WineBot image and
one synthetic 3D Windows application, preserving release and artifact
publication gates. Then qualify pinned SwiftShader ICD and run matched
multi-repetition Vulkan measurements. Do not promote without review.
