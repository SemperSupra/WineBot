# Red/blue team review: WineBot observer ownership, 2026-10-29

## Decision
Conditional approval for a narrow, test-first integration only.
Do not merge or release until the following P0 hazards are eliminated.

## Red-team attack matrix
P0-1 TOCTOU: validate token, then pause; successor admits; old
producer publishes or clears. Require mutation-boundary fencing.
P0-2 ABA: session name reused after restart; stale owner passes both
string callbacks. Require unique incarnation + monotonic epoch.
P0-3 SQLite rollback/backup restoration: monotonic counter moves
backward. Require durable authority incarnation and recovery refusal;
never treat a counter alone as globally unique.
P0-4 Service.shutdown unconditional registry.clear() can erase a
replacement bridge. Preserve registry.clear_if_owner(session,bridge);
scope service cleanup to its own bridge.
P0-5 Process survives revoke: cancel is advisory. Revoke publication
authority synchronously; terminate only owned process, bounded wait.
P1-1 Deadlock: broker lock held across registry lock or process join.
Specify lock ordering, no blocking operations under broker lock.
P1-2 Ambiguous commit: crash after commit before acknowledgment.
Use operation IDs and idempotent read/reconcile, not blind retry.
P1-3 Event cursor ABA: old cursor reused against new stream. Bind
cursor and event sequence to incarnation, explicit history_gap.
P1-4 Overflow, malformed JSON, source failure: fail closed, erase
partial events, preserve enum-only failure receipt.
P1-5 Public CI disclosure: no private source, tokens, raw events,
screenshots or uncontrolled artifacts.

## Blue-team design corrections
- Reuse InputBroker RLock for short atomic admission snapshots.
- Use frozen (resource,session,owner,incarnation,epoch,operation) record;
  validate against authoritative current state at each protected mutation.
- Avoid broker/registry nested locks: define a resource-owned admission
  gate that couples compare-and-mutate under one short critical section,
  or prove a stable lock order with adversarial tests.
- Preserve EventBridge bounded deque, exact schema, source sequence
  checks, explicit gaps, and registry bridge-identity clear_if_owner.
- Avoid unconditional service-level registry clear after successor
  admission; cancel/erase only the owned bridge.
- Separate process termination from publication authorization.
- Treat private WinBot SQLite CLAIM ledger as prior art, not a lease;
  no private-source copying to public GHA.
- Keep WinInspect checksum/RPC and renderer/game lanes independent.

## Verification gates
G0 source-custody review and contract acceptance.
G1 intentionally failing actual-service no-spawn tests:
late stop, same-session ABA, callback interleaving.
G2 minimal atomic admission and resource-side fencing fix.
G3 deterministic concurrency/crash/replay/overflow qualifications.
G4 real Wine/Xvfb synthetic fixture on free public GHA.
G5 independent security, three-audience UI/UX/DX, owner acceptance.
No merge, release or production deployment implied by CI PASS.

## Evidence boundaries
Prior GHA runs 40731692170 and 40731702503 passed synthetic
ownership oracles only. This review is a design assessment, not
verification that production defects are repaired.
