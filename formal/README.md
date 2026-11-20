# Cross-layer formal verification — first public-safe execution slice

**Authority:** `SemperSupra/WineBot` source and owning MVP DLE PR #158. **Status:** candidate; TLC/CI evidence required before acceptance. This is not a runtime fix and does not qualify private WinInspect.

## Actual system boundaries

| Model | Source surfaces | Atomicity problem | Acceptance property |
| --- | --- | --- | --- |
| `ControlLease.tla` | `api/core/broker.py`, `api/routers/input.py`, brokered WinInspect input | check-permission vs later physical input | an old queued epoch is discarded after STOP_NOW/revocation |
| `SessionHandover.tla` | `api/routers/lifecycle.py`, `api/utils/files.py`, Wine profile link, broker | separately written pointer, profile symlink, session state, broker | crash recovery converges all ownership projections to committed session |
| `ReleaseAdmission.tla` | private WinInspect #468, approved projection receipt, public product binary, WineBot #166 | source/evidence/artifact/consumer-pin mismatch | accepted source generation matches qualification, projection, build and consumer pin |

The models intentionally do **not** assert that the current production implementation satisfies these properties. The existing `asyncio.Lock` and `threading.RLock` are in-process protections, not host/guest or crash-atomic transactions. `api/core/operations.py` is memory-only and can lose operation state on process restart. The session transition marker is a stepwise journal, not an end-to-end atomic commit. Input checking and input effect require an independently proven fencing point.

## Method and execution

- Start with finite explicit-state TLA+ safety models checked by TLC, one worker and short bounded execution per model, in the existing **public repository** on free public GitHub-hosted Ubuntu. No local/sovereign runner admission, no private source or secrets, and no paid private Actions minutes.
- TLA+ v1.7.4 `tla2tools.jar` is pinned by exact release URL **and release-published SHA-1**. SHA-1 is only a published legacy release checksum: before treating this as a production supply-chain attestation, pin a stronger independently trusted SHA-256 or signed provenance. This check verifies the known release asset, not source authenticity.
- Run `ControlLease`, `SessionHandover`, and `ReleaseAdmission` TLC invariants in one bounded static workflow. A nonzero exit, missing jar, timeout, TLA+ syntax error, state-invariant counterexample, or negative-control test failure must fail CI.
- Run separate stdlib Python fault/negative controls to ensure stale queued input and interrupted handover are detectable, and a stale artifact tuple is refused. These are scenario-level independent checks, **not** proofs against the implementation.
- Require real source-code mapping and fault injection before marking any product behavior verified. Future phases: broker epoch/fencing point; handover intent+reconciliation startup; durable operations; recording commit/replay; atomic release authority.

## Adversarial model-checker sentinel

`ControlLeaseUnsafe.tla` intentionally models the check-to-effect hazard: an agent queues input while authorized, then STOP_NOW revokes authority, but an unchecked consumer still executes the queued action. The dedicated CI negative-control step **must receive a TLC counterexample for `NoUnauthorizedEffect`**; parser errors, timeouts or unexpected successful model checks fail the build instead. This sentinel does not prove an exploitable live dispatch, only that the formal oracle rejects the bad ordering. Source review of `api/routers/input.py` shows `broker.check_access()` before later `await run_async_command()` or `await _send_keys()`; no generation token accompanies that eventual effect. Qualify an actual commit-time fencing fix separately with controlled synthetic input.

`SessionHandoverUnsafe.tla` is the companion crash-recovery negative control. It changes only the active-session pointer, crashes, then incorrectly declares the system idle without replay or compensation. TLC must find a `ConvergedAtRest` counterexample, distinguishing a source model with an actual recovery transition from one that simply assumes a clean restart. This still does not prove the Python implementation can recover; its observed marker readback/replay mechanism must be built and tested separately.

## Required invariants

