# Persistent active-owner pointer across disposable WineBot runtimes (RDTE)

## Reproduced source distinction — 2026-11-22
- `api/utils/files.py:47` binds `SESSION_FILE` to `/tmp/winebot_current_session`.
  `read_session_dir()` reads that ephemeral file; `write_session_dir()`
  commits **only** that path, although it fsyncs that particular directory.
- `scripts/init/10-setup-infra.sh` selects a new session when neither
  `WINEBOT_SESSION_DIR` nor `WINEBOT_SESSION_ID` is supplied, and writes
  the active pointer to the same `/tmp` location.
- `api/core/handover_recovery.py` replays only the **active** session's
  durable intent marker. After a fresh container loses the `/tmp` pointer,
  the persisted session tree may still contain old transaction markers
  that the new default-session startup does not discover or reconcile.
- The source-safe TLA+ `SessionHandover` assumes an abstract authoritative
  pointer survives crash. That property is **not refined to** the existing
  /tmp-only code across disposable container replacement.

This is an independently source-verified *risk*, not evidence of a specific
user production failure. It directly affects the required disposable
runtime/application/persistent data architecture.

## Red/blue qualification
`PersistentSessionOwnerUnsafe.tla` demonstrates prepare durable intent,
lose the volatile pointer, and invent a new owner with a stranded journal.
The expected counterexample is `NoOrphanAtRest` violated; parsing errors
or other failure codes must not count as counterexamples.

`PersistentSessionOwner.tla` models a **proposed** persistent committed
owner and a volatile cache that is rebuilt from it; only a reconciled
owner may report READY. Independent Python stdlib graph search covers
both cases with no local Wine, private code, or user content.

## Required sequential production correction
1. Under the qualified **early entrypoint lease** (#184), choose a versioned
   persistent control-root owner pointer (e.g., a dedicated file under the
   admitted `WINEBOT_SESSION_ROOT`), with strict root, permissions,
   symlink rejection and bounded schema/identity. Never infer active from
   arbitrary directory mtime/lexical order.
2. Make `resume` changes generation-fenced/compare-and-swap, write a
   durable owner record atomically (tempfile fsync, rename, dir fsync),
   and preserve old `/tmp` pointer only as a derived compatibility cache.
   Specify crash order of both marker files, stable committed owner,
   profile relink, broker state and journal cleanup.
3. Before shell/guest/session mutation on new container startup, read the
   committed owner under the same lease, match a valid root-local
   session path, reconcile *all reachable corresponding* prepared intent
   markers, or **quarantine** on orphan/conflicting markers. Do not silently
   create a new session or trust a stale `/tmp` pointer.
4. Prove crash at each write/sync/rename/profile/broker stage using two
   disposable instances sharing the same persistent volume, including
   SIGKILL, stale generations, corrupted pointer and absent peer marker.
   Qualify exact-source Wine11 real guest, native GUI and frozen contracts.
5. Review throughput/latency, storage mount semantics, reader/worker
   authority and fail-closed error surfaces before promotion. The
   formal abstraction alone is **NOT READY** for hardware or release.

Independent from WinInspect-private native v0.5/cloud admission #468/#561.
No paid compute, private Actions minutes or source projection.
DLE = Durable (exact SHA+receipts), Legible (red/blue counterexamples),
Executable (gated source-to-runtime refinement plan).

## Source-only storage primitive workcell (#186)
The isolated `api/core/persistent_owner.py` introduces a strict version-1
one-file persistent owner record under the already admitted session root,
with monotonically advancing generation and explicit operation identity.
Its compare-and-swap acquires the same `writer_admission` lease, validates
root/session identity, refuses symlinks, unknown schema or corrupted data,
and writes through the established tempfile fsync → replace → parent fsync
primitive. Replay of the same operation/generation is idempotent; stale
generations and operation-ID reuse are denied. Synthetic tests include two
real competing Python processes and injected parent-directory fsync failure.

**Not integrated:** none of `docker/entrypoint.sh`, `api/routers/lifecycle.py`,
`api/server.py` or the legacy `/tmp` pointer is changed by this workcell.
No immediate product behavior or recovered active owner is claimed.
Integration follows release-accepted early admission #184 and must cover
the source-to-model mapping, root mount/permission handling, paired
handover journals, replay/quarantine and actual guest behavior.
