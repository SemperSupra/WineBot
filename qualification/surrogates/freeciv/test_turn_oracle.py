#!/usr/bin/env python3
"""Source-neutral failure and success controls for AI-turn qualification."""

import importlib.util
import pathlib
import sys
import tempfile
import unittest

root = pathlib.Path(__file__).parent
sys.path.insert(0, str(root))
spec = importlib.util.spec_from_file_location("freeciv_turn_oracle", root / "turn_oracle.py")
oracle = importlib.util.module_from_spec(spec)
spec.loader.exec_module(oracle)


def state(turn=1, year=-4000, players=2, running=True):
    return {"turn": turn, "year": year, "phase": 0,
            "server_state": "S_S_RUNNING" if running else "S_S_INITIAL",
            "save_players": True, "player_sections": players}


class TurnOracleContracts(unittest.TestCase):
    def test_turn_and_year_advance_and_reload(self):
        self.assertTrue(oracle.is_advanced(state(), state(2, -3900), state(2, -3900)))

    def test_same_turn_rejected(self):
        self.assertFalse(oracle.is_advanced(state(), state(), state()))

    def test_regressed_turn_rejected(self):
        self.assertFalse(oracle.is_advanced(state(turn=3), state(2), state(2)))

    def test_regressed_year_rejected(self):
        self.assertFalse(oracle.is_advanced(state(), state(2, -4100), state(2, -4100)))

    def test_reload_altered_phase_rejected(self):
        later = state(2, -3900)
        restored = dict(later)
        restored["phase"] += 1
        self.assertFalse(oracle.is_advanced(state(), later, restored))

    def test_missing_players_rejected(self):
        self.assertFalse(oracle.is_advanced(state(), state(2, -3900, 0), state(2, -3900, 0)))

    def test_missing_save_is_not_silent_success(self):
        with tempfile.TemporaryDirectory() as d, self.assertRaisesRegex(RuntimeError, "TURN_SAVE_COUNT_UNEXPECTED"):
            oracle.only_save(d, "before-turn")

    def test_multiple_save_candidates_are_rejected(self):
        with tempfile.TemporaryDirectory() as d:
            (pathlib.Path(d) / "before-turn.sav.xz").write_bytes(b"one")
            (pathlib.Path(d) / "before-turn.sav.gz").write_bytes(b"two")
            with self.assertRaisesRegex(RuntimeError, "TURN_SAVE_COUNT_UNEXPECTED"):
                oracle.only_save(d, "before-turn")

    def test_running_state_required(self):
        self.assertFalse(oracle.is_advanced(state(), state(2, -3900, running=False), state(2, -3900, running=False)))


if __name__ == "__main__":
    unittest.main()
