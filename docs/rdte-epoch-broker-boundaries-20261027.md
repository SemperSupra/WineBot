# Lease epoch research boundary

The synthetic EpochBroker serializes lease and generation admission under
one lock. Tests cover expiration, regrant fencing, revocation, renewal,
concurrent single-winner admission, and malformed input. It deliberately
does not expose an HTTP API or integrate into the production InputBroker.

Open risks: a process restart resets the in-memory epoch counter; durable
monotonic fencing is not established. Identity strings are test fixtures,
not authenticated principals. A wall-clock lease in production must be
reconciled with monotonic timing and persistence. Production grant semantics
and cross-process fencing require a separate reviewed contract.

Owner gates: no merge, no release, no real user sessions, no credentials.
