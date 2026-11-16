#!/usr/bin/env python3
"""Adversarial source-neutral save-transaction contract tests."""

import bz2
import gzip
import importlib.util
import lzma
import tempfile
import unittest
from pathlib import Path

spec = importlib.util.spec_from_file_location("freeciv_save_oracle", Path(__file__).with_name("save_oracle.py"))
oracle = importlib.util.module_from_spec(spec)
spec.loader.exec_module(oracle)


def fixture(turn=4, year=-3000, phase=0, state="S_S_RUNNING", players=2):
    result = ("[savefile]\nformat=" + '"3"' + "\n[game]\n"
              + f'turn={turn}\nyear={year}\nphase={phase}\nserver_state="{state}"\nsave_players=TRUE\n')
    for n in range(players):
        result += f"[player{n}]\nname=\"source-known-test\"\n"
    return result


class SaveOracleContracts(unittest.TestCase):
    def test_extract_known_fields_without_sensitive_details(self):
        data = oracle.game_fingerprint(fixture())
        self.assertEqual(data["turn"], 4)
        self.assertEqual(data["year"], -3000)
        self.assertEqual(data["player_sections"], 2)
        self.assertNotIn("name", data)

    def test_roundtrip_equivalent_fields(self):
        self.assertTrue(oracle.compare_fingerprints(oracle.game_fingerprint(fixture()),
                                                     oracle.game_fingerprint(fixture())))

    def test_roundtrip_turn_change_rejected(self):
        self.assertFalse(oracle.compare_fingerprints(oracle.game_fingerprint(fixture()),
                                                      oracle.game_fingerprint(fixture(turn=5))))

    def test_roundtrip_player_loss_rejected(self):
        self.assertFalse(oracle.compare_fingerprints(oracle.game_fingerprint(fixture()),
                                                      oracle.game_fingerprint(fixture(players=1))))

    def test_duplicate_state_field_rejected(self):
        with self.assertRaisesRegex(ValueError, "DUPLICATE_GAME_FIELD"):
            oracle.game_fingerprint(fixture() + "[game]\nturn=9\n")

    def test_missing_game_state_rejected(self):
        with self.assertRaises(ValueError):
            oracle.game_fingerprint("[game]\nturn=1\n")

    def test_invalid_integer_rejected(self):
        with self.assertRaisesRegex(ValueError, "NONINTEGER_GAME_STATE"):
            oracle.game_fingerprint(fixture(turn="injected"))

    def test_invalid_state_enum_rejected(self):
        with self.assertRaisesRegex(ValueError, "INVALID_GAME_STATE_ENUM"):
            oracle.game_fingerprint(fixture(state="FORGED"))

    def test_xz_gzip_bz2_bounded_decoders(self):
        with tempfile.TemporaryDirectory() as d:
            raw = fixture().encode()
            for extension, compress in (("xz", lzma.compress), ("bz2", bz2.compress), ("gz", gzip.compress)):
                p = Path(d, "test.sav." + extension)
                p.write_bytes(compress(raw))
                self.assertEqual(oracle.bounded_save_text(p), fixture())

    def test_expanded_size_limit(self):
        with tempfile.TemporaryDirectory() as d:
            p = Path(d, "zipbomb.sav.xz")
            p.write_bytes(lzma.compress(b"a" * (oracle.MAX_EXPANDED + 1)))
            with self.assertRaisesRegex(ValueError, "SAVE_EXPANSION_EXCEEDS_BUDGET"):
                oracle.bounded_save_text(p)

    def test_symlink_rejected(self):
        with tempfile.TemporaryDirectory() as d:
            real = Path(d, "real.sav")
            real.write_text(fixture())
            link = Path(d, "linked.sav")
            link.symlink_to(real)
            with self.assertRaisesRegex(ValueError, "INVALID_SAVE_BOUNDARY"):
                oracle.bounded_save_text(link)

    def test_invalid_duplicate_game_section_rejected(self):
        with self.assertRaises(ValueError):
            oracle.game_fingerprint(fixture() + "[game]\n")


if __name__ == "__main__":
    unittest.main()
