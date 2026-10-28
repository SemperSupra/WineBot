# Real Wine observer ownership review — 2026-10-28

Observed source at WineBot aba7dd157ef1f5965ba6f822a3692b325010b6e7:
- api/core/wine_events_process_rdte.py OwnedWineEventProcess._alive_session
  compares two callbacks to a string session ID. It does not carry a
  durable owner incarnation or fencing epoch.
- _stop_process sends Q then signals a new process group using the
  spawned process pid; this is local lifecycle containment, not a
  resource-side generation fence. PID reuse and late cleanup require
  explicit process ownership validation in production.
- api/core/wine_events_service_rdte.py checks active and broker session
  independently; _last_started_session is only a string.
- The fixed synthetic executable and sanitized environment are useful
  boundaries. Do not broaden to arbitrary process execution.

## Independent corrective plan
1. Keep current observer opt-in, read-only and bounded.
2. Model an opaque admission record with (session, owner, incarnation,
   epoch, resource instance). Source-of-truth broker admission must
   atomically authorize a specific observer resource incarnation.
3. Enforce the same record at start, event ingestion and stop/cleanup.
4. Inject same-session restart, delayed stop, PID reuse and callback
   interleavings in deterministic no-spawn tests.
5. Qualify real Wine/Xvfb on free public GHA only after synthetic
   counterexamples pass and source custody is reviewed.
6. Never treat this review as authority to merge, deploy or release.

This lane is independent of WinInspect portable checksum/RPC repair,
renderer/game work and the private WinBot SQLite recovery ledger.