**Control:** STOP_NOW invalidates queued older epochs; no agent effect may execute on an expired/superseded lease. One authoritative grant epoch; no assumption that an API's prior check atomically covers external Wine effects.

**Handover:** Only one committed session owner; after a successful commit or recovery all pointer/profile/broker projections converge; a crash mid-handover is either safely compensated or an incomplete operation is visibly recoverable. No silently succeeded partial handover.

**Release:** Every admission binds exact private source generation, reviewed projection, independently qualified public binary and WineBot consumer pin. Changing any upstream component invalidates downstream acceptance until requalified.

## State-machine scope limits and next implementation batch

This first slice deliberately abstracts remote processes and filesystem details into boolean or finite states and does not prove cross-process fencing, directory fsync, durable credentials, actual Windows Wine11 behavior, or read-only HWND identity. TLC proves only the bounded model and modeled transitions. A known-good TLC result must never be reported as WinInspect #468 C++ CTest PASS or MVP release admission.

Next implement a trace adapter from real `api/routers/lifecycle.py` checkpoints and `api/core/broker.py` to the modeled actions; inject restart/kill between `write_session_dir`, `link_wine_user_dir`, `write_session_state` and `broker.update_session` on disposable synthetic fixtures; check post-restart convergence. Test two concurrent grant/revoke/STOP_NOW actors with delayed input commit and a generation token. Never enable actual unsafe agent input as a negative control.

## Evidence and DLE reconciliation

Every run must record GitHub workflow run/job and commit SHA, TLC tool version/hash, `Spec` and invariant names, distinct/generated states, first counterexample if any, actual unit test result, and whether the verdict is `MODEL_PASS`, `MODEL_FAIL`, `NOT_RUN`, or `PRODUCT_UNQUALIFIED`. The public workflow emits fixed synthetic diagnostic markers only. Follow PR #158 and the formal-work PR for source lineage, reviews, and closure; no new scheduler or second authoritative workset.

## Concrete route interleaving — first code-to-model refinement

The source-owned test `tests/test_input_revocation_interleaving.py` uses the production `click_at` coroutine and real `InputBroker` but replaces X11 execution with a pure synthetic command fixture. A barrier suspends the window lookup **after** the first broker permission check, performs real broker `STOP_NOW` revocation and confirms access denied, then allows the route to complete. It asserts the known-bad current behavior: one later click command is still requested while `STOP_NOW` is active. This is a **red-team witness**, deliberately green only when the defect is reproducible; it must be converted into a safety assertion when the mitigation is introduced. It does not simulate a physical input event, prove an OS-level exploit, or certify a solution.

**Remediation contract:** Each asynchronous input request needs a session-scoped immutable authority token / generation, effective expiry, and a consumer-side enforcement point as close to the external effect as possible. A second check in an API route alone narrows but does not close the TOCTOU window if the called backend asynchronously queues unguarded work. Test human STOP_NOW, ordinary user override, lease expiry, session handover, delayed backend starts, process crash/restart, and possible already-in-flight input, including explicit semantics for actions that cannot be recalled. Do not make `STOP_NOW` wait indefinitely for a long-running input process. First materialize a fenced dispatcher in a separate controlled patch with safe mock effects, then qualify real native backends independently.

## Session-handover recovery evidence (source review)

In current public `api/routers/lifecycle.py`, `_write_transition_marker` writes `session.transition.json` during resume and `_clear_transition_marker` removes it after completion or caught exception. A direct source search of this file found marker writes/removals and no recovery reader of the marker at startup. The exception rollback tries to restore selected session pointer/state, but a process termination after `write_session_dir` and before profile linkage / broker update never reaches the exception handler. Thus a marker alone is not a proven restart-reconciliation protocol. Before accepting a change, add a reader/validator for the durable intent (schema, owner generation, previous and target identity), recover to a single authoritative owner on startup, and make crash injection exercise each physical write boundary and directory-sync durability. This is a code-inspection finding, not proof of an observed production crash or data loss.
