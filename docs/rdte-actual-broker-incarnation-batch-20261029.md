# WineBot actual InputBroker session-incarnation candidate — 2026-10-29

This is a bounded, source-backed **research branch**, deliberately separate from actual service/registry lifecycle qualification. Parent: `qualification/actual-observer-service-20261029@da21e2c92679b948dea615fdd43c0e980e5c23ab`. Owner: WineBot DLE #1.

## Scope and algorithms

Existing `InputBroker._lock` is an RLock protecting ControlState updates and detached deep snapshots. Add an in-memory integer `_observer_incarnation` incremented inside the **same critical section** on every `update_session`, including identical string names. The candidate `get_observer_session_snapshot()` returns an immutable `(session_id, incarnation)` pair while holding the same lock. There is no external route, process launch, kill, feed, registry cleanup or consumer contract change. The method explicitly provides **observation**, never authorization.

Adversarial public tests import the actual InputBroker class and check initial invalid/unknown incarnation, same-name ABA, immutable prior snapshot, concurrent session update vs three readers (no mixed session/incarnation pair), and detached original ControlState snapshot. This is intentionally *not* an admission or resource-side fencing test.

## Critical negative evidence

The integer starts over after process restart and may repeat after SQLite restore, rollback, or replacement. This is insufficient as a durable or cross-process lease, and must NOT be reused to authorize observer start/stop/cleanup. It does not resolve the user's already discovered split `_active_session` / `_broker_session` callbacks, unless that full boundary is redesigned to consume one immutable, externally validated identity. The existing private WinBot #109 ledger is separate prior art; none is copied into public source.

Independent sequence before promotion: (G0) source custody and immutable contract reviewed; (G1) actual-service and broker witnesses; (G2) genuinely atomic, mutation-boundary owner record and resource-side incarnation fence; (G3) race/crash/rollback tests; (G4) actual Wine under zero-cost public ephemeral runner; (G5) human owner acceptance. Security/disclosure #515, production, merge and release are held. Three audiences share truthful unauthorised/unavailable information; no agent-only privilege or new UI is implemented.
