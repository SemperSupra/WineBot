# Same-name registry read-side review — negative witness
Base: fdb3b9445f275bea0f181510077660cfe1ef3ca5 (partial incarnation integration); this branch is test/docs/workflow-only.
Scope: actual `SessionObserverRegistry` and `EventBridge`, synthetic session identifiers and schema-controlled events, no Wine process, network endpoint, raw identifiers, private source or screenshots.

The registry currently stores `(session_name, bridge)`, not the broker incarnation. Its `session_changed` invalidation compares names only. An `s -> other -> s` transition can leave a prior `s` bridge readable if no owner teardown has occurred; this test specifically proves the weaker same-string transition behavior, *not* the full interleaving. A green test is a red-team witness of a gap, not acceptance of the vulnerability.

Independent controls: different-name transition must erase; `clear_if_owner` must protect a successor bridge. The next reviewed design must fence attach/feed/observe at a linearizable mutation/read boundary using immutable owner/incarnation authority, without holding a broker lock across Wine I/O. Existing G0/G2 and security #515 holds are unchanged. No auto-restart, merge, release, CI uploads or promotion.
