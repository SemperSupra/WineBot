# Formal safety integration on the qualified MVP baseline

This stacked workstream starts at WineBot MVP PR #158 exact head
`9809519b94b9074ed681b297237f6dec89d43186`, not public main.
It reuses the public TLA+ finite-state specification and adversarial TLC
counterexample gates already qualified on draft PR #170. The contract
fixture for this MVP is `mark-e-deyoung/winebot-contracts@205666f7f0235cb0fc51ca8a5af84f9f67831a74`.

## Why the base is important

The public main-based conformance baseline and both main-based correction
branches produced 55 passed, 7 failed, 9 skipped tests under the same
external contract SHA; the MVP integration produced 62 passed, 0 failed,
9 skipped. The actual MVP diff contains its own control broker ownership
corrections and async input cancellation. We must not replace them with a
different main-based implementation whose assumptions and interface
disagree. PR #170 is a formal-analysis source, not an authoritative
runtime integration baseline. PR #171 remains independent and has to be
reconciled onto the MVP lifecycle code before it can be admitted.

## Refinement map

| Formal model | MVP source | Meaning of model PASS | Concrete gap |
| --- | --- | --- | --- |
| `ControlLease.tla` | `api/core/broker.py`, `api/routers/input.py` | Bounded stale queued epochs cannot execute after revocation in the abstract model | No durable cross-process epoch token; backends may finish already-delivered effects |
| `SessionHandover.tla` | `api/routers/lifecycle.py`, `api/server.py` | Abstract recovering owner converges | Startup has no verified persisted handover replay yet |
| `ReleaseAdmission.tla` | PR #158/#166, WinInspect-private #468 | Source, qualification, projection and pin belong to one source generation | Private C++ correction, approved projection, and native HWND qualification still blocked |

`ControlLeaseUnsafe.tla` must produce an invariant counterexample for
stale input after STOP_NOW. `SessionHandoverUnsafe.tla` must produce a
counterexample for split ownership after crash. Expected negative-control
counterexamples are required; a parser failure or a silent checker exit
must not masquerade as success.

## Targeted production change

MVP #158's broker already tracks/cancels asynchronous input tasks, refuses
duplicate active leases and stale handover grant challenges, and does
a final policy check near input dispatch. Its `check_access()` nonetheless
evaluated headless and agent-only shortcuts before `STOP_NOW`.
This stacked patch moves the human emergency-stop veto ahead of every
shortcut and adds tests for newly admitted headless requests and
cancellation of an outstanding synthetic task.

The retrofit changes no public contract assertions and introduces no
runtime actor, private source, paid resource or host-side input.

## Qualification and custody

- Run the imported public TLA+ v1.7.4 TLC workflow and both negative
  controls on free public GitHub-hosted Ubuntu.
- Run the owning MVP lint/unit, source-provenance, real Wine workload,
  disposable layer, and frozen external contract workflows. A green model
  alone does not authorize release.
- Keep this PR stacked on `mvp/ic1-integration-20261117` until independently
  accepted. Never merge into main or promote release without existing
  native WinInspect proof obligations.
- Preserve exact source SHA, model verdict, 62/0/9 conformance comparison,
  and counterexamples in DLE (Durable, Legible, Executable).
