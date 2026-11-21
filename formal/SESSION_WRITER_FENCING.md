# Two-writer session ownership and generation fencing (RDTE, unimplemented)

## Current source seam and release significance
The MVP integration `api/routers/lifecycle.py` uses a module-local
`session_transition_lock = asyncio.Lock()` while `resume_session()` reads and
writes the durable active session pointer, user profile link, broker state
and paired transition journals. `api/server.py::lifespan` similarly relinks
the profile and replays an interrupted operation during startup. An async
lock cannot coordinate independent Python processes sharing a session root.
This is a source-rooted risk, **not** an observed production multi-worker
failure or proof that two workers are deployed today.

`formal/tla/SessionHandover.tla` models one writer and crash recovery; it
does not prove cross-process linearizability. Metadata parent-directory
`fsync` in qualified #176 proves more durable individual renames, **not**
atomic commits across several files or processes.

## Proposed nonnegotiable invariants
1. Exactly zero or one mutating process owns one shared persistent WineBot
   session/control root at a time. Read-only clients connect to that owner.
2. An unavailable, contended or unsupported lock fails closed **before** any
   startup, profile-link, instance metadata, Wine or broker mutations.
3. Every ownership change requires a persisted generation token read under
   the exclusive lease; a stale observed epoch cannot commit or roll it back.
4. After crash the next admitted owner either reconciles paired intent,
   active pointer, profile and broker, or quarantines. Never silently
   acknowledges two ACTIVE owners.
5. POSIX `flock` alone is not a distributed lock or storage-fencing system.
   Each deployment's file-lock semantics, mount sharing and process
   namespaces require explicit qualification. Do not admit unsupported
   network/shared volumes or multiple hosts.
6. STOP_NOW remains an unconditional human veto; already-delivered X11,
   Wine/AHK events and independent process groups remain separate obligations.

## Blue/red model contract
`SessionWriterFence.tla` models **proposed** single-holder acquisition and
epoch-checked owner updates; an interrupted holder releases without logical
commit. `SessionWriterFenceUnsafe.tla` models two independent workers
reading A@1 and committing different targets without a CAS. TLC must find
the `NoStaleWrite` counterexample, not merely fail to parse the model.
`formal/tests/test_session_writer_fence.py` enumerates the same bounded
interleavings independently with only the Python standard library.

These tests prove properties of the **abstract protocols only**. They do
not show that current runtime code enforces an OS lock or generation CAS.

## Sequential implementation / acceptance plan
1. Qualify a source-bound secure process-lifetime admission lock in a
   disposable public Linux worker using two genuine competing processes,
   SIGKILL/restart, no symlink following, restrictive permissions, fixed
   safe lock path on the shared persistent control root and negative tests.
2. Bind that admission at the start of API lifespan, *before* any persistent
   mutations. Keep FD custody through shutdown; guard other mutator paths
   and reject multiple workers until safely partitioned.
3. Add explicit persisted monotonically advancing generation/operation-id
   CAS and revalidate while holding the lease. Extend restart/intent
   reconciliation under the same admission, including unmatched orphans.
4. Run crash-point and two-worker interleaving tests with a reproducible
   synthetic session tree, then source-exact public Wine 11 GUI workloads.
5. Require all exact-head CI/TLC/negative controls, frozen API contracts,
   source review, root/mount custody, safe redacted receipts, and explicit
   owner promotion before hardware/production release.

No production guard is implemented by this RDTE workcell. No private
WinInspect source, secrets, user files or paid/private runners are needed.
The release is NOT_READY_FOR_HARDWARE_TEST; WinInspect-private #468 native
qualification and WineBot #166 actual read-only HWND acceptance remain
independent blocked gates.

DLE: Durable = source and CI receipts tied to exact commits; Legible = this
model/refinement gap and negative counterexample; Executable = concrete
implement/qualify/admit sequence, no hidden manual waiver.
