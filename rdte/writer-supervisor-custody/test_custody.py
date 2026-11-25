"""Synthetic Linux custody qualification; not a production supervisor."""
import fcntl
import os
import select
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

GUEST = r'''
import errno, os, sys
assert (os.getuid(), os.getgid()) == (1000, 1000)
assert os.getgroups() == []
path, fd = sys.argv[1], int(sys.argv[2])
try:
    os.fstat(fd)
except OSError as exc:
    assert exc.errno == errno.EBADF
else:
    raise AssertionError('unexpected inherited descriptor')
for action in (lambda: os.open(path, os.O_RDWR), lambda: os.unlink(path)):
    try:
        action()
    except PermissionError:
        continue
    raise AssertionError('guest reached protected lock')
print('GUEST_CUSTODY=DENIED', flush=True)
'''
HOLDER = r'''
import fcntl, os, sys
fd = os.open(sys.argv[1], os.O_RDWR | os.O_NOFOLLOW | os.O_CLOEXEC)
fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
print('HOLDER=READY', flush=True)
sys.stdin.read()
'''


class SupervisorCustody(unittest.TestCase):
    def setUp(self):
        self.assertEqual(sys.platform, 'linux')
        self.assertEqual(os.geteuid(), 0, 'numeric UID test requires root')
        self.root = tempfile.TemporaryDirectory(prefix='synthetic-custody-')
        self.addCleanup(self.root.cleanup)
        os.chmod(self.root.name, 0o755)
        protected = Path(self.root.name) / 'protected'
        protected.mkdir(mode=0o700)
        self.path = protected / 'writer.lock'
        fd = os.open(self.path, os.O_CREAT | os.O_EXCL | os.O_RDWR | os.O_CLOEXEC, 0o600)
        os.close(fd)

    def open_lock(self):
        fd = os.open(self.path, os.O_RDWR | os.O_NOFOLLOW | os.O_CLOEXEC)
        self.addCleanup(os.close, fd)
        return fd

    def test_guest_cannot_inherit_reopen_or_unlink(self):
        owner, rival = self.open_lock(), self.open_lock()
        fcntl.flock(owner, fcntl.LOCK_EX | fcntl.LOCK_NB)
        self.assertFalse(os.get_inheritable(owner))
        before = os.fstat(owner)
        guest = subprocess.run(
            [sys.executable, '-I', '-c', GUEST, str(self.path), str(owner)],
            user=1000, group=1000, extra_groups=[], close_fds=True,
            capture_output=True, timeout=5, check=False,
        )
        self.assertEqual(guest.returncode, 0)
        self.assertEqual(guest.stdout, b'GUEST_CUSTODY=DENIED\n')
        self.assertEqual(guest.stderr, b'')
        after = self.path.stat()
        self.assertEqual((before.st_dev, before.st_ino), (after.st_dev, after.st_ino))
        with self.assertRaises(BlockingIOError):
            fcntl.flock(rival, fcntl.LOCK_EX | fcntl.LOCK_NB)

    def test_supervisor_death_does_not_prove_guest_reaped(self):
        # Independent synthetic survivor is deliberately NOT a descendant.
        # This models an execution scope whose lifetime outlasts the holder.
        with subprocess.Popen(
            [sys.executable, '-I', '-c', HOLDER, str(self.path)],
            stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL,
        ) as holder, subprocess.Popen(
            [sys.executable, '-I', '-c', 'import sys; sys.stdin.read()'],
            stdin=subprocess.PIPE, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
            user=1000, group=1000, extra_groups=[], close_fds=True,
        ) as guest:
            try:
                self.assertTrue(select.select([holder.stdout], [], [], 5)[0])
                self.assertEqual(holder.stdout.readline(), b'HOLDER=READY\n')
                rival = self.open_lock()
                with self.assertRaises(BlockingIOError):
                    fcntl.flock(rival, fcntl.LOCK_EX | fcntl.LOCK_NB)
                holder.kill()
                holder.wait(timeout=5)
                self.assertIsNone(guest.poll())
                fcntl.flock(rival, fcntl.LOCK_EX | fcntl.LOCK_NB)
                self.assertIsNone(guest.poll())
            finally:
                for child in (holder, guest):
                    if child.poll() is None:
                        child.kill()
                    child.wait(timeout=5)


if __name__ == '__main__':
    unittest.main()
