# Writer/Controller lock-file custody: expected unsafe negative, R040

## Verified counterexample, not a vulnerability patch

The existing writer-admission and candidate deployment-gate use Linux
`flock` on pathnames under external artifacts' `sessions` directory.
The state initializer currently gives UID1000 ownership of this directory,
which may also be accessible to a Wine application executing as UID1000.
A writer with permission to modify the *parent directory* can remove an
existing root-owned or same-UID file directory entry. A new lock file can
then be created at the same pathname. Both processes may acquire LOCK_EX
because their open file descriptions refer to different inodes.

`tests/test_lock_inode_custody_negative.py` is a bounded **expected unsafe
witness**: an original process acquires an exclusive lock; a separate
same-UID subprocess unlinks the temp filename, creates another file and
acquires another exclusive lock; the parent verifies distinct inodes and
that the old FD is still attached to the unlinked original. It runs only
inside a newly created synthetic TemporaryDirectory. No WineBot mount,
third-party target, hardware, credential or private data is accessed.

**Important:** A PASS means the Linux filesystem exhibits this known
unsafe property. It does NOT mean WineBot is secure. This negative receipt
must be paired with an actual protected control-plane architectural gate
and independent hostile same-UID admission qualification before release.

## Corrective design / release criteria

1. Separate the trusted admission/persistent-owner authority from Wine
   execution at the container/user-namespace boundary. Keep its lock
   directory and control volume out of the Wine process's writable
   namespace. A chmod-only patch cannot protect a file when the parent
   can be renamed by the runtime principal.
2. Use a dedicated minimal control service with a protected persistent
   volume, generation CAS, auditable ownership transfer and separate
   API auth/human STOP priority; client processes cannot originate
   unrestricted privileged mutations merely by sharing UID or a socket.
3. Add bad-volume, mount-identity, substitution, forced gate/controller
   crash, concurrent rival controller, orphan recovery and guest attempt
   to alter lock files to the exact-head public synthetic test matrix.
4. Admit native Windows/WinBot and WinInspect observer semantics
   separately. No cross-host NFS distributed locking claim.

This source-only negative-control experiment is explicitly a **release
STOP** for arbitrary/untrusted Wine apps until the architecture changes.
