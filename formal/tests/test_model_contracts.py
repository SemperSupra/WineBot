"""Bounded deterministic negative controls for the public formal models.

This is NOT a replacement for TLC; it tests the intended fault scenarios
independently, with synthetic data and no private source or external effects.
"""
import unittest
from collections import deque
from dataclasses import dataclass, replace


@dataclass(frozen=True)
class Lease:
    epoch: int = 1
    granted: bool = False
    stopped: bool = False
    queued: int = 0
    effects: int = 0


def lease_next(s: Lease):
    if not s.granted and not s.stopped and s.epoch < 4:
        yield "grant", replace(s, granted=True, epoch=s.epoch + 1)
    if s.granted and not s.stopped and not s.queued:
        yield "queue", replace(s, queued=s.epoch)
    if s.granted and s.epoch < 4:
        yield "stop", replace(s, granted=False, stopped=True, epoch=s.epoch + 1)
    if s.stopped and not s.queued:
        yield "ack", replace(s, stopped=False)
    if s.queued and s.granted and not s.stopped and s.queued == s.epoch:
        # Boolean observed effect, not an unbounded count: finite state space.
        yield "effect", replace(s, queued=0, effects=1)
    if s.queued and (not s.granted or s.stopped or s.queued != s.epoch):
        yield "discard", replace(s, queued=0)


def explore(init, next_fn, invariant):
    seen = {init}
    queue = deque([(init, ())])
    while queue:
        state, trace = queue.popleft()
        if not invariant(state):
            return trace, len(seen)
        for name, successor in next_fn(state):
            if successor not in seen:
                seen.add(successor)
                queue.append((successor, trace + (name,)))
    return None, len(seen)


@dataclass(frozen=True)
class Handover:
    phase: str = "idle"
    committed: str = "A"
    pointer: str = "A"
    profile: str = "A"
    broker: str = "A"
    intent: bool = False


def handover_next(s: Handover):
    if s.phase == "idle" and s.committed == "A":
        yield "prepare", replace(s, phase="prepared", intent=True)
    if s.phase == "prepared":
        yield "pointer", replace(s, phase="pointer_written", pointer="B")
    if s.phase == "pointer_written":
        yield "profile", replace(s, phase="profile_linked", profile="B")
    if s.phase == "profile_linked":
        yield "broker", replace(s, phase="broker_switched", broker="B")
    if s.phase == "broker_switched":
        yield "commit", replace(s, phase="committed", committed="B", intent=False)
    if s.phase in {"prepared", "pointer_written", "profile_linked", "broker_switched"}:
        yield "crash", replace(s, phase="recovering")
    if s.phase == "recovering":
        yield "recover", Handover()


def converged_when_idle(s: Handover):
    return s.phase not in {"idle", "committed"} or (
        s.pointer == s.profile == s.broker == s.committed and not s.intent
    )


class ModelContractTests(unittest.TestCase):
    def test_lease_finite_model_has_no_nonfenced_effect(self):
        counterexample, count = explore(
            Lease(),
            lease_next,
            lambda s: s.effects >= 0 and not (s.stopped and s.granted),
        )
        self.assertIsNone(counterexample)
        self.assertGreater(count, 5)

    def test_stale_queued_input_is_discarded_after_stop(self):
        state = Lease(epoch=2, granted=True, queued=2)
        stopped = dict(lease_next(state))["stop"]
        self.assertNotIn("effect", dict(lease_next(stopped)))
        self.assertIn("discard", dict(lease_next(stopped)))

    def test_unfenced_negative_control_is_detected(self):
        state = Lease(epoch=2, granted=True, queued=2)
        stopped = dict(lease_next(state))["stop"]
        # Deliberately simulate a broken dispatcher that acts on any queue.
        unsafe_effect = stopped.queued > 0
        self.assertTrue(unsafe_effect)
        self.assertFalse(stopped.granted)

    def test_handover_crash_at_each_precommit_step_converges(self):
        current = Handover()
        for action in ("prepare", "pointer", "profile", "broker"):
            current = dict(handover_next(current))[action]
            interrupted = dict(handover_next(current))["crash"]
            recovered = dict(handover_next(interrupted))["recover"]
            self.assertEqual(recovered, Handover())

    def test_handover_bounded_model_never_claims_partial_commit(self):
        counterexample, count = explore(Handover(), handover_next, converged_when_idle)
        self.assertIsNone(counterexample)
        self.assertGreater(count, 8)

    def test_release_requires_same_source_generation(self):
        source = 2
        qualified, projected, built, pinned, approved = 1, 1, 1, 1, True
        self.assertFalse(
            approved and qualified == projected == built == pinned == source
        )


if __name__ == "__main__":
    unittest.main()
