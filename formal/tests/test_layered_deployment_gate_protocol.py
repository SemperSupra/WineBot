"""Bounded exhaustive interleaving check for cooperative local deployment admission.

A finite abstract state machine, NOT a proof of Linux flock, Docker
health delivery, host mount identity, file permissions or hostile writers.
"""
from collections import deque
from dataclasses import dataclass, replace
import unittest

INITIAL = ("new", "new")


@dataclass(frozen=True)
class State:
    gate: int = -1
    writer: int = -1  # -1 free, 0/2 init, 1/3 runtime
    phases: tuple[str, str] = INITIAL
    interleaved: bool = False


def set_phase(s: State, i: int, phase: str, **changes) -> State:
    phases = list(s.phases)
    phases[i] = phase
    return replace(s, phases=tuple(phases), **changes)


def transitions(s: State, *, unsafe_release: bool):
    for i in range(2):
        phase = s.phases[i]
        other = 1 - i
        if phase == "new" and s.gate == -1:
            yield f"p{i}:acquire_gate", set_phase(s, i, "leased", gate=i)
        if phase == "leased" and s.gate == i and s.writer == -1:
            yield f"p{i}:begin_init", set_phase(s, i, "initializing", writer=2*i)
        if phase == "initializing" and s.writer == 2*i:
            yield f"p{i}:finish_init", set_phase(
                s, i, "prepared", writer=-1,
                interleaved=s.interleaved or s.phases[other] == "prepared",
            )
        if phase == "prepared" and s.gate == i and s.writer == -1:
            yield f"p{i}:runtime_admission", set_phase(
                s, i, "running", writer=2*i+1,
            )
        if phase == "running" and s.gate == i:
            yield f"p{i}:release_gate_after_runtime", replace(s, gate=-1)
        if phase == "running" and s.writer == 2*i+1:
            yield f"p{i}:runtime_exit", set_phase(
                s, i, "stopped", writer=-1,
                gate=-1 if s.gate == i else s.gate,
            )
        if s.gate == i and phase in ("leased", "prepared"):
            yield f"p{i}:controller_crash", set_phase(
                s, i, "aborted", gate=-1,
            )
        if s.gate == i and phase == "initializing":
            yield f"p{i}:controller_crash_during_init", set_phase(
                s, i, "init_aborted", gate=-1,
            )
        if phase == "init_aborted" and s.writer == 2*i:
            yield f"p{i}:aborted_init_exit", set_phase(
                s, i, "aborted", writer=-1,
            )
        if s.gate == i and phase == "running":
            yield f"p{i}:controller_crash_after_runtime", replace(
                s, gate=-1,
            )
        if unsafe_release and s.gate == i and phase == "prepared":
            yield f"p{i}:UNSAFE_release_gate_before_runtime", replace(
                s, gate=-1,
            )


def explore(*, unsafe_release: bool, max_depth: int = 14):
    start = State()
    q = deque([(start, ())])
    seen = {start}
    while q:
        state, trace = q.popleft()
        if state.interleaved:
            return seen, trace, state
        if len(trace) >= max_depth:
            continue
        for label, next_state in transitions(
            state, unsafe_release=unsafe_release,
        ):
            if next_state in seen:
                continue
            seen.add(next_state)
            q.append((next_state, trace + (label,)))
    return seen, (), None


class GateModelTest(unittest.TestCase):
    def test_admitted_gate_prevents_interposed_initializer(self):
        states, trace, violation = explore(unsafe_release=False)
        self.assertGreater(len(states), 15)
        self.assertIsNone(violation, trace)
        for state in states:
            for i, phase in enumerate(state.phases):
                if phase in ("leased", "initializing", "prepared"):
                    self.assertEqual(state.gate, i)
                if phase == "initializing":
                    self.assertEqual(state.writer, 2*i)
                if phase == "running":
                    self.assertEqual(state.writer, 2*i+1)

    def test_early_gate_release_exposes_interposed_initializer(self):
        _, trace, violation = explore(unsafe_release=True)
        self.assertIsNotNone(violation)
        self.assertTrue(
            any("UNSAFE_release" in step for step in trace)
        )
        self.assertEqual(len(trace), 7)
        self.assertIn("begin_init", trace[-2])
        self.assertIn("finish_init", trace[-1])


if __name__ == "__main__":
    unittest.main()
