# WineBot generation-bound cursor: isolated synthetic RDTE (2026-10-27)

Authority: https://github.com/mark-e-deyoung/winebot-research/issues/1
Parent: qualification/wine-events-soak-20261026 at 8aba752a2f70d27f4f0867104673fb78a4956780.

The parent already has TWO qualified 70-second Wine/Xvfb soak receipts: Actions 40269929279 and 40270342318. Do not re-run those as cursor evidence.

## Research objective and minimal cut

The current EventBridge exposes an unversioned integer source cursor.
One-start-per-session currently prevents unsafe same-session restarts; it must
remain enforced. After a new process resets sequence to 1, an old integer
cursor cannot distinguish the old collector from its replacement.

The new local-only rdte/wine11/generation_cursor_rdte.py wraps an already
trusted, synthetic EventBridge and issues a fresh random collector-generation
identity per view. It does not start Wine, select windows, attach to the
production registry, provide HTTP input, change auth tokens or alter shared
contracts. Closing one view erases only its own owned synthetic bridge.

## Minimal version-1 cursor

Exactly four fields:

- version: strict integer 1, not boolean
- session: local fixture identity [A-Za-z0-9_-], 1 to 64 chars
- generation: opaque lower-case 32-hex-digit discriminator, not a credential
- sequence: strict nonnegative source sequence integer

The read response has fixed schema winebot.wine.cursor.v1, a fixed state, a list
of privacy-minimized events, and next_cursor only when state is ready.
Unqualified source failures may provide a fixed allowlisted reason.

States: ready, not_ready, unavailable, invalid_cursor, session_mismatch,
stale_generation, history_gap, unqualified.

A stale-generation cursor must never resume at the sequence=1 of a
replacement collector. Lost history returns history_gap instead of silently
resynchronizing. Invalid, closed, gap or overflow conditions never return
buffered event content or an advanced cursor.

Security limitation: a trusted caller must authenticate and authorize the
session separately. A cursor is not a bearer token, tamper-proof signature or
process-ownership lease. No per-actor identity, web route, persistent catalog,
external ingestion or operational deployment is implied or authorized.
Fresh system randomness separates views, but this experiment intentionally
does not implement automatic restart or process recovery.

## Three-audience contract

Human-facing and assistive interfaces should distinguish history unavailable,
collector replaced, stream not ready and unqualified status truthfully;
accessible UI implementation is NOT tested.

Automation consumes the same deterministic states, exact source sequence
checks and bounded limits without parsing raw titles, images or logs.

Agents receive the identical visibility, but no privileged process
selection, new actuation endpoint, concealed replay or mutation permission.

## Red/blue-team qualification

The stdlib-only test_wine_generation_cursor_rdte.py tests: schema/version,
multi-page reads, concurrent human/automation/agent readers, generation
replacement with source sequence reset, cross-session and stale rejection,
malformed and forged fields, future sequence, retention gap, before-ready,
source gap and terminal overflow erasure, close/ownership semantics,
construction validation and output fields.

No network, external binaries, production data, HIL, private runner or paid
compute. The new branch-only wine-events-generation-cursor-rdte.yml workflow
runs pure Python under a pinned checkout action, read-only repository
permissions, no artifacts or image publication. Require the exact source head
and a terminal Actions job before recording hosted PASS. Synthetic unit
success does not establish real Wine semantics or native Windows parity.

## Next bounded actions

1. Record exact workflow head, terminal job, first failure and attached
   artifact enumeration in DLE #1.
2. Design trusted collector-owner allocation and atomic broker lease
   binding, with explicit expiry, erasure and no stale cursor replay.
3. Qualify a newly admitted session under real Wine with separate generations,
   preserving same-session restart OFF.
4. Independently address per-actor authorization, UIA/accessibility, explicit
   capability discovery, immutable container image identity and CPU/RSS.
5. Preserve security/disclosure authority
   https://github.com/SemperSupra/agent-dispatch-private/issues/515,
   legacy conformance RED, WinInspect, review, owner and release holds.

RDTE ONLY: no production merge, public endpoint, release or deployment.
