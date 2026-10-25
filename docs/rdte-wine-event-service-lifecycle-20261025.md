# RDTE: WineBot synthetic observer bound to the actual API lifespan

2026-10-25. Status: experiment, **NOT PRODUCTION ADMITTED**.
DLE: https://github.com/mark-e-deyoung/winebot-research/issues/1

## Discover and Observe

The independently qualified baseline comprises:

- Existing public Debian Wine read-only WinEvent hook,
  synthetic X11 fixture and session-local EventBridge: GHA 40075822335 PASS.
- Source-built unmodified Wine 11 WoW64 and complete
  WinEvent→EventBridge: GHA 40076089386 PASS.
- Token/session-bound GET-only WineBot API candidate, 11 tests,
  plus 10 trusted local source tests and 3 app startup tests:
  GHA 40150194533 PASS.
- Disposable derived image with actual API import/startup:
  GHA 40150322980 PASS.
- Fixed-command Wine observer process on real Wine/Xvfb with cleanup,
  restart and session handover: GHA 40158835591 PASS (13 unit cases and
  6 live allowlisted PASS receipts, 0 attached artifacts).

Those receipts did not prove that the **actual WineBot API lifespan**
would own the process, reconcile active sessions, and stop it at shutdown.
This is the next falsification lane.

## Plan and Apply

The isolated candidate \`qualification/wine-events-service-lifecycle-20261025\`
adds:

- \`OwnedWineEventProcess.request_stop\`: cooperative one-way
  cancellation; process poll and cleanup stay bounded, no SIGKILL to
  unrelated process groups.
- \`api/core/wine_events_service_rdte.py\`: internal singleton
  supervisor; requires **both** \`WINEBOT_WINE_EVENTS_RDTE_ENABLED=1\`
  and \`WINEBOT_WINE_EVENTS_PROCESS_RDTE_ENABLED=1\`, a real nonempty
  \`API_TOKEN\`, hardcoded fixture-class observer binary at
  \`/opt/winebot/rdte/win_event_observer.exe\`, preexisting Wine
  prefix, matching active filesystem and broker session. Starts at most
  one observer per session and rejects missing/mismatched/unsafe state.
- \`api/server.py\` lifespan glue: constructs/adopts supervisor only
  with the two flags and token, starts the admitted owner, checks for
  newly admitted sessions inside the existing bounded resource monitor,
  and requests shutdown during app termination.
- \`tests/test_wine_events_service_rdte.py\`: explicit flags,
  missing token/binary/prefix, broker mismatch and exception rejection,
  correct creation and once-per-session behavior, new session handover,
  owner shutdown and cleanup.
- \`tests/test_wine_events_server_lifespan_rdte.py\`: real FastAPI
  TestClient startup/shutdown hooks under patched synthetic filesystem
  context, both opt-in and default-off.
- A further disposable public-base image builds real API runtime
  dependencies, pinned synthetic Win32 observer and GUI fixture,
  Xvfb / disposable Wine prefix, and directly executes the API
  TestClient against live Wine callbacks. The test issues authenticated
  GETs and checks actual show/location before the API lifespan ends.

No HTTP producer endpoint, arbitrary program choice, control grant,
write method, screenshot, model/vision data, persistent event logs,
shared contract change, or physical/personal machine access.

## Verify and stop conditions

Workflow \`.github/workflows/wine-events-service-lifecycle-rdte.yml\`
is isolated to this experimental branch:

1. Static stage: 8 supervisor tests, 2 real FastAPI lifespan tests,
   13 existing process owner cases, 10 source cases, 11 read-only API
   cases and 3 import/mount cases — 47 independent positive/adversarial
   checks. Actual job evidence is needed before declaring PASS.
2. Real substrate: build disposable public-base image, network-disabled
   runtime, no artifact or image uploads; exercise Wine fixture events
   from authenticated API GET, wrong token/cross-session denials, and
   shutdown state erasure. Output consists only of fixed PASS/FAIL
   classifications; raw application frames are not printed.
3. If red, locate first phase and fix only an isolated branch. Do not
   merge, publish, relax schema, suppress known failures, or assert
   accessibility/graphics/real application parity from this test.
4. If green, seek independent security/source-custody review of
   external actor authorization (shared instance API token is not
   per-actor), real WCAG/AT/UIA semantics, CV pixel-ground-truth
   correlation, WinInspect semantic RPC readiness, general application
   stress and game/CPU renderer qualification.

## Release gate and known constraints

- The Win32 observer deliberately watches **only** synthetic class
  \`WB_RDTE_WINDOW\`, and expires after ~12 seconds. It cannot serve
  as a general-purpose accessibility observer without further design.
- The service starts once per session and does not auto-restart an
  expired owner in the same session. Therefore this qualification is
  an integration proof, **not** continuously available production
  observation.
- The runner uses a public WineBot-base **tag**, not an independently
  recorded immutable digest. Pinning digest is required for
  reproducible A/B comparisons.
- Independent WinInspect PR #136 remains red from RPC response ID.
  WinInspect upstream PR #18 already proposes that correction but
  has not been merged/promoted.
- Existing WineBot v1 conformance and
  \`SemperSupra/agent-dispatch-private#515\` source/privacy gates
  remain open; no merge, production deployment or release is permitted.
