# WinInspect v0.4.0 Integration

## Summary

WinInspect v0.4.0 is no longer just a WinSpy-style GUI inspector. It ships:

- `wininspectd.exe`: daemon/broker
- `wininspect.exe`: CLI client
- `wininspect-gui.exe`: native GUI client
- length-prefixed JSON protocol over TCP and named pipe transports
- capability probing through `daemon.health` and `daemon.capabilities`
- window, screen, process, clipboard, registry, input, metrics, and control
  method families

WineBot should treat WinInspect as a read-first inspection sidecar inside the
Wine prefix. Mutating operations must remain subordinate to WineBot's input
broker and control policy.

## Build And Deployment Requirements

Pinned release asset in `docker/Dockerfile`:

- `WinInspectPortable-v0.4.0.zip`
- SHA256: `83b64999fef9ab01d749ab94193899e3915774d217900ac80c3c34021ff3e416`

The portable zip contains only:

- `wininspect.exe`
- `wininspectd.exe`
- `wininspect-gui.exe`
- `config.default.json`
- `LICENSE`

Release smoke must verify runtime dependencies under Wine rather than assuming
DLL needs. Use:

```bash
bash /scripts/diagnostics/smoke-wininspect.sh
```

This smoke checks CLI/daemon startup, loopback daemon readiness, capabilities,
and top-window listing.

## Recommended WineBot Use

### 1. Capabilities First

At startup or diagnostic time, query WinInspect capabilities and persist the
result in diagnostics:

- `daemon.health`
- `daemon.capabilities`
- CLI equivalent: `wine wininspect.exe capabilities`

Use capability fields to decide whether to use a feature:

- `uia`: expected false on Wine 10.0 today
- `clipboard`: useful for inspection and controlled workflows
- `input_injection`: useful only behind WineBot broker authorization
- `registry_write`: do not expose by default
- `service_manager`: expected false on Wine
- `window_highlight`: useful for debugging and visual diagnostics
- `pipe_available`: useful to choose named pipe versus TCP

### 2. Replace Ad Hoc Inspection Where Practical

Use WinInspect for structured window and screen inspection instead of adding
more xdotool/AutoIt parsing:

- `window.listTop`
- `window.listChildren`
- `window.getInfo`
- `window.getTree`
- `window.pickAtPoint`
- `window.findRegex`
- `screen.desktopInfo`
- `screen.getPixel`
- `screen.pixelSearch`

WineBot's existing `/health/windows` and `/inspect/window` endpoints can grow a
WinInspect backend while keeping their public API stable.

Current WineBot integration exposes read-only daemon/window/screen inspection
through:

- `GET /health/wininspect`
- `GET /wininspect/capabilities`
- `GET /wininspect/windows`
- `GET /wininspect/window/{hwnd}`
- `GET /wininspect/screen`
- `GET /wininspect/pick`
- `POST /inspect/window`

### 3. Keep Mutations Brokered

WinInspect exposes mutating methods:

- `window.controlClick`
- `window.controlSend`
- `input.mouseClick`
- `input.text`
- `input.hotkey`
- `window.move`
- `window.resize`
- `process.kill`
- `reg.write`

WineBot should not expose these directly until they are routed through the
existing Input Broker and audit controls. The preferred integration is:

1. WineBot API receives an authorized request.
2. Input Broker grants or denies control.
3. WineBot calls WinInspect only after broker approval.
4. WineBot records the action in existing input/control traces.

### 4. Prefer Loopback TCP Initially

WinInspect supports TCP, TLS TCP, named pipe, HTTP, WebSocket, and UDP
discovery in its protocol docs. For WineBot:

- start with loopback TCP on `127.0.0.1:1985`
- do not bind externally by default
- keep WinInspect discovery disabled unless there is a deliberate multi-node
  discovery feature
- defer SSH-key/TLS auth until WineBot needs remote WinInspect access

Named pipe support should be probed with `pipe_available`, but TCP is easier to
smoke and diagnose from Linux-side WineBot processes.

### 5. Metrics And Diagnostics

Use WinInspect's daemon status/metrics as diagnostic data:

- `daemon.status`
- `daemon.metrics`
- `daemon.diag`

These should feed diagnostic bundles rather than release-facing APIs first.

## Features To Defer

| Feature | Reason |
|:---|:---|
| `ui.inspect` | UIA is expected unavailable on Wine 10.0 until Wine/UIA support improves. |
| `mem.read` / `mem.write` | High-risk debug feature; keep out of normal release surface. |
| `reg.write` / `reg.delete` | Mutating registry operations require explicit policy and recovery design. |
| `daemon.downloadUpdate` | WineBot already pins third-party tools in Docker builds. Runtime self-update breaks reproducibility. |
| WinInspect recording | WineBot has its own recorder and artifact manifest. Evaluate later, do not mix formats now. |
| UDP discovery / external bind | Release should remain loopback-only unless explicitly exposing WinInspect. |

## Closeout Status - 2026-07-05

Completed on PR #89:

- Image build and CI smoke with WinInspect v0.4.0 passed in CI run
  `28753849320`.
- `scripts/diagnostics/smoke-wininspect.sh` verifies CLI/daemon help,
  loopback daemon readiness, capabilities, and top-window listing under Wine.
- WineBot exposes the first read-only API slice through `/health/wininspect`,
  `/wininspect/*`, and `/inspect/window`.

Remaining work:

1. Extend diagnostic bundles to persist `daemon.capabilities`,
   `daemon.status`, and smoke output with release artifacts.
2. Use the read-only WinInspect API endpoints in the dashboard and E2E
   diagnostics where structured HWND/control data is useful.
3. Gate any WinInspect mutation method behind the Input Broker.
4. Keep #87 and #88 open until PR #89 merges, then close them with CI run
   `28753849320` as evidence.

## Related Tracking

- #87: WinInspect runtime dependency check
- #88: WinInspect upgrade and capability evaluation
- #94: reusable Wine automation helper bundle extraction
