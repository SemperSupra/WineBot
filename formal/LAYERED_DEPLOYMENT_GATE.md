# Layered deployment-gate R1 — cooperative same-host admission

## Why two separate locks

WineBot's runtime keeps `/artifacts/sessions/.winebot-active-writer.lock`
throughout its process lifetime (one admitted state writer). The one-shot
`state-init` now uses this same runtime lock, but releases it before the
Compose runtime can acquire it. That gap permits a second stack to initialize
state and win a race to start. We do **not** claim a seamless transfer of the
runtime lock FD across containers.

An **independent deployment gate** instead takes an exclusive, nonblocking
flock on `/state/artifacts/sessions/.winebot-deployment-gate.lock` and
**retains the open file description** for the entire lifetime of a small,
isolated OCI service. Both `state-init` and `winebot-interactive` depend
on the gate's health, which is only declared after lock admission. As the
controller stays alive across service startup, a second conforming Compose
project with the same external artifacts volume cannot start its own
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
attestation still need host-level qualification. Deployment gate currently
runs root with cap DAC_OVERRIDE and artifacts RW; security review is a
specific release gate. Controller health is admission evidence, not an
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
