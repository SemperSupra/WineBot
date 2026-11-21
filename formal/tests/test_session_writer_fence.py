"""Deterministic two-process session-fencing blue/red model tests.

Source-level RDTE only: no production WineBot lock, process or guest effects.
"""

import unittest
from collections import deque
from dataclasses import dataclass, replace

TARGETS = ("B", "C")


@dataclass(frozen=True)
class State:
    epoch: int = 1
    owner: str = "A"
    holder: int = -1
    phase: tuple[int, int] = (0, 0)  # 0 ready, 1 observed, 2 completed
    seen: tuple[int, int] = (0, 0)
    stale_commit: bool = False


def changed(values: tuple[int, int], index: int, value: int) -> tuple[int, int]:
    result = list(values)
    result[index] = value
    return (result[0], result[1])


def blue_actions(s: State):
    for i in range(2):
        if s.holder == -1 and s.phase[i] == 0 and s.epoch < 3:
            yield f"acquire_{i}", replace(
                s, holder=i, phase=changed(s.phase, i, 1),
                seen=changed(s.seen, i, s.epoch),
            )
        if s.holder == i and s.phase[i] == 1:
            if s.seen[i] == s.epoch:
                yield f"commit_{i}", replace(
                    s, holder=-1, owner=TARGETS[i], epoch=s.epoch + 1,
                    phase=changed(s.phase, i, 2),
                )
            yield f"crash_{i}", replace(
                s, holder=-1, phase=changed(s.phase, i, 2),
            )


def unsafe_actions(s: State):
    for i in range(2):
        if s.phase[i] == 0:
            yield f"read_{i}", replace(
                s, phase=changed(s.phase, i, 1),
                seen=changed(s.seen, i, s.epoch),
            )
        if s.phase[i] == 1:
            yield f"write_{i}", replace(
                s, owner=TARGETS[i], epoch=s.seen[i] + 1,
                phase=changed(s.phase, i, 2),
                stale_commit=s.stale_commit or s.seen[i] != s.epoch,
            )


def explore(next_actions, invariant):
    initial = State()
    q = deque([(initial, ())])
    visited = {initial}
    while q:
        state, actions = q.popleft()
        if not invariant(state):
            return actions, visited
        for action, next_state in next_actions(state):
            if next_state not in visited:
                visited.add(next_state)
                q.append((next_state, actions + (action,)))
    return None, visited


class SessionWriterFenceTests(unittest.TestCase):
    def test_fenced_two_processes_cannot_stale_commit_or_overlap(self):
        def invariant(s: State):
            held = [i for i, phase in enumerate(s.phase) if phase == 1]
            return (
                not s.stale_commit
                and len(held) <= 1
                and (not held or held[0] == s.holder)
                and (s.epoch > 1 or s.owner == "A")
            )

        counterexample, states = explore(blue_actions, invariant)
        self.assertIsNone(counterexample)
        self.assertGreater(len(states), 5)
        self.assertTrue(any(s.epoch == 3 for s in states))

    def test_unfenced_read_then_write_has_real_stale_epoch_counterexample(self):
        counterexample, states = explore(unsafe_actions, lambda s: not s.stale_commit)
        self.assertIsNotNone(counterexample)
        self.assertIn("read_0", counterexample)
        self.assertIn("read_1", counterexample)
        self.assertIn("write_0", counterexample)
        self.assertIn("write_1", counterexample)
        self.assertGreater(len(states), 5)

    def test_explicit_old_writer_cannot_commit_after_new_owner(self):
        # Unsafe interleaving: two workers first accept owner A generation 1.
        s = State()
        s = dict(unsafe_actions(s))["read_0"]
        s = dict(unsafe_actions(s))["read_1"]
        s = dict(unsafe_actions(s))["write_0"]
        self.assertEqual((s.owner, s.epoch), ("B", 2))
        s = dict(unsafe_actions(s))["write_1"]
        self.assertTrue(s.stale_commit)
        self.assertEqual((s.owner, s.epoch), ("C", 2))
        # A missing CAS permits replay of generation 2 without increment.


if __name__ == "__main__":
    unittest.main()
