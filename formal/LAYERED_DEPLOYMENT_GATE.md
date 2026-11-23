# Layered deployment-gate R1 — cooperative same-host admission

## Why two separate locks

WineBot's runtime keeps `/artifacts/sessions/.winebot-active-writer.lock`
throughout its process lifetime (one admitted state writer). The one-shot
`state-init` now uses this same runtime lock, but releases it before the
Compose runtime can acquire it. That gap permits a second stack to initialize
state and win a race to start. We do **not** claim a seamless transfer of the
runtime lock FD across containers.

An **independent deployment gate** instead takes an exclusive, nonblocking
flock on `/winebot-control/.winebot-deployment-gate.lock` in an independent
root-owned external control volume that is not mounted into the runtime and
**retains the open file description** for the entire lifetime of a small,
isolated OCI service. Both `state-init` and `winebot-interactive` depend
on the gate's health, which is only declared after lock admission. As the
controller stays alive across service startup, a second conforming Compose
project with the same external protected control volume cannot start its own
`state-init` even in the gap between initial setup and WineBot runtime lock.

## State machine / linearization points

`Absent → GateHeld → StateInit → RuntimeAdmission → Running → Stopped`.

- The gate's successful kernel `flock` is the deployment-serialization
  point for compliant Compose projects on one Linux host, one local mount.
- Only after the gate is healthy can init change volume owner metadata.
- Init separately takes the *runtime writer lock* before mutations; its exit
  releases that short-lived lock.
- Runtime obtains the same runtime writer lock **while gate remains held**.
- Rival deployment gate rejects immediately with `lock_contended` and its
  dependent init is not eligible to start.
- Runtime stays guarded by its runtime writer lock even if the deployment
  gate later dies. A different gate may start, but its state-init will then
  fail to acquire the runtime writer lock.
- Gate restart uses a persisted lock inode but never unlinks it. Kernel
  process exit releases the OFD, requiring fresh admission.

## Threat/operational limits — release BLOCKED

This is cooperative same-host Linux flock behavior, *not* a Byzantine
filesystem or consensus algorithm. It requires all mutating deployments to
use this Compose dependency graph and both locking components. Operators
using `docker run` without the controller, malicious same-UID writers,
a privileged host attacker, compromised/multi-host NFS, independent
uncoordinated orchestrators, and state owners pointing at mismatched
external mounts are out of model. Filesystem path identity + OCI digest
attestation still need host-level qualification. Deployment gate is root-owned but has no DAC_OVERRIDE capability and
only mounts its protected control volume RW. Host volume custody, root
namespace and guest mount denial require independent security review. Controller health is admission evidence, not an
authenticated long-lived lease or an atomic cross-layer mutation.

Persistent-owner pointer CAS is **not yet wired** to restart flow. A passing
two-gate race test does not imply such pointer activation, human STOP
priority, native Windows/WinBot equivalence, WinInspect v0.5 acceptance,
or promotion authorization.

## Qualification

`scripts/ci/qualify-disposable-layers.sh` tests real isolated gates
competitively on synthetic Docker external volumes, tests release and
reacquire and existing state replay. Full `wine11-disposable-layer-hil.yml`
tests two distinct Compose projects with a real source-built Wine11 runtime,
then existing competing initializer, extended soak, WM recovery, SIGKILL
and durable user-state replay. Both are public disposable CI only; no
real host state or private data. Never merge on source-only green.

## R2 protected-controller correction (2026-11-23)

This is a **partial** remedy for the same-UID lock-file substitution
counterexample recorded in draft #210. The controller now holds its
long-lived deployment-gate lock inside a dedicated, root-owned mode-0700
external volume. Its Compose service is the ONLY service that mounts
`control-plane`; neither runtime nor one-shot state-init mounts it.
The controller has all Linux capabilities dropped and no network. An
unprivileged Wine UID1000 cannot unlink the controller's lock even if a
synthetic test explicitly mounts its control volume into another
unprivileged container; real Wine has no such mount.

**DO NOT CALL THIS PRODUCTION-SECURE:** the separate runtime writer
lock is *still* in `/artifacts/sessions`, which is guest-writable.
The persistent-owner CAS file remains in that same writable namespace
and is not wired into active restart. A guest may be able to subvert
that writer lock or the CAS pointer. Full release requires moving all
trusted state, generation fencing and mutation authority out of the
untrusted guest's writable namespace, with independent guest/control
process principal separation and authenticated capability-scoped IPC.
Check host mount identities, process capabilities and wrong-volume
aliasing before release. Passing the protected-controller negative
test cannot close those remaining gaps.
