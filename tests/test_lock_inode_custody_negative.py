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



@unittest.skipUnless(sys.platform == "linux", "Linux flock semantics only")
class InheritedWriterUnlockNegative(unittest.TestCase):
    def test_inherited_child_unlocks_live_parent_without_replacing_inode(self):
        with tempfile.TemporaryDirectory(prefix="winebot-synthetic-ofd-") as root:
            path = Path(root) / "writer.lock"
            owner = os.open(path, os.O_CREAT | os.O_EXCL | os.O_RDWR, 0o600)
            rival = os.open(path, os.O_RDWR | os.O_NOFOLLOW)
            try:
                fcntl.flock(owner, fcntl.LOCK_EX | fcntl.LOCK_NB)
                original = os.fstat(owner)
                with self.assertRaises(BlockingIOError):
                    fcntl.flock(rival, fcntl.LOCK_EX | fcntl.LOCK_NB)
                result = subprocess.run(
                    [sys.executable, "-c",
                     "import fcntl,sys; fcntl.flock(int(sys.argv[1]), fcntl.LOCK_UN)",
                     str(owner)],
                    pass_fds=(owner,), capture_output=True, check=False, timeout=5,
                )
                self.assertEqual(result.returncode, 0)
                self.assertEqual(result.stdout, b"")
                self.assertEqual(result.stderr, b"")
                fcntl.flock(rival, fcntl.LOCK_EX | fcntl.LOCK_NB)
                current = os.stat(path, follow_symlinks=False)
                self.assertEqual((original.st_dev, original.st_ino),
                                 (current.st_dev, current.st_ino))
                self.assertEqual(os.fstat(owner).st_nlink, 1)
                with self.assertRaises(BlockingIOError):
                    fcntl.flock(owner, fcntl.LOCK_EX | fcntl.LOCK_NB)
            finally:
                os.close(rival)
                os.close(owner)


if __name__ == "__main__":
    unittest.main()
