# Repository reconciliation execution matrix — 2026-10-28

Authoritative DLE: mark-e-deyoung/winebot-research#1.
Current live inventories: WineBot 18 open PRs, WinInspect 25,
WinBot 7. Do not assume draft PRs are production-ready.

## Work cells and dependency graph
- WineBot WinInspect: PR 124 trusted portable archive checksum;
  PR 134 path resolution -> PR 138 loopback -> PR 139 RPC protocol
  -> PR 141 error redaction. PR 136 semantic bridge is a separate
  real-Wine acceptance lane and must be rebased/reconciled only after
  verified upstream WinInspect PR 18 transport correction.
- WinInspect: PR 18 response correlation has x64 and ARM64 green
  checks but is unmerged; PR 27 Wine local IPC remains experimental.
- WinBot: private PR 109 SQLite recovery-claim ledger is prior art,
  NOT an observer lease authority; PRs 106/107 address WinInspect
  v0.5.0 adapter and hello validation. Do not assume its protocol
  compatibility with WineBot v0.4.4.
- WineBot PR 123 conformance and PRs 125/127/129 evidence/security
  need explicit release and publication review.
- Game/render PRs 132/133/135/143/144 and UI PR 131/137 can be
  independently qualified but must not consume security admission
  capacity or merge without review.

## First observed failures
- WineBot PR 141 preflight: WinInspect v0.4.0 archive SHA mismatch.
  Fix trusted pin via PR 124, never disable verification.
- WineBot PR 136 real Wine: response_id_mismatch.
  Fix upstream protocol before downstream assertion changes.
- Observer: no proven resource-side broker-atomic fencing; local
  SQLite test green does not establish this.
- Duplication: new SQLite allocator overlaps private WinBot #109;
  freeze bespoke expansion and use as research comparator only.

## Parallel READY
A. Trusted asset hash provenance and redaction tests.
B. WinInspect upstream RPC/IPC qualification.
C. Synthetic delayed shutdown, ABA and crash-recovery oracles.
D. Real Wine observer handover/overflow/soak (no release).
E. Independent CPU renderer and game fixtures.
F. Three-audience and evidence/source-custody review.

## Sequential gates
1. Reconcile private prior art and approve source-safe interface.
2. Validate trusted WinInspect release pin; qualify redaction chain.
3. Validate upstream RPC; qualify downstream real Wine bridge.
4. Prove resource-side fence + atomic broker admission, then
   connect persistence and supervisor.
5. Prove actual Wine observer lifecycle and bounded event delivery.
6. Clear conformance, private/public source-custody and owner gates.
   Do not merge, deploy or release.

## Handoff
Next READY: run stale-owner synthetic fixture and inspect exact-head
job result; then replace toy Resource with actual WineBot broker/
observer seam under a reviewed contract. Tests must show successor
resources unchanged after delayed stale shutdown. Record first
failure and receipts in DLE.
