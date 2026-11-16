#!/usr/bin/env python3
"""Source-neutral offline tests, independent of Freeciv and private source."""
import importlib.util
from pathlib import Path
import tempfile
import unittest

spec = importlib.util.spec_from_file_location("freeciv_probe", Path(__file__).with_name("probe.py"))
probe = importlib.util.module_from_spec(spec)
spec.loader.exec_module(probe)


class ContractTests(unittest.TestCase):
    def test_required_signal_contract(self):
        self.assertEqual(len(probe.REQUIRED_SIGNALS), 7)
        self.assertEqual(len(set(probe.REQUIRED_SIGNALS)), len(probe.REQUIRED_SIGNALS))

    def test_digest_mutation(self):
        with tempfile.TemporaryDirectory() as td:
            p = Path(td) / "f.bin"
            p.write_bytes(b"hello")
            h = probe.digest(p)
            self.assertEqual(len(h), 64)
            p.write_bytes(b"jello")
            self.assertNotEqual(probe.digest(p), h)

    def test_trace_classification_does_not_exfiltrate_content(self):
        with tempfile.TemporaryDirectory() as td:
            p = Path(td) / "syscalls.99"
            p.write_text('openat(123, "/secret/private/something")\n'
                         'socket(AF_INET,SOCK_STREAM,IPPROTO_TCP)\n'
                         'bind(4,...)\n')
            counts = probe.trace_classification(td)
            self.assertEqual(counts["file_syscalls"], 1)
            self.assertEqual(counts["network_syscalls"], 2)
            self.assertNotIn("secret", str(counts))

    def test_save_scrub(self):
        with tempfile.TemporaryDirectory() as td:
            p = Path(td) / "surrogate-a.sav.xz"
            p.write_bytes(b"this is a synthetic save")
            saves = probe.inspect_saves(td)
            self.assertEqual(len(saves), 1)
            self.assertEqual(set(saves[0]), {"bytes", "sha256"})
            self.assertNotIn("surrogate-a", str(saves))

    def test_external_connect_does_not_pass_egress_guard(self):
        with tempfile.TemporaryDirectory() as td:
            p = Path(td)/"syscalls.1"
            p.write_text('connect(4, {sa_family=AF_INET, sin_port=htons(443), sin_addr=inet_addr("8.8.8.8")}, 16)\n')
            counts = probe.trace_classification(td)
            self.assertEqual(counts["non_loopback_ipv4_connects"], 1)

    def test_version_collected_from_stderr(self):
        with tempfile.TemporaryDirectory() as td:
            script = Path(td) / "version-script"
            script.write_text('#!/bin/sh\nprintf "Version 3.1.0\\n" >&2\n')
            script.chmod(0o700)
            self.assertEqual(probe.capture_version(str(script)), ["Version 3.1.0"])

    def test_blank_version_rejected(self):
        with tempfile.TemporaryDirectory() as td:
            script = Path(td) / "blank-version-script"
            script.write_text('#!/bin/sh\nexit 0\n')
            script.chmod(0o700)
            with self.assertRaisesRegex(RuntimeError, "FREECIV_VERSION_UNOBSERVED"):
                probe.capture_version(str(script))

    def test_non_save_exclusion(self):
        with tempfile.TemporaryDirectory() as td:
            Path(td,"metadata.json").write_text("{}")
            Path(td,"surrogate-a.log").write_text("private")
            self.assertEqual(probe.inspect_saves(td), [])

    def test_socket_failure_is_not_success(self):
        self.assertFalse(probe.loopback_ready(1, deadline=.05))


if __name__ == "__main__":
    unittest.main()
