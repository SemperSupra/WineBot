"""Native and negative qualification for source-known checkpoint/breakpoint witness."""

import importlib.util
import json
import shutil
import subprocess
import tempfile
import unittest
from pathlib import Path

HERE = Path(__file__).parent
spec = importlib.util.spec_from_file_location("checkpoint_bridge", HERE / "bridge.py")
bridge = importlib.util.module_from_spec(spec)
spec.loader.exec_module(bridge)


class BreakpointNativeTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        if not shutil.which("gcc") or not shutil.which("nm"):
            raise unittest.SkipTest("GCC_AND_NM_REQUIRED")
        cls.tmp = tempfile.TemporaryDirectory(prefix="checkpoint-fixture-")
        cls.bin = Path(cls.tmp.name) / "fixture"
        cls.compile(HERE / "fixture.c", cls.bin)
        cls.sha = bridge.digest(cls.bin)

    @classmethod
    def tearDownClass(cls):
        if hasattr(cls, "tmp"):
            cls.tmp.cleanup()

    @staticmethod
    def compile(src, output, pie=False):
        flags = ["-fpie", "-pie"] if pie else ["-fno-pie", "-no-pie"]
        subprocess.run(["gcc", "-std=c11", "-O0", "-fno-omit-frame-pointer", "-Wall",
                        "-Wextra", "-Werror", *flags, str(src), "-o", str(output)],
                       check=True, capture_output=True, timeout=10)

    def test_two_actual_external_breakpoints_with_pre_and_post_checkpoints(self):
        report = bridge.run(self.bin, self.sha)
        self.assertEqual(report["status"], "PASS")
        self.assertEqual(report["breakpoint_hits"], 2)
        self.assertTrue(report["child_clean_exit"])
        self.assertTrue(report["breakpoint_original_bytes_restored"])
        self.assertTrue(report["state_transition_observed"])
        self.assertNotIn("addresses", json.dumps(report).lower())

    def test_repeated_native_process_has_same_expected_state_digests(self):
        first = bridge.run(self.bin, self.sha)
        second = bridge.run(self.bin, self.sha)
        self.assertEqual(first["checkpoint_digests"], second["checkpoint_digests"])

    def test_wrong_sha_fails_closed_before_execution(self):
        with self.assertRaisesRegex(bridge.WitnessError, "BINARY_DIGEST_MISMATCH"):
            bridge.run(self.bin, "0" * 64)

    def test_symlink_input_rejected(self):
        link = Path(self.tmp.name) / "symlink"
        link.symlink_to(self.bin)
        with self.assertRaisesRegex(bridge.WitnessError, "INVALID_SOURCE_IDENTITY"):
            bridge.run(link, self.sha)

    def test_pie_without_proven_bias_refused(self):
        path = Path(self.tmp.name) / "fixture-pie"
        self.compile(HERE / "fixture.c", path, pie=True)
        with self.assertRaisesRegex(bridge.WitnessError, "NON_PIE_X86_64_ELF_REQUIRED"):
            bridge.run(path, bridge.digest(path))

    def test_wrong_actual_state_not_promoted(self):
        code = (HERE / "fixture.c").read_text().replace("controlled_state += 1;", "controlled_state += 2;")
        src = Path(self.tmp.name) / "wrong.c"
        src.write_text(code)
        wrong = Path(self.tmp.name) / "wrong"
        self.compile(src, wrong)
        with self.assertRaisesRegex(bridge.WitnessError, "CHECKPOINT_STATE_MISMATCH"):
            bridge.run(wrong, bridge.digest(wrong))

    def test_missing_known_symbol_fails_closed(self):
        code = (HERE / "fixture.c").read_text().replace("observe_after", "missing_expected_function")
        src = Path(self.tmp.name) / "missing.c"
        src.write_text(code)
        wrong = Path(self.tmp.name) / "missing"
        self.compile(src, wrong)
        with self.assertRaisesRegex(bridge.WitnessError, "MISSING_FIXTURE_SYMBOL"):
            bridge.run(wrong, bridge.digest(wrong))


if __name__ == "__main__":
    unittest.main()
