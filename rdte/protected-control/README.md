# Protected control owner CAS / v1 — source-only RDTE

This Go stdlib-only Linux proof of concept is a **separate trusted
control-plane owner registry**, not a WineBot API or runtime patch.

It reads/writes only a root-owned, mode-0700 `/winebot-control` mount,
which draft #211 mounts exclusively into its isolated deployment-gate
container, *not* into Wine/guest or state-init services.

Fields: `schema`, monotonically increasing signed 63-bit
`generation`, bounded opaque `session_id` and `operation_id`.
Operations are `claim(session, expectedGeneration, operationID)`
and `view()`. A nonblocking Linux `flock` serializes root-local
CAS; file handles are opened with `O_NOFOLLOW`, checked for single
regular link, exact owner, mode0600 and strict JSON v1. Atomic
same-directory rename and file + directory sync establish a local
durability barrier. Idempotent retries may re-ACK only the exact
session, generation and operation id after a fresh directory fsync.
Stale epochs, duplicate JSON keys, wrong schema, alias/symlink paths,
bad perms, wrong UID, operation reuse and invalid IDs refuse.

All unit tests operate inside new `t.TempDir()` synthetic roots
owned by the test's process. The binary CLI intentionally fixes its
path to `/winebot-control` and requires euid 0, emitting only
`CONTROL_OWNER=...` fixed result codes. The public workflow runs
Go vet, race tests and compilation with no dependency downloads,
image publication, artifacts or private GH minutes.

**Status: experimental; not a safe runtime owner yet.** The Python
`api/core/persistent_owner.py` pointer remains active only as a
standalone implementation, with guest-writable artifacts root.
This Go store is not invoked by the current Compose controller; no
cross-container authenticated IPC, STOP priority, mount attestation,
host-user namespace proof, crash generation lease handoff, file
migrations or trusted source/runtime provenance exists. Never
silently treat passing CLI unit tests as runtime release approval.
