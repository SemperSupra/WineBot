# Portable observer consumer interface — test-only contract candidate (2026-10-31)

Status: **RDTE ONLY / not promoted**. Runtime targets: native Windows and **source-pinned Wine 11.0**, not Ubuntu Wine 9. This document and Go harness do not authorize real application inspection, injection, actuation, release or any new public API.

## Consumer invariant

A consumer such as WinInspect must not need to know whether Win32 events came from native Windows, Wine 11's user32/win32u/server hook machinery, a UIA provider, a DLL interceptor, or a snapshot-delta fallback. The adapter exposes **identical versioned envelope syntax and meanings**. Backend-specific support is declared separately as a capability, with `unverified` or `unsupported` when appropriate. Consistent interface **does not** mean fabricated events or guaranteed feature parity.

The prototype `observer.portable.v0` consumes the existing privacy-minimized `winebot.wine.event.v1` raw stream without changing its source. The externally trusted supervisor supplies the opaque **producer incarnation/stream identity**, independently of raw producer bytes. The adapter is **not** an authorization check, session broker, event-history database, injection engine or WinInspect daemon.

## Read-only event envelope

```json
{"contract":"observer.portable.v0","stream":"opaque-test-incarnation","source":"win32.setwineventhook","sequence":2,"status":"observed","kind":"window.shown"}
```

Allowed normalized `kind` for the current WinEvent collector: `window.created`, `window.shown`, `window.hidden`, `window.destroyed`, `window.location_changed`, `window.focused`, `window.foreground_changed`. `ready`, `gap`, `overflow`, `unsupported` are **status**, not invented window events. An actual raw sequence discontinuity produces an explicit **terminal gap**, not a fabricated window event. Exact 128-observation bound and terminal `overflow@129` are validated. The existing `ready@0` handshake is distinct from any application event. Neither callback delivery nor an input acknowledgement proves the desired application postcondition.

No raw HWND, process ID, title, screen contents, password, coordinates, local path or credential may appear in the portable envelope. A scoped target identity may be present in a separately admitted internal projection when justified; never silently expose it in public fixtures.

## Capability discovery

An experimental capability response explicitly reports `contract`, `runtime` (`windows` or `wine`), `source`, `fixture_scoped`, and feature-specific statuses. Every feature is initially `unverified`; neither using the same Win32 API nor a successful compile permits automatic promotion to supported. A future admitted product contract may report `supported`, `degraded`, `permission_denied`, `unsupported`, `unavailable`, with exact executable/runtime/version and evidence tier. Do not claim semantic UIA parity under Wine 11 until independently tested.

## Relationships to existing projects

| Project | Role | Constraint |
| --- | --- | --- |
| WinInspect | Optional generic sensor/semantic-enrichment consumer and existing RPC/transport surface | Reuse `events.poll`/capability architecture as owner directs; do not create a second global daemon or treat polling snapshots as true notifications; preserve published v0.4.4 and draft v0.5 target-epoch contract independently |
| WineBot | Wine 11 session/runtime, process ownership, Xvfb, event stream, resource limits | Broker/registry incarnation G2 remains an active security gate; raw adapter cannot bypass |
| WinBot | Native Windows interactive-session/desktop arbitration, single input lease, human preemption | No injected source or WinInspect direct invocation may bypass the authenticated broker |
| winebot-contracts | Optional cross-runtime capability-qualified conformance after evidence and owner approval | This public RDTE PoC is *not* a promoted contract or universal required core |

**Three identities remain separate:** principal/session/desktop authority (whether an action is allowed); WinInspect HWND/UIA `target_epoch` (which target instance); observer producer incarnation/cursor (which observations belong to the current source). An event epoch is not a security credential.

## Minimum independent acceptance for promotion

1. Exact same **current** observer source and normalized fixture events on native Windows x64 and x86 and pinned Wine **11.0**, with source SHA, binary and runtime evidence.
2. Failure negatives: malformed/private raw fields refused, missing/replayed sequences surfaced as gap, overflow terminal, stale-stream/revoked read refused by external trusted owner/registry, late control-read and reader lifetime.
3. WinInspect benchmark: compare fixed-snapshot `events.poll` against a scoped live WinEvent feed and UIA where available, then verify real consumer task postconditions, event latency, misses, overhead and cancellation.
4. Explicit `supported` only for mechanisms with evidence, `unverified` for untested environments, `degraded` for known gaps, and `unsupported` for genuinely absent providers. No synthesized feature parity.
5. Keep one canonical observer source/adapter set, capability versioning, no source/credential/artifact leakage, and no unsupported direct actuator authority. WinBot desktop P0, WineBot G0/G2 and security #515 remain separate blockers.

## Artifacts and ownership

Experimental schema/code/test fixtures remain in this isolated Git branch. Decisions, exact CI receipts and executable baton go in private WineBot DLE #1 with cross-reference to WinInspect #367 and WinBot #110. Large approved binary traces would use Google Drive with hash/provenance; this RDTE produces none.
