"""Finite owner-pointer loss vs durable restart recovery (synthetic only)."""

import unittest
from collections import deque
from dataclasses import dataclass, replace


@dataclass(frozen=True)
class Pointer:
    phase: str = "ready"
    durable: str = "A"
    volatile: str = "A"
    reported: str = "A"
    intent: bool = False


def valid_actions(s: Pointer):
    if s.phase == "ready":
        yield "prepare", replace(s, phase="prepared", intent=True)
    if s.phase == "prepared":
        yield "commit", replace(
            s, phase="committed", durable="B", volatile="B",
            reported="B", intent=False,
        )
    if s.phase in ("ready", "prepared", "committed"):
        yield "crash", replace(
            s, phase="down", volatile="none", reported="none",
        )
    if s.phase == "down":
        yield "reconcile", replace(
            s, phase="ready", volatile=s.durable,
            reported=s.durable, intent=False,
        )


def unsafe_actions(s: Pointer):
    if s.phase == "ready":
        yield "prepare", replace(s, phase="prepared", intent=True)
    if s.phase == "prepared":
        yield "crash", replace(
            s, phase="down", volatile="none", reported="none"
        )
    if s.phase == "down":
        yield "unsafe_fresh_container", replace(
            s, phase="ready", volatile="C", reported="C"
        )


def explore(actions, invariant):
    start = Pointer()
    seen = {start}
    pending = deque([(start, ())])
    while pending:
        s, history = pending.popleft()
        if not invariant(s):
            return history, seen
        for label, next_state in actions(s):
            if next_state not in seen:
                seen.add(next_state)
                pending.append((next_state, history + (label,)))
    return None, seen


class PersistentPointerModelTests(unittest.TestCase):
    def test_durable_protocol_restarts_to_one_resting_owner(self):
        def good(s):
            if s.phase in ("ready", "committed"):
                return (
                    not s.intent
                    and s.volatile == s.durable == s.reported
                )
            return True

        trace, states = explore(valid_actions, good)
        self.assertIsNone(trace)
        self.assertGreater(len(states), 6)
        self.assertTrue(any(s.phase == "ready" and s.durable == "B" for s in states))

    def test_ephemeral_only_pointer_produces_orphaned_journal(self):
        trace, states = explore(
            unsafe_actions,
            lambda s: s.phase != "ready"
            or (s.volatile == s.durable and not s.intent),
        )
        self.assertEqual(trace, (
            "prepare", "crash", "unsafe_fresh_container"
        ))
        self.assertGreater(len(states), 3)

    def test_crash_before_durable_commit_restores_previous_owner(self):
        state = Pointer()
        state = dict(valid_actions(state))["prepare"]
        state = dict(valid_actions(state))["crash"]
        state = dict(valid_actions(state))["reconcile"]
        self.assertEqual((state.durable, state.volatile, state.reported), ("A", "A", "A"))
        self.assertFalse(state.intent)


if __name__ == "__main__":
    unittest.main()
