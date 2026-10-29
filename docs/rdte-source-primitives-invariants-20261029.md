# WineBot source primitive and invariant audit — 2026-10-29

## Inspected source at pinned revisions
- SemperSupra/WineBot e804acb82c1df5e80c16a5dfadb155bbef4919b9:
  api/core/broker.py, api/core/wine_events_service_rdte.py,
  api/core/wine_events_process_rdte.py, api/core/wine_events_rdte.py,
  api/core/wine_events_source_rdte.py, rdte/wine11/event_bridge.py,
  rdte/wine11/sqlite_epoch_store_rdte.py.
- mark-e-deyoung/WinBot 340f952fe416a27595dafc659e5ff9622bc60ee7:
  host/providers/libvirt_kvm_ledger.py, PRIVATE source reviewed in place;
  do not reproduce or publish its implementation.
- SemperSupra/WinInspect PR #18 remains a separate source/transport
  qualification work cell; exact implementation not verified in this audit.

## Algorithms and data structures
1. InputBroker: Python threading.RLock; state mutation guarded in many
   methods; get_state deep-copies state. update_session changes session
   identity but no observed durable incarnation or epoch. revoke_agent is
   sync and does not itself acquire lock; currently used within locked
   callers, but public method calls need explicit contract review.
2. SessionObserverRegistry: RLock + (session_id, EventBridge identity);
   attach_internal closes predecessor, clear_if_owner requires both same
   session and exact bridge object identity. This is already a valuable
   stale-producer cleanup fence. HOWEVER service.shutdown calls
   registry.clear() unconditionally, so cleanup at the service boundary
   is not scoped to a specific owner. Do not replace clear_if_owner.
3. TrustedLocalEventSource: finite JSONL ingestion, 130-record budget,
   24,576-byte budget, explicit overflow sentinel, first-ready handshake.
   It checks two independent session-name callbacks; it does not bind
   an immutable incarnation/generation admission token.
4. EventBridge: bounded deque(maxlen=capacity), lock, frozen Event
   dataclass, exact schema fields, monotonic sequence, fail-closed
   invalid JSON/extra fields/sequence gap, explicit history_gap and
   overflow rejection, close erases retained events.
5. OwnedWineEventProcess: bounded selector poll loop, fixed Wine argv,
   sanitized environment, process-group shutdown; liveness uses two
   session-name callbacks, not incarnation. Stop of a specific
   subprocess is scoped by its retained process object, but process
   ownership and PID-reuse qualification remain to be tested.
6. Research SQLite epoch store: BEGIN IMMEDIATE, synchronous=FULL,
   increment then COMMIT. No cross-process owner authorization,
   incarnation binding, or resource-side fence.
7. Private WinBot claim ledger: stronger file/sidecar custody, WAL,
   synchronous FULL, BEGIN IMMEDIATE, single-use tombstones, monotonic
   generations. This is a recovery CLAIM system, not a lease or
   authorization. Only transfer reviewed public abstract contracts.

## Invariants to compose
- A resource owner is a tuple of resource identity, session identity,
  immutable incarnation, monotonic epoch, and operation identity.
- Atomic broker admission must return one consistent tuple; separate
  callback reads cannot authorize a new process.
- All start/feed/stop paths must validate that tuple at the resource
  boundary; a stale owner must not mutate a successor.
- Registry cleanup must remain bridge-identity scoped; replace the
  service-level unconditional clear only after lifecycle ownership
  semantics and tests are reviewed.
- Event sequence, cursor and gap semantics are per incarnation.
- Overflow, invalid data and uncertain durability must fail closed.
- Retained evidence must be schema-limited, source-neutral, exact-SHA,
  and safe for public GHA; private recovery ledger code stays private.

## Recommended composition sequence
A. Write actual-service no-spawn test for late shutdown and
   same-session ABA, using injected owner_factory.
B. Introduce an opaque atomic broker admission snapshot with epoch and
   incarnation under the existing broker lock, without changing
   public HTTP control semantics.
C. Bind registry, event source and process to the admission tuple,
   retaining existing EventBridge and clear_if_owner primitives.
D. Run deterministic adversarial tests (late cleanup, restart,
   duplicate start, callback reorder, overflow, replay).
E. Qualify real Wine/Xvfb in a sanitized public GHA work cell.
F. Independent source custody, security and three-audience review;
   no automatic merge/release.

## Evidence boundary
The prior two public GHA runs 40731692170 and 40731702503
qualified synthetic state-machine oracles only. No production
admission or resource-side fencing fix has been verified here.
