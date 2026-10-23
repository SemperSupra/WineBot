# WineBot Wine 11.0 custom source-build RDTE — 2026-10-23

## Purpose and authority
Start a reproducible **unmodified upstream** Wine 11.0 source build as the first
WineBot-specific build lane. The build is custom by its selected architecture,
install prefix, dependencies, runtime flags and qualification harness, but **does
not yet contain Wine source patches**. No version substitution for production.

- Source: official `https://dl.winehq.org/wine/source/11.0/wine-11.0.tar.xz`
- Source SHA-256: `c07a6857933c1fc60dff5448d79f39c92481c1e9db5aa628db9d0358446e0701`
- Image base: same digest-pinned Debian Trixie base used by WineBot
- Configure: `--enable-archs=x86_64,i386 --disable-tests`
- Private-source inputs: none. Source patches: none.
- Wine prefix: `/opt/winebot-wine/11.0`; test prefix is ephemeral.
- CI: disposable standard public GitHub Actions Ubuntu runner, zero paid services.
- Initial smoke: exact Wine 11.0 version, new 32-bit WoW64 cmd, visible
  64-bit Notepad under Xvfb. No system/device identities or screenshot output.

## Do-not-cross boundaries
1. Do not modify `docker/base.Dockerfile`, `docker/Dockerfile`, production
   WineBot `VERSION`, GHCR/release tags or existing images during this RDTE.
2. Keep independent security gate `SemperSupra/agent-dispatch-private#515`,
   WinInspect packaging/bridge qualification, red legacy conformance and
   existing PR/merge/release gates intact.
3. Do not upload artifacts or Docker build records; do not enable debug logs,
   export Wine prefixes, raw windows, full diagnostics, credentials or actual
   hardware, runner or network identifiers.
4. No private Actions runners, discretionary cloud spend, live user data,
   external game assets, proprietary app installers or automated promotion.
5. This isolated push lane intentionally avoids opening a PR and triggering
   the general CI workflow while its public artifact controls remain unresolved.

## Outcome classes
- **BUILD_FAILED:** source retrieval/hash, configure, compile or installation.
- **WINEBOOT_FAILED:** image built, but Wine initialization failed.
- **WOW64_FAILED:** 32-bit PE invocation failed.
- **WINDOW_FAILED:** X11-backed Notepad not visible.
- **SMOKE_PASSED:** all checks passed; **not** WineBot integration success.

Record exact source branch/head, Actions run/job IDs and first failing phase
in the linked GitHub DLE. Red CI is evidence, not a reason to bypass safeguards.

## Follow-on plan (separately admitted)
1. Independent review of build output/dependency completeness and patch queue
   policy; make a minimal and upstreamable patch only when falsified.
2. Test new build in an isolated alternate WineBot base with fresh prefixes.
   Do not reuse an existing Wine 10 pre-warmed prefix without an explicit migration
   test. Assert Input Broker/API, scoped X11 capture, WinInspect and 32/64-bit
   application launch with synthetic fixtures.
3. Compare Wine 10 production, Wine 11.0 stable and pinned Wine 11.x development
   separately for GUI, accessibility, event traces, CPU LLVMpipe/Lavapipe
   rendering, Windows games and image/annotation consistency.
4. Only after source, licensing, security, conformance and performance
   qualification consider a public artifact, controlled image promotion or merge.

No Wine 11 integration, cross-platform GPU parity, performance or accessibility
claim follows from initial compilation or this initial smoke.
