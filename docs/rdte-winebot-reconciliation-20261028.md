# WineBot reconciliation and corrective-action matrix — 2026-10-28

Authority: mark-e-deyoung/winebot-research issue 1. This document is a
research-only branch work cell, not an approval to merge or publish.

## Reconciled repository state
- SemperSupra/WineBot: 18 open draft PRs at inspection. WinInspect
  integration PRs 134, 136, 138, 139, 141 overlap and must not be
  independently merged. Game/renderer PRs 132, 133, 135, 143, 144
  remain separate RDTE. Conformance/security PRs 123,124,125,127,129
  require a source-custody gate.
- SemperSupra/WinInspect: PR 18 open non-draft, candidate patch applies
  response id assignment after dispatch; PRs 19, 17, 16 and multiple
  independent experimental PRs remain open. PR 18 is not integrated.
- Research DLE issue 1 records verified green synthetic cursor, lease,
  epoch, restart negative oracle, RPC fixture and actual Wine handover.
- The qualification branches are isolated; green CI does not imply
  a production fix or authority to merge.

## Error / first-failure classification
1. response_id_mismatch: upstream core dispatch loses/changes the
   request correlation ID; WinInspect PR 18 proposes reassigning it.
   WineBot PR 141 separately prevents daemon hello identity from
   leaking into diagnostics. Treat as separate root-cause and
   containment fixes, with independent tests.
2. Observer admission race: WineBot broker has RLock, mutable
   session_id and lease_expiry; observer checks active and broker
   session via independent callbacks. A snapshot plus later collector
   admission is not a broker-atomic operation.
3. Epoch ABA after restart: in-memory counters restart from initial
   state. Synthetic shared-store oracle proves the failure condition,
   not persistence. Require durable transactional monotonic epoch,
   crash recovery, and process fencing before runtime integration.
4. Evidence/provenance: branch-only public tests qualify exact heads;
   logs and build artifacts are independent publication surfaces.
   Require exact-head job receipts, zero attached artifacts, redacted
   output, and separate tested checkout/source SHA.
5. Work-cell duplication: many draft PRs and research branches address
   adjacent issues; designate an owning PR for each capability and
   keep independent experiment branches non-promotable.

## Parallel execution lanes
A. WinInspect upstream PR 18 Windows x64/ARM64 protocol tests.
B. WineBot WinInspect PR 141 diagnostic redaction and PR 136
   read-only integration fixtures (separate runners).
C. Broker lease epoch/expiry/revoke/renew and lock-order hostile tests.
D. Persistent epoch crash/recovery oracle, separate from broker API.
E. Wine/Xvfb event observer soak, lifecycle and bounded overflow.
F. Games/CPU renderer and native-vs-Wine comparator, source-pinned.

## Sequential dependencies and release holds
1. Verify upstream PR 18 transport response correlation against
   real executable before integrating it into WineBot PR 136.
2. Verify diagnostic redaction independently; then reconcile 134,
   138, 139, 141 into one reviewed WinInspect integration contract.
3. Prove broker-held session/lease/generation atomicity and durable
   fencing before promoting synthetic observer cursor to runtime.
4. Reconcile security/disclosure issue 515 and legacy conformance RED
   before any private-to-public transfer, merge, release or deployment.
5. Owner review and explicit approval remain mandatory.

## Three audiences
Human: clear error reason, run links, session status and privacy-safe
diagnostics. Automation: stable exit codes, JSON verdict schema,
reproducible source hashes. Agent: bounded capabilities, lease epochs,
machine-readable admission denials and next-action baton.

## Next READY
Inspect CI for WinInspect PR 18 and WineBot PR 141, determine the
first actual failing job and evidence. Qualify durable persisted
epoch fencing in a separate branch. Record receipts in DLE issue 1.
No automatic merges, releases or unreviewed disclosure.
