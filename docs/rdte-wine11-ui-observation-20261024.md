# WineBot custom Wine observability qualification — 2026-10-24

## Discover → Observe → Plan → Apply → Verify

### Discovered live baseline
- Unmodified, source-built upstream Wine **11.0** `x86_64,i386` new-WoW64 build
  was executed on public synthetic GitHub Actions **run 40010876411**,
  job **120610733436**, source HEAD
  `345b959650dd0bd4d1935c15261c069abaeb93d2`.
- All build steps passed. Allowed smoke outcomes, inspected independently:
  `wine_source_version_11_0`, `fresh_prefix`,
  `wow64_32bit_cmd`, `64bit_notepad_x11_window`.
- WineBot's current WinInspect integration offers read-only **snapshot**
  capabilities (top windows/children/window information, tree and screen),
  but its independently gated PortableApps packaging and daemon qualification
  remain unmerged. Prior X11 tests prove visible windows and scoped screenshots,
  **not** Win32 event completeness. Neither is evidence of UIA support.
- Public WineBot `main` remains at
  `d0fe951cc7a0a9e2ce1f3dba52e44db02ad15611`; no production mutation.

### Objective: a reversible, no-patch Win32 read-only observation seam
Falsify the need for a maintained Wine source fork **before** carrying one.
`rdte/wine11/win_event_observer.c` uses Windows' standard
`SetWinEventHook(WINEVENT_OUTOFCONTEXT)`. It filters to an exact, synthetic
window class `WB_RDTE_WINDOW`, and emits only allowlisted event **kinds**
(create/show/hide/destroy/focus/foreground/location), sequence and protocol
version. It does not collect HWND, PID, title, class name, keyboard content,
coordinates, host identity, screenshots, filenames, or arbitrary windows.
There are no mutation handlers. Fail-closed `unsupported`/overflow behavior.

`rdte/wine11/win_event_fixture.c` creates a synthetic window, changes its
geometry and focus, then destroys it. `wine11-event-smoke.sh` launches them
in a fresh Wine prefix under isolated Xvfb, asserts visible X11 fixture
presence **and** a complete, bounded semantic event stream. The validator
rejects extra JSON fields, sensitive identifiers, invalid sequence and missing
show/location events; its self-test includes malformed/adversarial fixtures.
Raw ephemeral event data is deliberately **not** printed or uploaded.

### Hypotheses and falsifiable tests
| Hypothesis | Measurement | Success condition |
|---|---|---|
| H0 upstream Wine exposes WinEvent callbacks | Observer registration and event stream | Hook starts and synthetic `show`, `location` observed |
| X11 window presence differs from semantic events | Synthetic fixture visible independently | X11 PASS alone never implies WinEvent PASS |
| No identifiers needed in public proof | Schema-normalizer tests | Reject `hwnd`, raw content or additional fields |
| Wine upstream sufficient for first event bridge | Side-by-side evidence | No source patch if event stream works |
| Source patches might add unique value | Future WinInspect + X11 + observer differential test | Instrument only measured missing primitive |

### Three audiences and placement
- Humans/assistive clients: use a future brokered semantic API with independently
  qualified MSAA/UIA and focus-order fidelity; do not mistake event availability
  for screen-reader or keyboard-accessibility conformance.
- Automation: brokered actions, idempotency, verified state transitions and
  bounded event observations. WinEvent callback is read-only, not a control path.
- Agents: machine-readable read-only snapshots/events and scoped CV cues with
  independently approved storage/redaction policies. No agent privilege
  escalation and no direct mutation API.

### Proposed follow-on execution DAG
1. **READY:** Build this Win32 probe with the same Wine 11.0 source;
   compare actual event registration, window visibility, and bounded JSONL
   evidence in a fresh public synthetic session.
2. **BLOCKED on 1:** Add a strictly opt-in local WineBot adapter that consumes
   an authenticated/brokered in-memory event stream without publishing raw
   telemetry or bypassing Input Broker. Independent unit+security review.
3. **BLOCKED on WinInspect independent qualification:** compare WinInspect
   snapshot data to the event stream for changed window state. Only propose
   tiny upstream-oriented Wine patch for a proven missing event.
4. **PARALLEL research:** nonpublishing renderer profiles (GDI, OpenGL/LLVMpipe,
   Vulkan/Lavapipe), CPU benchmarks, E2E accessible interaction and CV
   ground-truth provenance. Do not mix new game downloads into event RDTE.
5. **GATED:** alternate-base WineBot integration with a fresh prefix and
   synthetic broker/API/WinInspect/capture tests; separate security review,
   conformance and packaging gates for any production promotion.

### Security / source custody / performance limits
Only public WineHQ source and new synthetic Win32 test programs enter the
build. Standard public Linux GitHub Actions free-tier runner, no private GHA,
no external services, no app assets, no image push, no artifact upload, no
private host data. `contents:read`, network-disabled test container with
explicit CPU/memory/PID limits. Runtime hook overhead, accuracy on real apps,
UIA/MSAA completeness, graphics performance, accessibility and gaming
compatibility are **unqualified** until separately measured. Preserve
`SemperSupra/agent-dispatch-private#515` and WineBot CI/security/WinInspect
PR gates. No public PR, merge, release or production substitution.

## Baton
Inspect the Actions run triggered by this experimental branch, record exact
SHA/run/job IDs and first failing step/class in private
`mark-e-deyoung/winebot-research#1`. If red, repair the minimal fixture or
capture mechanism and rerun on the experiment branch. Keep all red signals.
No future handoff should claim a Wine source patch was implemented here:
**the first step is intentionally a no-patch experiment.**
