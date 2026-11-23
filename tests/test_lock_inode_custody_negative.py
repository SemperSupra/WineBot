"""Synthetic negative control: user-writable lock paths cannot fence rivals.

A POSIX flock protects an inode, not a filename. This is an expected unsafe
counterexample only, not authorization to test/alter user or host paths.
"""
import fcntl
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path


class LockFileCustodyNegative(unittest.TestCase):
    def test_separate_process_replaces_path_and_obtains_second_exclusive_flock(self):
        if os.name != "posix":
            self.skipTest("Linux/POSIX-only negative control")
        with tempfile.TemporaryDirectory(prefix="winebot-synthetic-lock-") as dirname:
            path = Path(dirname) / ".winebot-active-writer.lock"
            old_fd = os.open(path, os.O_CREAT | os.O_RDWR, 0o600)
            try:
                fcntl.flock(old_fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
                original = os.fstat(old_fd)
                # A separate same-UID process changes only its private
                # temp-directory entry and opens an independent FD/inode.
                child = (
                    "import fcntl,os,sys\n"
                    "p=sys.argv[1]\n"
                    "os.unlink(p)\n"
                    "fd=os.open(p,os.O_CREAT|os.O_RDWR,0o600)\n"
                    "try:\n"
                    " fcntl.flock(fd,fcntl.LOCK_EX|fcntl.LOCK_NB)\n"
                    " os.write(1,b'SYNTHETIC_SPLIT_FLOCK=CONFIRMED\\n')\n"
                    "finally:\n"
                    " os.close(fd)\n"
                )
                result = subprocess.run(
                    [sys.executable, "-c", child, str(path)],
                    capture_output=True, text=True, check=False, timeout=5,
                )
                self.assertEqual(result.returncode, 0)
                self.assertEqual(
                    result.stdout, "SYNTHETIC_SPLIT_FLOCK=CONFIRMED\n",
                )
                self.assertEqual(result.stderr, "")
                replacement = os.stat(path, follow_symlinks=False)
                self.assertNotEqual(
                    (original.st_dev, original.st_ino),
                    (replacement.st_dev, replacement.st_ino),
                )
                # The old lock is still held on a now-unlinked inode.
                self.assertEqual(os.fstat(old_fd).st_nlink, 0)
            finally:
                os.close(old_fd)


if __name__ == "__main__":
    unittest.main()
