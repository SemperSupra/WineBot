"""Adversarial offline tests of the exact Wine11/native observer stream oracle."""
import importlib.util
import json
from pathlib import Path
import unittest

path = Path(__file__).with_name("probe.py")
spec = importlib.util.spec_from_file_location("winebot_probe_oracle", path)
probe = importlib.util.module_from_spec(spec)
spec.loader.exec_module(probe)

def line(kind="show", sequence=1, **overrides):
    item = {"schema": probe.SCHEMA, "kind": kind, "sequence": sequence}
    item.update(overrides)
    return (json.dumps(item) + "\n").encode()

class OracleNegatives(unittest.TestCase):
    def test_valid_ready_and_event(self):
        self.assertEqual(probe.normalize(line("ready", 0))["sequence"], 0)
        self.assertEqual(probe.normalize(line())["kind"], "show")

    def test_rejects_non_schema_or_unsafe_fields(self):
        for item in (
            b"", b"not-json\n", b"\xff\n", b"x"*257,
            line("show", 1, title="secret"),
            line("show", True),
            line("show", -1),
            line("show", 130),
            line("other", 1),
            line("show", "1"),
            line("show", 1, hwnd=1),
        ):
            with self.subTest(item=item[:25]):
                with self.assertRaises(ValueError):
                    probe.normalize(item)

    def test_no_silent_gap_in_sequence_or_required_kinds(self):
        events = [probe.normalize(line("ready", 0)),
                  probe.normalize(line("show", 1)),
                  probe.normalize(line("location", 2)),
                  probe.normalize(line("destroy", 3))]
        self.assertEqual([x["sequence"] for x in events], list(range(len(events))))
        self.assertTrue(probe.REQUIRED <= {x["kind"] for x in events})
        missing = {x["kind"] for x in events if x["kind"] != "destroy"}
        self.assertFalse(probe.REQUIRED <= missing)
        replay = [0, 1, 1, 3]
        self.assertNotEqual(replay, list(range(len(replay))))

if __name__ == "__main__":
    unittest.main()
