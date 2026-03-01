# Invariants

This document is the canonical registry of correctness invariants for WineBot.

## Lifecycle invariants

1. A `oneshot` session in `completed` state is terminal and cannot be resumed.
2. A `completed` session cannot be suspended.
3. Suspend/resume/shutdown transitions must be idempotent under repeated requests.
4. Session handover (`resume` into a new target) must either complete or roll back without partial active-session state.

Code:
- `api/routers/lifecycle.py`
- `api/utils/files.py`

Tests:
- `tests/test_lifecycle_hardened.py`
- `tests/test_invariants.py`

## Control invariants

1. Human priority is absolute: agent never takes control in effective `human-only`.
2. In interactive mode, agent control requires an active lease.
3. In `agent-only`, active controller must be `AGENT`.
4. User input and `STOP_NOW` revoke agent control.

Code:
- `api/core/broker.py`
- `api/routers/control.py`

Tests:
- `tests/test_policy.py`
- `tests/test_lifecycle_hardened.py`
- `tests/test_invariants.py`

## Configuration invariants

1. `MODE=headless` cannot run with effective `human-only`.
2. `MODE=headless` + effective `hybrid` is blocked unless `WINEBOT_ALLOW_HEADLESS_HYBRID=1`.
3. `BUILD_INTENT=rel-runner` cannot run with `MODE=interactive`.

Code:
- `api/core/config_guard.py`
- `api/server.py` (startup admission)
- `api/routers/control.py` (runtime admission)

Tests:
- `tests/test_config_guard.py`
- `tests/test_profile_matrix.py`
- `tests/test_invariants.py`

## Persistence invariants

1. Critical state files are written atomically (`fsync` + `replace`) and fail closed on IO errors.
2. Critical state writes are not silently ignored.
3. Runtime temporary state files used for atomic commits are non-hidden and cleaned up after replace.

Code:
- `api/utils/files.py`

Tests:
- `tests/test_invariants.py`

## Runtime invariant observability

Endpoint:
- `GET /health/invariants`

Behavior:
- Returns `ok=false` and structured violations when runtime invariant checks fail.
- `/health` includes `invariants_ok` and degrades status when violations are present.
