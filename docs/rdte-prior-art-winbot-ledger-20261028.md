# Prior-art reconciliation: WinBot SQLite recovery ledger

2026-10-28 discovery of authoritative existing private implementation:
mark-e-deyoung/WinBot draft PR #109, head
340f952fe416a27595dafc659e5ff9622bc60ee7.
Private files host/providers/libvirt_kvm_ledger.py and
tests/parity/test_libvirt_kvm_ledger.py implement a more mature
non-admitting SQLite recovery-claim ledger.

Verified source properties: BEGIN IMMEDIATE, WAL, synchronous FULL,
transactional generation issuance and supersession, one-use consume,
replay rejection after reopening, crash-before-commit rollback,
exclusive ownership/permissions, symlink and WAL sidecar custody.
Its tests explicitly deny treating claim consumption as lease or
mutation authorization.

This WineBot branch's sqlite_epoch_store_rdte.py duplicates a narrow
subset (BEGIN IMMEDIATE, FULL sync, monotonic counter, concurrency,
rollback). Do not promote this duplicate as a separate authoritative
persistence layer. Retain only as a minimal public research comparator
until cross-project contract reuse is reviewed.

Private source custody: do not copy private WinBot implementation or
test data to public WineBot, public Actions, or other public surfaces.
A reviewed sanitized interface contract can be independently authored
without projecting private source. Existing private PR remains draft.

Next: compare semantics and define provider-neutral epoch store
interface; identify ownership and authorized publication path; prove
real broker admission and crash recovery separately. Do not claim
the WinBot recovery ledger authenticates WineBot observer leases.
