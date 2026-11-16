"""Fail-closed I/O trace semantics, synthetic source-neutral fixtures."""
import importlib.util
import tempfile
import unittest
from pathlib import Path

spec = importlib.util.spec_from_file_location("freeciv_io_boundary", Path(__file__).with_name("io_boundary.py"))
mod = importlib.util.module_from_spec(spec)
spec.loader.exec_module(mod)


class IOTests(unittest.TestCase):
    def test_realistic_read_write_without_data_leak(self):
        with tempfile.TemporaryDirectory() as d:
            Path(d, "syscalls.1").write_text(
                'openat(AT_FDCWD, "/tmp/private-alpha.sav", O_RDONLY) = 3</tmp/private-alpha.sav>\n'
                'read(3</tmp/private-alpha.sav>, "SECRET", 6) = 6\n'
                'write(4</tmp/private-alpha.sav>, "SECRET", 6) = 6\n')
            r = mod.parse_trace(d)
            self.assertEqual(r["status"], "PASS")
            self.assertEqual(r["counters"]["bytes_read"], 6)
            self.assertEqual(r["counters"]["bytes_written"], 6)
            self.assertEqual(r["file_category_counts"]["save_candidate.read_calls"], 1)
            self.assertNotIn("SECRET", str(r))
            self.assertNotIn("private-alpha", str(r))

    def test_memory_mapping_metadata(self):
        with tempfile.TemporaryDirectory() as d:
            Path(d, "syscalls.4").write_text(
                'mmap(NULL, 8192, PROT_READ, MAP_PRIVATE, 3</foo/texture.png>, 0) = 0x7fffff000000\n'
                'read(3</foo/texture.png>, "", 2) = 2\n'
                'write(4</foo/texture.png>, "", 2) = 2\n')
            result = mod.parse_trace(d)
            self.assertEqual(result["counters"]["mapping_calls"], 1)
            self.assertEqual(result["file_category_counts"]["asset_candidate.mapping_calls"], 1)

    def test_failed_call_does_not_count(self):
        with tempfile.TemporaryDirectory() as d:
            Path(d, "syscalls.2").write_text('read(3</a>, "", 10) = -1 EBADF\n')
            r = mod.parse_trace(d)
            self.assertEqual(r["status"], "UNQUALIFIED")
            self.assertEqual(r["counters"]["failed_calls"], 1)

    def test_missing_trace_refused(self):
        with tempfile.TemporaryDirectory() as d:
            with self.assertRaisesRegex(ValueError, "ABSENT"):
                mod.parse_trace(d)

    def test_symlink_trace_refused(self):
        with tempfile.TemporaryDirectory() as d:
            Path(d, "actual").write_text("not trusted")
            Path(d, "syscalls.1").symlink_to(Path(d, "actual"))
            with self.assertRaisesRegex(ValueError, "UNSAFE"):
                mod.parse_trace(d)

    def test_unsafe_budget(self):
        with tempfile.TemporaryDirectory() as d:
            Path(d, "syscalls.1").write_bytes(b"x" * 64)
            old = mod.MAX_FILE_BYTES
            try:
                mod.MAX_FILE_BYTES = 40
                with self.assertRaisesRegex(ValueError, "BUDGET"):
                    mod.parse_trace(d)
            finally:
                mod.MAX_FILE_BYTES = old

    def test_no_path_publication(self):
        self.assertEqual(mod.file_category("/srv/secret/unit.png"), "asset_candidate")
        self.assertEqual(mod.file_category("/srv/secret/settings.ini"), "config_candidate")
        self.assertEqual(mod.file_category("/srv/secret/libengine.so.23"), "library_candidate")
        self.assertEqual(mod.file_category("/srv/foo/../secret"), "other")

    def test_unmapped_descriptor_is_explicit(self):
        with tempfile.TemporaryDirectory() as d:
            Path(d, "syscalls.1").write_text('read(3, "x", 1) = 1\nwrite(4, "y", 1) = 1\n')
            r = mod.parse_trace(d)
            self.assertEqual(r["file_category_counts"]["unknown_fd.read_calls"], 1)


if __name__ == "__main__":
    unittest.main()
