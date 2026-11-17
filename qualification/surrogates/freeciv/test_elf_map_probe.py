#!/usr/bin/env python3
"""No Freeciv or private source required; tests include real public /bin/sleep."""
import importlib.util
import pathlib
import subprocess
import unittest

spec = importlib.util.spec_from_file_location("elf_map_probe", pathlib.Path(__file__).with_name("elf_map_probe.py"))
probe = importlib.util.module_from_spec(spec)
spec.loader.exec_module(probe)


class LoadMapTests(unittest.TestCase):
    def test_live_sleep_elf_and_maps(self):
        exe = "/usr/bin/sleep" if pathlib.Path("/usr/bin/sleep").exists() else "/bin/sleep"
        child = subprocess.Popen([exe, "2"])
        try:
            record = probe.observe_pid(child.pid, exe, probe.file_digest(exe))
            self.assertEqual(record["status"], "CORRELATED_ELF_LOAD_MAP_NOT_PC")
            self.assertGreaterEqual(record["matching_file_maps"], 2)
            self.assertFalse(record["pc_observed"])
            self.assertFalse(record["raw_addresses_exported"])
        finally:
            child.terminate()
            child.wait(timeout=4)

    def test_wrong_hash_refuses_real_pid(self):
        exe = "/usr/bin/sleep" if pathlib.Path("/usr/bin/sleep").exists() else "/bin/sleep"
        child = subprocess.Popen([exe, "2"])
        try:
            with self.assertRaisesRegex(probe.CorrelationError, "EXECUTABLE_SHA256_MISMATCH"):
                probe.observe_pid(child.pid, exe, "0" * 64)
        finally:
            child.terminate()
            child.wait(timeout=4)

    def test_identity_negative(self):
        with self.assertRaisesRegex(probe.CorrelationError, "NO_EXACT_INODE"):
            probe.correlate_map_text("1000-2000 r-xp 00000000 00:01 77 /a\n", [(0,0,4096,5)], (0,1), 78, 3)

    def test_synthetic_aslr_and_wrong_offset(self):
        segment = [(0,0,8192,5)]
        base = 0x55000000
        text = (f"{base:08x}-{base+4096:08x} r--p 00000000 08:02 42 /a\n"
                f"{base+4096:08x}-{base+8192:08x} r-xp 00001000 08:02 42 /a\n")
        record = probe.correlate_map_text(text, segment, (8,2), 42, 3)
        self.assertEqual(record["matched_load_maps"], 2)
        bad = text.replace("00001000", "00003000")
        with self.assertRaises(probe.CorrelationError):
            probe.correlate_map_text(bad, segment, (8,2), 42, 3)

    def test_bad_elf_refuses(self):
        with self.assertRaisesRegex(probe.CorrelationError, "ELF64"):
            import tempfile
            with tempfile.NamedTemporaryFile() as f:
                f.write(b"not an elf")
                f.flush()
                probe.elf_segments(f.name)

    def test_bad_page_size_refuses(self):
        with self.assertRaisesRegex(probe.CorrelationError, "PAGE_SIZE_INVALID"):
            probe.correlate_map_text("", [], (0,0), 0, 3, 1234)


if __name__ == "__main__":
    unittest.main()
