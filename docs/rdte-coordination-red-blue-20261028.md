# Red/blue-team corrective gate — WineBot coordination and observer

Date: 2026-10-28. Authority: mark-e-deyoung/winebot-research#1.
Status: research-only; not approval to integrate, merge or release.

## Discover / Observe
Existing private WinBot draft PR #109 already implements a SQLite WAL
one-use recovery claim ledger with custody checks and crash-before-commit
rollback. It is NOT a lease or authorization service. The WineBot
sqlite_epoch_store_rdte.py branch is a narrow comparator, not a new
production dependency. Public CI passing does not prove runtime safety.

## Red-team attack matrix
P0:
- A holds epoch 41; B obtains epoch 42; A's delayed shutdown/revoke
  arrives after handover. Assert B's resources are unchanged.
- Persistent database deleted, replaced or restored from stale backup.
  Reject incarnation rollback; no counter reset may authorize an owner.
- Client commits grant, loses response and retries. Exactly one
  logical grant; deterministic idempotency or explicit uncertain state.
- Concurrent grant, revoke, renew and collector-start. Assert one
  linearization point and no TOCTOU after admission.
- Private-source leakage via public branch, logs, artifacts or Actions
  checkout. Fail closed; never copy WinBot private implementation.
P1:
- Collector restarts, replay duplicates, cursor gaps, slow consumer,
  journal overflow, disk-full and crash between event and checkpoint.
- Supervisor restart leaves orphaned process or kills another owner's
  process due to PID reuse.
- etcd or JetStream partition/outage creates availability failure;
  safety must remain intact.
- Test receipt references wrong SHA, branch or image provenance.

## Blue-team invariant contract
I1: resource_id, owner_id, session_id, incarnation_id, epoch and
operation_id are separately typed/validated.
I2: every externally consequential mutation validates the current
incarnation and epoch at the resource-side enforcement boundary.
I3: stale revoke/shutdown cannot affect successor resources.
I4: durable state recovery never silently resets generation or
revives consumed authorization.
I5: ambiguous commit is idempotent or returns UNKNOWN requiring
read-only reconciliation, never blind retry.
I6: events carry monotonic source generation plus per-generation
sequence; replay is deduplicated; gaps and overflow are explicit.
I7: all evidence names exact tested checkout, source provenance,
job result, artifacts and first failure.
I8: admission remains fail closed under unavailable dependencies.

## Reuse decision
Baseline: SQLite for single-host transactional state; existing broker
for policy; OS supervisor for process-tree containment; bounded local
journal for events. Defer etcd and JetStream until independent tests
show a measurable requirement that baseline cannot satisfy. Do not
copy private WinBot source into public WineBot.

## Parallel work cells
A. Contract and state-machine adversarial oracle (synthetic public).
B. Crash/recovery, replacement/backup rollback and custody test
   qualification (private or reviewed sanitized fixture).
C. Real Wine session handover and stale-shutdown enforcement probe.
D. Event replay, overflow, resource budget and consumer-cursor probe.
E. Provenance, CI disclosure and human/automation/agent usability audit.
F. Optional etcd/JetStream comparative benchmarks only after A defines
   identical workload and acceptance thresholds.

## Sequential gates
1. Review authority, private-to-public sanitation and exact contract.
2. Qualify resource-side fencing; allocation-only green is insufficient.
3. Qualify broker atomicity + persistence + process containment.
4. Qualify event integration in real Wine with bounded resource limits.
5. Resolve conformance/security RED and owner review; no automatic
   merge, release or deployment.

## Three audiences
Human: show owner, epoch, lifecycle, overflow and why operation denied.
Automation: deterministic exit codes, JSON verdicts and exact SHA.
Agent: capability-limited read/act APIs, structured denials and
executable DLE baton. All redact identity and secrets.

## Immediate next READY
Use existing source-safe tests to reproduce delayed stale shutdown
against successor session; require zero successor mutations.
Stop bespoke persistence feature expansion pending WinBot reuse review.
