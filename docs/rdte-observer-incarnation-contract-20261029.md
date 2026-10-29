# Wine observer incarnation contract — draft, no release authority

## Authority and mutation boundary
Broker issues an opaque immutable incarnation on each session transition, including same-name reuse. Admission is a single broker-lock operation returning a session ID and incarnation only while the session is active. A resource owner stores the issued pair and must revalidate it at each attach/feed/publish boundary. Equality of session names alone never grants authority.

## Required invariants
1. Every session transition invalidates the previous incarnation, even s → other → s.
2. Revocation precedes successor admission and stale owners cannot clear a successor bridge.
3. No lock is held across child process spawn, process wait, I/O, or callbacks.
4. A failed or ambiguous durable commit never authorizes publication.
5. A broker restart without a verified durable epoch fails closed.
6. A service shutdown without an owner must not mutate the global registry.
7. Existing EventBridge bounds, ready handshake, cursor gaps, and overflow termination remain intact.
8. Public CI contains only synthetic fixture data and sanitized verdicts.

## Interface candidate
Broker: admit_observer(session_id) -> (session_id, incarnation) | None; validate_observer(session_id, incarnation) -> bool. No HTTP admission endpoint. ObserverService passes the immutable receipt to OwnedWineEventProcess and TrustedLocalEventSource. All mutation points check the receipt; cleanup uses registry.clear_if_owner(session, exact_bridge).

## Red-team matrix
Same-name ABA; check-then-attach interleaving; stop/attach race; stale close; restart/rollback; malformed JSONL; event overflow; process timeout; partial shutdown; no-owner shutdown; duplicate start; nested-lock deadlock.

## Release holds
This document is a contract candidate, not an implementation, merge approval, or proof of restart safety. Preserve private source custody and all owner-controlled release gates.
