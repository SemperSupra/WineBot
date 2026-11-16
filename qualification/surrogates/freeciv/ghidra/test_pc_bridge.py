#!/usr/bin/env python3
"""Adversarial source-neutral pointer mapping tests; no original game required."""
import importlib.util
import json
import shutil
import subprocess
import sys
import tempfile
import types
import unittest
from pathlib import Path

# The live runner provides the sibling ELF module. Local isolated unit tests
# use a no-op import stub because only the native integration calls that helper.
if not (Path(__file__).resolve().parent.parent / "elf_map_probe.py").exists():
    sys.modules["elf_map_probe"] = types.ModuleType("elf_map_probe")
spec = importlib.util.spec_from_file_location("pc_bridge", Path(__file__).with_name("pc_bridge.py"))
bridge = importlib.util.module_from_spec(spec)
spec.loader.exec_module(bridge)


def fixture(path, digest="a" * 64, ranges=None, functions=100):
    if ranges is None:
        ranges = [[4096 + j * 16, 4104 + j * 16, j + 1] for j in range(functions)]
    x = {"schema": bridge.INTERVAL_SCHEMA, "artifact_sha256": digest, "image_base": 1048576,
         "function_count": functions, "intervals": ranges}
    Path(path).write_text(json.dumps(x), encoding="utf-8")


