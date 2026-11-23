"""Synthetic cooperative flock and source-bound layered admission gates.

No deployment, network, non-synthetic state, or privileged test target.
These controls are not evidence of an atomic inter-container handoff.
"""
import fcntl
import io
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


class LayeredWriterFence(unittest.TestCase):
    def test_same_lock_identity_and_stage_before_mutation(self):
        script = (ROOT / "scripts/layers/prepare-state.sh").read_text()
        owner = (ROOT / "api/core/writer_admission.py").read_text()
        self.assertIn('LOCK_BASENAME = ".winebot-active-writer.lock"', owner)
        self.assertIn('DEFAULT_SESSION_ROOT = "/artifacts/sessions"', owner)
        self.assertIn('control_root="$control_parent/sessions"', script)
        self.assertIn('control_file="$control_root/.winebot-active-writer.lock"', script)
        self.assertIn('flock -n -x 9', script)
        self.assertLess(script.index('flock -n -x 9'), script.index('for dir in /state/prefix'))
        self.assertLess(script.index('flock -n -x 9'), script.index('chown 1000:1000 "$dir"'))
        self.assertIn('stat -Lc', script)
        self.assertIn('fail lock_contended', script)
        self.assertIn('fail lock_identity_invalid', script)

    def test_prerequisites_and_actual_guest_contender_required(self):
        compose = (ROOT / "compose/layered.yml").read_text()
        dockerfile = (ROOT / "docker/app-bundle.Dockerfile").read_text()
        hil = (ROOT / "scripts/ci/qualify-wine11-layered.sh").read_text()
        self.assertIn('cap_add: [CHOWN, DAC_OVERRIDE]', compose)
        self.assertIn('command -v flock >/dev/null', dockerfile)
        self.assertIn('run --rm --no-deps state-init', hil)
        self.assertIn('stage=state_init_conflict_rejected', hil)
        self.assertNotIn('docker push', hil)
        self.assertNotIn('actions/upload-artifact', hil)

    def test_independent_process_cannot_acquire_held_lock(self):
        if os.name != "posix":
            self.skipTest("Linux-only flock contract")
        with tempfile.TemporaryDirectory() as root:
            path = Path(root) / ".winebot-active-writer.lock"
            with path.open("a+b") as held:
                fcntl.flock(held.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
                # A distinct subprocess must open its own OFD. Testing in the
                # parent process or after fork with inherited FD is invalid.
                code = (
                    "import fcntl,sys\n"
                    "with open(sys.argv[1], 'r+b') as f:\n"
                    "  try: fcntl.flock(f.fileno(),fcntl.LOCK_EX|fcntl.LOCK_NB)\n"
                    "  except BlockingIOError: sys.exit(73)\n"
                    "  sys.exit(0)\n"
                )
                denied = subprocess.run(
                    [sys.executable, "-c", code, str(path)],
                    check=False, capture_output=True, text=True, timeout=5,
                )
                self.assertEqual(denied.returncode, 73)
                self.assertEqual(denied.stdout, "")
                self.assertEqual(denied.stderr, "")
            allowed = subprocess.run(
                [sys.executable, "-c", code, str(path)],
                check=False, capture_output=True, text=True, timeout=5,
            )
            self.assertEqual(allowed.returncode, 0)


if __name__ == "__main__":
    unittest.main()
