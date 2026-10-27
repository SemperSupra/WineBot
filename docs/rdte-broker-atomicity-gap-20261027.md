# Broker integration qualification boundary (research only)

Observed in api/core/broker.py at base 0ce6d71d:
InputBroker owns a threading.RLock and mutable state.session_id and
state.lease_expiry. Its get_state() is a snapshot accessor; it is not
an atomic collector-generation admission API. ObserverService uses two
independent callbacks for active session and broker session, and enforces
one start per session. A broker state read followed by a separate
generation admission can race with session update, lease revocation,
and lease expiry.

Integration design requires broker-held serialization of (1) session
identity, (2) active owner/grant and expiry, (3) monotonic lease epoch,
(4) collector generation admission/revocation. Do not equate session_id
with authenticated ownership or an agent grant. Preserve one-start-per-
session, fail-closed revocation and no same-session restart.

Before production work: inspect control-state model and grant semantics,
add bounded expiry/revoke/renew/ABA/rollback fixtures, and prove lock
ordering and no deadlocks. The current SyntheticBrokerLeaseCell is
a test double, not the real broker contract. Keep review and release
gates closed.
