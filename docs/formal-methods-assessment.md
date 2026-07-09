# Formal Methods Assessment — 2026-07-09

## Current Verification Coverage

| Method | What It Covers | Strength |
|:-------|:---------------|:---------|
| Invariants tests | Session transitions, control modes, health invariants | ✅ 18 parametrized cases |
| Conformance tests (71) | HTTP API contract, 54/71 passing | ✅ 76.1% coverage |
| Lifecycle hardened tests | Edge cases, idempotency, concurrency | ✅ 12+ tests |
| E2E input tests | Keyboard/mouse pipeline | ✅ 9 E2E tests |

## State Machines in WineBot

### 1. Session Lifecycle
```
active → suspend → suspended → resume → active
active → shutdown → completed
```
**Complexity:** 3 states, 3 transitions
**Already verified by:** `test_invariants.py` (parametrized), `test_lifecycle_hardened.py`
**Verdict:** ✅ Sufficiently covered by tests — formal model not needed

### 2. Control/Broker State Machine
```
human-only:   agent NEVER controls
agent-only:   agent always controls, user can override
hybrid:       agent has lease, user can revoke
```
**Complexity:** 3 modes, 2 active controllers, leases
**Already verified by:** `test_policy.py`, `test_conformance_runtime_policy.py`
**Verdict:** ⚠️ Most complex state machine — highest value candidate for TLA+

### 3. Recording State Machine
```
idle → recording → paused ↔ recording
recording → stopping → complete
```
**Complexity:** 4 states, 5 transitions
**Already verified by:** `test_recorder_unit.py`, `test_recording_recovery.py`
**Verdict:** ✅ Edge cases tested — formal model low priority

## When Formal Methods Add Value

Formal methods (TLA+, Alloy, Lean) are most valuable when:

1. **Concurrent interactions** — multiple actors operating simultaneously
2. **Subtle edge cases** — states reachable only through specific sequences
3. **Safety-critical** — failure causes data loss or security breach
4. **Distributed state** — multiple nodes sharing state

WineBot's single-process API with session isolation reduces the need for formal
verification. The broker (human/agent arbitration) is the most concurrent component
and would benefit most from a TLA+ model.

## Recommendation: Defer

Close issue #81 as "Deferred — revisit when broker concurrency bugs emerge."

**Rationale:**
- Current test coverage (44 test files, conformance suite, invariants) is strong
- No design-level concurrency bugs have been found in practice
- A TLA+ model takes 1-2 weeks to build, validate, and map back to code
- Better to invest that time in completing the remaining 17 conformance gaps (#114)
- If a concurrency bug is found in the broker, that's the trigger to build formal models

**When to revisit:**
- If a race condition or deadlock is reported in the broker
- If distributed session management is added (multi-node orchestration)
- If WinBot introduces a dual-controller protocol with WineBot
