# WineBot large-batch execution plan — 2026-10-31

Authoritative owner decisions and evidence remain in private WineBot DLE #1. This document is a public-source-safe work breakdown, not permission to merge or release.

## Workcell A — native package and installer (current writer: batched-native-package-matrix)
- Native Win32 x86 and x64 real-binary build and PE-machine check.
- SHA256 manifest, side-by-side v1/v2 staged install, real fixture launch, uninstall isolation, overwrite/tamper negatives.
- Reparse-path tests on separate existing hardening branch.
- Pending: actual ZIP-to-installer path, package path/case collisions, malicious manifest/TOCTOU, rollback and Win11 prefix install.
- Gate: no release until package contract and negative tests qualified on both platforms.

## Workcell B — pinned Wine11 runtime (separate writer)
- Reuse exact pristine Wine 11.0 source hash and existing successful source-build run 41199060529; avoid rebuilding Wine per test.
- In one eligible runner job: install package into disposable Wine prefix, current collector fixture, 12x teardown, overflow >=129, bounded event delivery, resource/timeout receipts, no artifact upload.
- Wine9 historical comparator only. No false cross-runtime feature parity.

## Workcell C — portable observation/WinInspect (separate writer)
- Versioned observer.portable.v0 reference exists with Linux+Windows offline conformance run 41199835065.
- Add two independent cursors, producer/session epoch and explicit gaps; two-target ambiguous events must not be falsely correlated.
- Trusted local target_ref/target_epoch bridge under G0; WinInspect additive read-only provider and protocol owner gate; preserve legacy events.poll and private source.
- Gate: no target-aware claim without identity, no private code copied to public branch.

## Workcell D — actuation/security/three audiences (separate writer)
- Standalone CLI design + EN/DE/TH Unicode fixtures, stable JSON errors and capability discovery.
- Pure negative reference tests for stale lease, ABA, unauthorized principal, concurrent agents, outcome_unknown, no mutation.
- Actual input/control only after WinBot #110 desktop lease, G0 security #515 and G2 broker-registry atomic fencing. Never treat observer cursor or target_ref as actuator authorization.

## Dependencies / concurrency

A, B, C, D can run in separate worktrees/branches concurrently, one writer per workcell. A package contract must stabilize before B's installed-binary tests. C target identity and D authorization must both pass before any live targeted actuation. Integration demonstration sequence: build -> package -> install -> observe -> WinInspect attach -> verified reinspection -> stop -> uninstall. No merge/release/deploy absent owner gate.

## Evidence and custody

Each batch should carry exact source commit, pinned dependencies, runner job, first failure, correction, capability matrix, resource bounds, and next DLE baton. Git/DLE for source and compact evidence; Google Drive only for approved larger binary deliverables with provenance and access controls. Public free GHA runners for public synthetic source only, no private minutes and no binary upload.
