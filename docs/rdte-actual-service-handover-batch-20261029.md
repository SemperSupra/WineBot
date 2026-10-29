# Actual service handover — 2026-10-29 bounded batch

Source authority: WineBot DLE #1 and `qualification/actual-observer-service-20261029@da21e2c92679b948dea615fdd43c0e980e5c23ab`. Actual first-failure witness and scoped shutdown correction previously qualified at Actions 40914343938. This is an isolated follow-up, not an authorization to merge or release.

## Hardening tests and invariants
The tests import actual `ObserverService`, `SessionObserverRegistry`, and `EventBridge`. Only the fixed Wine subprocess owner is replaced with a bounded synthetic fixture to exercise deterministic races. Verify that no-owner shutdown cannot erase a foreign bridge, late stale owner stop cannot erase a successor bridge even if the session string is reused, cross-session handover cannot erase a successor, shutdown is idempotent and permanently disables admission, and a synchronized competing replacement remains intact after shutdown.

Preserve `clear_if_owner(session_id, bridge)` object identity as the one existing local cleanup fence. The test does **not** prove atomic broker admission, resource-side fence, cross-process durable epoch, process-group termination, real Wine compatibility or genuine agent/human separation. Retain G0–G5 review gates, owner acceptance and disclosure #515. No private source in the public branch.

Execute existing service/registry/source regressions together in **one public GHA batch** and inspect the exact SHA, job conclusion, logs, first failure and artifacts. Do not claim a failed or missing workflow as qualified. No merge or release.