class PcBridgeContracts(unittest.TestCase):
    def test_exact_schema_and_correct_identity(self):
        with tempfile.TemporaryDirectory() as d:
            path = Path(d, "functions.json")
            fixture(path)
            arr = bridge.load_intervals(path, "a" * 64)
            self.assertEqual(len(arr), 100)
            self.assertEqual(bridge.classify_elf_pc(0x71000000 + 4097, 0x71000000, arr,
                                                    [(0, 4096, 2000, 5)]), "FUNCTION_MATCH")

    def test_wrong_hash_cannot_match(self):
        with tempfile.TemporaryDirectory() as d:
            path = Path(d, "functions.json")
            fixture(path)
            with self.assertRaisesRegex(bridge.PCError, "IDENTITY_MISMATCH"):
                bridge.load_intervals(path, "b" * 64)

    def test_deliberately_wrong_bias_rejected(self):
        with tempfile.TemporaryDirectory() as d:
            path = Path(d, "functions.json")
            fixture(path)
            intervals = bridge.load_intervals(path, "a" * 64)
            self.assertEqual(bridge.classify_elf_pc(0x71000000 + 4097, 0x71002000, intervals,
                                                    [(0, 4096, 2000, 5)]), "OUTSIDE_IMAGE")

    def test_outside_function_not_promoted(self):
        with tempfile.TemporaryDirectory() as d:
            path = Path(d, "functions.json")
            fixture(path)
            intervals = bridge.load_intervals(path, "a" * 64)
            self.assertEqual(bridge.classify_elf_pc(0x71000000 + 4108, 0x71000000, intervals,
                                                    [(0, 4096, 2000, 5)]), "EXECUTABLE_NOT_IN_FUNCTION")

    def test_ambiguity_rejected(self):
        with tempfile.TemporaryDirectory() as d:
            path = Path(d, "functions.json")
            spans = [[4096 + j * 16, 4104 + j * 16, j + 1] for j in range(100)]
            spans[1] = [4096, 4105, 2]
            fixture(path, ranges=spans)
            intervals = bridge.load_intervals(path, "a" * 64)
            self.assertEqual(bridge.classify_elf_pc(0x71000000 + 4097, 0x71000000, intervals,
                                                    [(0, 4096, 2000, 5)]), "AMBIGUOUS_FUNCTION")

    def test_duplicate_json_keys_rejected(self):
        with tempfile.TemporaryDirectory() as d:
            path = Path(d, "functions.json")
            fixture(path)
            text = path.read_text()
            path.write_text(text.replace('"image_base":', '"image_base": 4, "image_base":', 1))
            with self.assertRaisesRegex(bridge.PCError, "DUPLICATE_WITNESS_KEY"):
                bridge.load_intervals(path, "a" * 64)

    def test_boolean_integer_rejected(self):
        with tempfile.TemporaryDirectory() as d:
            path = Path(d, "functions.json")
            fixture(path)
            j = json.loads(path.read_text())
            j["intervals"][0][1] = True
            path.write_text(json.dumps(j))
            with self.assertRaisesRegex(bridge.PCError, "RANGE_INVALID"):
                bridge.load_intervals(path, "a" * 64)

    def test_oversized_and_symlink_rejected(self):
        with tempfile.TemporaryDirectory() as d:
            path = Path(d, "functions.json")
            fixture(path)
            link = Path(d, "link.json")
            link.symlink_to(path)
            with self.assertRaisesRegex(bridge.PCError, "FILE_INVALID"):
                bridge.load_intervals(link, "a" * 64)
            with self.assertRaisesRegex(bridge.PCError, "FILE_INVALID"):
                bridge.load_intervals(Path(d, "not-there"), "a" * 64)

    def test_single_step_budget_abstains_without_function_match(self):
        if shutil.which("gcc") is None:
            self.skipTest("gcc unavailable in this local test environment")
        with tempfile.TemporaryDirectory() as d:
            source = Path(d, "spin.c")
            program = Path(d, "spin")
            source.write_text('#include <unistd.h>\nint main(void){volatile unsigned long i=0; '
                              'while(i<6000000000UL){i++;} return 0;}\n')
            subprocess.run(["gcc", "-O0", "-fPIE", "-pie", str(source), "-o", str(program)],
                           check=True, stdout=subprocess.DEVNULL)
            proc = subprocess.Popen([str(program)], stdout=subprocess.DEVNULL,
                                    stderr=subprocess.DEVNULL)
            try:
                result = bridge.step_until_function(
                    proc.pid, lambda _pc: "OUTSIDE_IMAGE", max_steps=4)
                self.assertEqual(result["steps_executed"], 4)
                self.assertEqual(result["classifications"]["FUNCTION_MATCH"], 0)
                self.assertEqual(result["classifications"]["OUTSIDE_IMAGE"], 5)
                self.assertIsNone(proc.poll())
            finally:
                proc.kill()
                proc.wait(timeout=3)

    def test_actual_process_single_step_and_restore(self):
        if shutil.which("gcc") is None:
            self.skipTest("gcc unavailable in this local test environment")
        with tempfile.TemporaryDirectory() as d:
            source = Path(d, "spin.c")
            program = Path(d, "spin")
            source.write_text('#include <unistd.h>\nint main(void){volatile unsigned long i=0; '
                              'while(i<6000000000UL){i++;} return 0;}\n')
            subprocess.run(["gcc", "-O0", "-fPIE", "-pie", str(source), "-o", str(program)],
                           check=True, stdout=subprocess.DEVNULL)
            proc = subprocess.Popen([str(program)], stdout=subprocess.DEVNULL,
                                    stderr=subprocess.DEVNULL)
            try:
                observed = []

                def classify(pc):
                    observed.append(pc)
                    return "FUNCTION_MATCH" if len(observed) == 5 else "OUTSIDE_IMAGE"

                result = bridge.step_until_function(proc.pid, classify, max_steps=15)
                self.assertEqual(result["steps_executed"], 4)
                self.assertEqual(result["classifications"]["FUNCTION_MATCH"], 1)
                self.assertEqual(len(observed), 5)
                self.assertIsNone(proc.poll())  # debugger detached; process resumed
            finally:
                proc.kill()
                proc.wait(timeout=3)

    def test_actual_process_ptrace_read_only(self):
        # A real Linux x86_64 controlled C child; fail closed when unavailable,
        # but do not silently accept any Ghidra/Freeciv claim from this test.
        if shutil.which("gcc") is None:
            self.skipTest("gcc unavailable in this local test environment")
        with tempfile.TemporaryDirectory() as d:
            src = Path(d, "busy.c")
            dest = Path(d, "busy")
            src.write_text('#include <unistd.h>\nint main(void){volatile unsigned long i=0; '
                           'while(i<6000000000UL){i++;} return 0;}\n')
            subprocess.run(["gcc", "-O0", "-fPIE", "-pie", str(src), "-o", str(dest)],
                           check=True, stdout=subprocess.DEVNULL)
            proc = subprocess.Popen([str(dest)], stdout=subprocess.DEVNULL,
                                    stderr=subprocess.DEVNULL)
            try:
                pc = bridge.sample_pc_once(proc.pid)
                self.assertGreater(pc, 0)
                self.assertIsInstance(pc, int)
            finally:
                proc.kill()
                proc.wait(timeout=3)


if __name__ == "__main__":
    unittest.main()
