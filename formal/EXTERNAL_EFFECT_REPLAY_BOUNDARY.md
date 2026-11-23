# External guest effects: crash/replay and STOP boundary — R040

## The missing atomic transaction

Protected Go owner CAS and root-owned controller flock can serialize
control-plane state. They cannot, by themselves, atomically commit
an arbitrary Windows application's external effect and a separate
supervisor ledger acknowledgment. If the supervisor crashes after an
effect and before its acknowledgment, blindly retrying may repeat it.

The stdlib Python BFS in formal/tests/test_external_effect_replay.py
uses a bounded 12-step horizon. The UNSAFE variant requires the
exact witness: prepare -> effect -> crash -> restart -> effect again.
The CONDITIONAL SAFE variant assumes the target itself atomically
records a deduplication operation ID together with its effect; it
checks at-most-once application and STOP blocking any new effect.
STOP cannot roll back effects which were already applied.

These are abstract source models, NOT TLC, NOT a Wine/Windows test,
NOT a proof of the runtime or a guarantee of exactly once for any
uncooperative proprietary Windows application.

## Operational release rule

Classify every cross-layer action into:
(1) read-only observation;
(2) idempotent effect with target-owned operation-ID proof;
(3) non-retryable attempt requiring reconciliation when outcome UNKNOWN.

Without target-side idempotency, never silently retry potentially
effectful guest operations following a timeout, controller crash,
or ambiguous acknowledgment. Human STOP must fence admission at
the same boundary as the effect; already in-flight work needs
explicit UNKNOWN accounting until trustworthy completion evidence.

This experiment cannot close the independent guest-UID1000 writer
lock inode replacement issue or prove SO_PEERCRED production isolation.
