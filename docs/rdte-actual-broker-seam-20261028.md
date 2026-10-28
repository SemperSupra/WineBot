# Actual broker/observer admission seam — 2026-10-28

Source read: api/core/broker.py and api/core/wine_events_service_rdte.py.
The real InputBroker serializes many operations using RLock and
get_state() deep-copies ControlState. It does not expose durable
generation or incarnation fields in the observed source. ObserverService
checks active_session() and broker_session() separately and uses a
last-started-session string. These are distinct, potentially racy
observations, not an atomic fencing admission.

Production changes are blocked until a reviewed admission contract
provides a single broker-authorized (session, owner, incarnation,
generation) snapshot and the observer validates that tuple at the
actual process resource boundary. Never infer authority from a
session-name match alone. The private WinBot SQLite recovery ledger
is non-admitting prior art, not a drop-in observer lease.

A read-only source-contract test was added. No production broker,
observer, or process lifecycle behavior was changed. CI for this
work cell is not established unless a run receipt is independently
observed. Next: fix any import/dependency issues in isolated tests,
then build an intentionally-red actual-broker stale-owner oracle
before implementing the reviewed atomic admission seam.
