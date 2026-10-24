#!/usr/bin/env python3
"""Public-safe, synthetic-only regression suite for the Wine event adapter probe.

In particular, a >131-byte JSONL stream must not be truncated by readlines(131).
No real application data, paths, Win32 handles or runner details are printed.
"""
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[2]
SCRIPT = ROOT / "scripts" / "ci" / "verify-wine-event-roundtrip.py"
MODULES = ROOT / "rdte" / "wine11"


def record(kind, sequence, **extras):
    return json.dumps({
        "schema": "winebot.wine.event.v1",
        "kind": kind,
        "sequence": sequence,
        **extras,
    }, separators=(",", ":")).encode("utf-8") + b"\n"


GOOD_STREAM = b"".join((
    record("ready", 0),
    record("create", 1),
    record("show", 2),
    record("location", 3),
    record("hide", 4),
))


class RoundtripTests(unittest.TestCase):
    def check_stream(self, content, expected_success):
        with tempfile.TemporaryDirectory(prefix="wine-event-test-") as folder:
            source = Path(folder) / "events.jsonl"
            source.write_bytes(content)
            env = dict(os.environ)
            env["PYTHONPATH"] = str(MODULES)
            result = subprocess.run(
                [sys.executable, str(SCRIPT), str(source)],
                env=env,
                capture_output=True,
                text=True,
                timeout=15,
                check=False,
            )
            if expected_success:
                self.assertEqual(result.returncode, 0, "synthetic roundtrip unexpectedly failed")
                self.assertIn("PASS: live_wine_event_adapter_ingest", result.stdout)
                self.assertIn("PASS: live_wine_event_cursor_readback", result.stdout)
                self.assertIn("PASS: live_wine_event_close_clears_state", result.stdout)
            else:
                self.assertNotEqual(result.returncode, 0, "invalid stream was accepted")
                self.assertIn("FAIL:", result.stdout)
            # Never echo untrusted events; only fixed, allowlisted verdict lines.
            self.assertNotIn('"schema":', result.stdout)
            self.assertNotIn('"kind":', result.stdout)

    def test_longer_than_131_bytes_must_not_truncate(self):
        self.assertGreater(len(GOOD_STREAM), 131)
        self.check_stream(GOOD_STREAM, True)

    def test_source_gaps_rejected(self):
        self.check_stream(b"".join((
            record("ready", 0),
            record("show", 1),
            record("location", 3),
        )), False)

    def test_missing_semantics_rejected(self):
        self.check_stream(record("ready", 0) + record("show", 1), False)

    def test_extra_raw_identifiers_rejected(self):
        self.check_stream(b"".join((
            record("ready", 0),
            record("show", 1, hwnd="sensitive"),
            record("location", 2),
        )), False)

    def test_unbounded_file_rejected(self):
        self.check_stream(GOOD_STREAM + (b" " * 24_577), False)

    def test_too_many_lines_rejected(self):
        content = record("ready", 0)
        content += b"".join(record("location", n) for n in range(1, 131))
        self.check_stream(content, False)

    def test_invalid_utf8_rejected(self):
        self.check_stream(GOOD_STREAM + b"\xff\n", False)

    def test_partial_terminal_line_rejected(self):
        self.check_stream(GOOD_STREAM.rstrip(b"\n"), False)


if __name__ == "__main__":
    unittest.main()
