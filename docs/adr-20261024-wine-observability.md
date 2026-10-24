# ADR (experimental): prefer stock Wine WinEvent instrumentation before source patches

Date: 2026-10-24
Status: **experimental / not production admitted**
DLE: https://github.com/mark-e-deyoung/winebot-research/issues/1

## Context and evidence

WineBot serves three audiences simultaneously: human operators (including
assistive technologies), automation, and agents. All must observe the same
underlying Windows application state, with different accessible presentation
and control surfaces. Existing WineBot has a brokered input API, X11 window
enumeration, WinInspect snapshot integration, and CV sidecars.

- Unmodified source-built Wine 11.0 WoW64, Xvfb, 32-bit CMD and visible
  Notepad baseline: Actions **40010876411**, PASS.
- Existing Debian Wine baseline, visible synthetic X11 window and read-only
  `SetWinEventHook` show/location callbacks: Actions **40046310033**, PASS.
- Per-session bounded event-stream adapter static qualification, 9 tests:
  Actions **40047035425**, PASS.
- Built-in WinInspect v0.4.4 qualification is independent and currently
  **UNQUALIFIED** (draft PR #136): daemon and TCP are alive but read-only RPC
  reports response-ID mismatch, HTTP 502. X11 readiness != WinInspect readiness.
- Source-built Wine 11.0 event probe: run **40045850159** completed **PASS**;
  exact job confirms original WoW64/Notepad smoke and new X11+WinEvent
  synthetic tests. This is not a Windows UIA or full-app claim.

## Decision

**Do not carry a Wine source patch to emit synthetic WinEvent callbacks.**
The current Debian Wine control demonstrates this narrow capability without
a fork. First evaluate standard Win32 observer APIs and existing WinInspect
and X11 interfaces. Any later Wine patch must cite a reproducible missing
primitive, minimize its footprint, remain opt-in, and undergo separate
licensing/security and regression review.

## Experimental component contract

`rdte/wine11/event_bridge.py` accepts the allowlisted
`winebot.wine.event.v1` protocol: exact keys `schema`, `kind`,
`sequence`; only synthetic event kind and monotonic sequence are retained.
A required `ready@0` is followed by consecutive positive source indexes.
Unrecognized type/field, extra identifiers, overflow, missing source index,
out-of-order events or raw sensitive metadata cause an unqualified state.
No raw events are persisted or printed. A bounded in-memory ring supports
read-only cursor pagination; an overwritten cursor reports an explicit history
gap; `close` wipes buffered state.

Each bridge instance belongs to **one session only**; transport
authorization, session binding, lease checks and broker integration are not
implemented in this RDTE. All consumer roles are read-only here. Never expose
it as an unauthenticated HTTP, VNC, socket, MCP, or external-agent service.

## Three-audience admission requirements

| Audience | Future behavior (not yet implemented) | Gate |
|---|---|---|
| Human/assistive | User-facing focus/alert state, keyboard operation, screen reader compatibility, discoverability | Empirical MSAA/UIA/AT testing |
| Automation | Action-to-event correlation, deterministic postcondition, idempotency and lease validation | Input Broker review, replay tests |
| Agent | Capability-qualified semantic snapshots/events and optional scoped CV ground truth | Authenticated session binding, redaction, model data provenance |

WinInspect snapshots can enrich event observations only after independent
RPC qualification and correct Windows HWND/X11 window mapping; never infer a
complete accessibility tree from a window title or WinEvent callback.

## Evidence boundaries and next DAG

1. **PASSED:** Actions 40045850159 proves native Wine 11 synthetic WinEvent callbacks.
2. **RED:** run 40047245106 confirmed synthetic Wine callback receipt and
   strict source-schema validation, but the live adapter reported
   `bridge_missing_event`. Preserve as an unqualified cursor/integration test.
   Isolated diagnostic run 40047495264 established
   `roundtrip_source_disagrees_with_validator`. Root cause was Python
   `readlines(131)` interpreting 131 as a byte hint. Corrected in
   `qualification/wine10-event-null-20261024@45556d5ed28ed058a3b7c235fbd603a0bd292487`:
   byte-capped full read, exact schema and final newline, 8 regression tests.
   **PASS:** Actions 40075822335 verified all 8 unit tests, X11 fixture,
   WinEvent stream, strict-schema checks, and live adapter ingest/cursor/close.
   Zero attached run artifacts. Historical red receipts remain valid.
3. **RUNNING:** Wine11 source-built callback + EventBridge full roundtrip in
   isolated Actions 40076089386, head `ab9a36bbddf4f29f4e4a556c4a91a05ae1df046f`.
   Independent CPU-only regression preflight precedes source compilation;
   do not claim end-to-end Wine11 success until that run finishes.
4. **READY AFTER 3:** compare exact Wine versions and immutable base digests;
   read-only capability negotiation, missing event detection, overflow policy,
   stream authorization and session isolation.
5. **SEPARATE BLOCKER:** existing WinInspect upstream PR #18 already supplies
   a test-qualified proposed response ID preservation fix, but remains
   unmerged. WineBot draft #136 packaged daemon is still unqualified;
   verify source/binary provenance and requalify with an independently
   admitted corrected binary before consuming its snapshots.
6. **OWNER/REVIEW GATES:** security disclosure authority #515, existing
   red v1 contract conformance, prior WinInspect packaging/merge gates and all
   release/production gates remain unaltered. No PR, publish or merge.

Until the above proof is complete, this ADR is not a Wine11-vs-Wine10
performance claim or production system architecture approval.
