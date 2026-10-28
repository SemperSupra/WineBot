# WinInspect corrective integration ordering — 2026-10-28

Live PR facts:
- WineBot PR 124 fixes WinInspect portable pin to v0.4.4 and proposed
  SHA-256 6ac0a65f774ffe69672f1c459254931ebfddb1e52c9fbec14b5db1348ccaad04.
  The hash is a PR candidate, not independently reverified here.
- PR 141 (redaction) is based on fix/wininspect-rpc-protocol-030-20261024,
  not main. Its preflight failure logs show checksum mismatch for v0.4.0,
  before redaction tests could establish a result.
- PR 136 (semantic bridge) is based on main. Its real Wine diagnostic
  is response_id_mismatch. Upstream WinInspect PR 18 has successful
  x64/ARM64 jobs but is unmerged.

Corrective sequence:
1. Independently verify trusted release asset v0.4.4 and SHA-256 from
   approved provenance, and qualify PR 124 in an isolated checkout.
2. Retest PR 141 against the corrected asset pin, preserving its base
   dependency and ensuring the redaction test actually executes.
3. Qualify upstream PR 18 real protocol behavior, then integrate the
   reviewed upstream fix into a source-pinned WinInspect build.
4. Run PR 136 semantic bridge in actual Wine, with protocol version,
   correlation, loopback and redaction checks. Do not silently accept
   absent or mismatched IDs.
5. Review 134/138/139/141 as overlapping dependency changes. Retire
   redundant branches only after evidence and owner approval.

Independent parallel lanes: release checksum provenance, redaction unit
oracle, upstream protocol qualification, broker persisted epoch tests.
Sequential: trusted asset -> redaction build; upstream transport ->
real Wine integration; both -> integration review. No merge/release.
