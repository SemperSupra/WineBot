"""Bounded executable admission/recovery model, not a runtime controller."""
from collections import deque
from dataclasses import dataclass, replace

MAX_GENERATION = 3


@dataclass(frozen=True)
class State:
    generation: int = 0
    phase: str = "IDLE"
    gate_open: bool = False
    pending: frozenset[int] = frozenset()
    live: frozenset[int] = frozenset()
    proof: int = 0


def successors(s: State, *, unsafe_empty=False, unsafe_stale=False):
    """Yield (transition, state); pending launches may complete after STOP.

    A generation abstracts a unique, non-reused scope identity. The launch
    admission gate is assumed enforced by a trusted actuator, not the guest.
    Proof issuance assumes a trusted observer of both pending and live work.
    """
    g = s.generation
    if s.phase == "IDLE" and g < MAX_GENERATION:
        # Model a durable atomic reservation BEFORE the launch gate opens.
        yield "reserve", replace(s, generation=g + 1, phase="RESERVED", gate_open=True)
    if s.phase == "RESERVED" and s.gate_open:
        # One submission per generation; pending represents accepted but not
        # yet observed work, including ambiguous launch acknowledgements.
        yield "submit", replace(s, phase="RUNNING", pending=s.pending | {g})
    if s.phase in ("RESERVED", "RUNNING"):
        # In the abstract trusted actuator, gate closure is atomic with
        # quarantine. In-flight work is NOT assumed cancelled.
        for event in ("stop", "crash"):
            yield event, replace(s, phase="QUARANTINED", gate_open=False)
    for token in sorted(s.pending):
        yield "launch_complete", replace(
            s, pending=s.pending - {token}, live=s.live | {token}
        )
        yield "launch_cancel_confirmed", replace(s, pending=s.pending - {token})
    for token in sorted(s.live):
        yield "scope_reaped", replace(s, live=s.live - {token})
    if s.phase == "QUARANTINED" and not s.gate_open:
        if g not in s.live and (unsafe_empty or g not in s.pending):
            if s.proof != g:
                yield "observe_empty", replace(s, proof=g)
        if s.proof == g or (unsafe_stale and s.proof > 0):
            yield "reconcile", replace(s, phase="IDLE")
    # Proof records deliberately survive future reservations, to exercise
    # stale-generation rejection instead of assuming old proofs disappear.


def invariant(s: State):
    active = s.pending | s.live
    assert len(active) <= 1, "overlapping generation scopes"
    assert active <= {s.generation}, "old-generation work survives admission"
    assert not (s.pending & s.live), "duplicate modeled launch"
    if s.phase == "IDLE":
        assert not active, "idle without confirmed termination"
    assert s.gate_open == (s.phase in ("RESERVED", "RUNNING"))
    assert 0 <= s.proof <= s.generation <= MAX_GENERATION


def explore(**options):
    """Reach a fixed point of all states within the generation bound."""
    initial = State()
    paths = {initial: ()}
    queue = deque([initial])
    coverage = set()
    while queue:
        state = queue.popleft()
        try:
            invariant(state)
        except AssertionError as exc:
            return paths[state], str(exc), len(paths), coverage
        for event, target in successors(state, **options):
            coverage.add(event)
            if target not in paths:
                paths[target] = paths[state] + (event,)
                queue.append(target)
    return None, None, len(paths), coverage


def main():
    path, reason, count, coverage = explore()
    assert path is None, (path, reason)
    assert count > 20
    assert coverage == {
        "reserve", "submit", "stop", "crash", "launch_complete",
        "launch_cancel_confirmed", "scope_reaped", "observe_empty", "reconcile",
    }
    for options in ({"unsafe_empty": True}, {"unsafe_stale": True}):
        path, reason, _, _ = explore(**options)
        assert path is not None and reason == "idle without confirmed termination"
        assert "submit" in path and "reconcile" in path
    # Old-generation proof cannot reconcile even an actually empty scope;
    # a fresh trusted observation is required.
    stale = State(generation=2, phase="QUARANTINED", proof=1)
    assert "reconcile" not in {event for event, _ in successors(stale)}
    # STOP may be followed by completion of already accepted work. No new
    # submission, proof, or re-admission while that work remains pending.
    stopped = State(generation=1, phase="QUARANTINED", pending=frozenset({1}))
    assert {event for event, _ in successors(stopped)} == {
        "launch_complete", "launch_cancel_confirmed",
    }
    print(f"WRITER_LIFECYCLE_MODEL=PASS states={count}")
    print("PENDING_LAUNCH_AND_STALE_PROOF_NEGATIVES=CONFIRMED")


if __name__ == "__main__":
    main()
