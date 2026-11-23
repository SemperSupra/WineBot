"""Finite control-plane/guest-effect model: synthetic counterexample only.

Durable owner CAS cannot make a separate Windows effect exactly once
across a supervisor crash. The safe variant assumes target idempotence.
"""
import unittest
from collections import deque
from dataclasses import dataclass, replace


@dataclass(frozen=True)
class State:
    generation: int = 0
    prepared: bool = False
    crashed: bool = False
    stopped: bool = False
    effect_count: int = 0
    target_seen: bool = False
    retry_pending: bool = False
    acked: bool = False

def successors(s: State, *, idempotent_target: bool):
    if not s.prepared and not s.stopped:
        yield "prepare_durable_generation", replace(s, prepared=True, generation=1)
    if s.prepared and not s.crashed and not s.stopped and not s.acked:
        if s.effect_count == 0 or s.retry_pending:
            if idempotent_target and s.target_seen:
                yield "replayed_target_dedup", replace(s, retry_pending=False)
            else:
                yield "guest_effect_applied", replace(
                    s, effect_count=min(2, s.effect_count + 1),
                    target_seen=idempotent_target, retry_pending=False,
                )
        if s.effect_count > 0:
            yield "ack_durable", replace(s, acked=True)
        yield "supervisor_crash", replace(s, crashed=True)
    if s.crashed:
        yield "supervisor_restart", replace(s, crashed=False, retry_pending=True)
    if not s.stopped:
        yield "human_stop", replace(s, stopped=True, generation=s.generation + 1)

def explore(*, idempotent_target: bool, max_steps: int = 12):
    initial = State()
    queue = deque([(initial, ())])
    visited = {initial}
    while queue:
        current, trace = queue.popleft()
        if current.effect_count > 1:
            return visited, trace
        if len(trace) >= max_steps:
            continue
        for name, next_state in successors(current, idempotent_target=idempotent_target):
            if next_state not in visited:
                visited.add(next_state)
                queue.append((next_state, trace + (name,)))
    return visited, ()

class ExternalEffectSafety(unittest.TestCase):
    def test_atomic_target_dedup_required_for_at_most_once(self):
        states, witness = explore(idempotent_target=True)
        self.assertGreater(len(states), 10)
        self.assertFalse(witness, witness)
        self.assertTrue(any(s.acked and s.effect_count == 1 for s in states))
        self.assertTrue(all(s.effect_count <= 1 for s in states))

    def test_cas_only_has_crash_replay_duplicate_witness(self):
        _, witness = explore(idempotent_target=False)
        self.assertEqual(witness, (
            "prepare_durable_generation",
            "guest_effect_applied",
            "supervisor_crash",
            "supervisor_restart",
            "guest_effect_applied",
        ))

    def test_stop_blocks_future_effect_after_restart(self):
        for idempotent in (True, False):
            for state in explore(idempotent_target=idempotent)[0]:
                if not state.stopped:
                    continue
                for label, child in successors(state, idempotent_target=idempotent):
                    self.assertNotEqual(label, "guest_effect_applied")
                    self.assertEqual(child.effect_count, state.effect_count)
                    self.assertTrue(child.stopped)

if __name__ == "__main__":
    unittest.main()
