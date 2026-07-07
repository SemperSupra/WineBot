# Testing Assessment — 2026-07-07

## Current Coverage

| Category | Count | Coverage |
|:---------|:------|:---------|
| Conformance tests | 5 files | CLI contract, HTTP semantics, mDNS, OpenAPI, runtime policy |
| Invariants tests | 1 file | Session transitions, mode control, health endpoints |
| Unit tests | 30 files | API, contracts, config, discovery, environment, input, lifecycle, policy, process, profiles, recorder, telemetry, UI, winebotctl, WinInspect |
| E2E tests | 9 files | Input pipeline, dashboard, keyboard conformance, occlusion, UX quality/accessibility |
| CI policy tests | 3 files | Build intent, SBOM, dependency policy |

**Total: 44 test files**

## Conformance Testing

The existing conformance tests cover the public API surfaces:
- **HTTP semantics**: health status codes, auth, methods, version negotiation
- **CLI contract**: wb and winebotctl commands, flags, error codes
- **OpenAPI**: spec is valid JSON Schema, has operation IDs
- **mDNS**: service discovery protocol conformance
- **Runtime policy**: enforcement of control mode + session mode combinations

**Assessment**: Conformance coverage is strong for the current API surface. No additional conformance tests needed at this time.

## Formal Methods

The project tracks formal methods (TLA+, Alloy, etc.) in issue #81.

The primary state machine is the session lifecycle:
```
active → suspend → suspended → resume → active
active → shutdown → completed
```

This state machine is relatively simple (3 states, 3 transitions) and is already
verified by:
- `test_invariants.py` — parametrized tests for all valid/invalid transitions
- `test_lifecycle_hardened.py` — edge cases and concurrency
- `test_conformance_runtime_policy.py` — control mode enforcement

**Assessment**: Formal methods are not required at this stage. The existing invariants
and conformance tests provide sufficient verification. Formal methods would add value
if the state machine grows significantly (e.g., multi-instance orchestration, distributed
session management).

## Gaps

1. **No conformance test for API rate limiting** — not currently implemented
2. **No conformance test for recording format** — tests exist but not as conformance specs
3. **No performance benchmarks** — tracked separately in `.benchmarks/`

## Recommendation

The current testing strategy (conformance tests + invariants + unit tests + E2E) is
appropriate for the project's current maturity. No changes recommended at this time.
