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

## Experimental kernel-credential control socket

The optional 'serve' CLI mode listens only on the fixed
/winebot-control/.winebot-control-v1.sock, beneath a validated root-owned
0700 volume which is NEVER mounted in a Wine guest or the existing FastAPI.
The Unix socket has mode 0600. Requests are bounded to 2048 bytes, strict
duplicate-free JSON with only read and generation-checked claim operations.
Linux SO_PEERCRED must report root UID AND root GID before parsing any request.
All results are fixed enumerated markers, not source record contents.

Independent public Go -race tests exercise real Linux AF_UNIX sockets and
kernel identity, rejection when the expected UID/GID differs, malformed/extra
protocol fields, stale generation and idempotent retry, duplicate socket
server refusal and symlink/stale path refusal on a fresh synthetic tempdir.

The code is not wired to Docker Compose, WineBot runtime, API, or user state.
A future production control socket must be kept inaccessible to Wine UID1000
even if the API is compromised; principal separation, API authorization,
human STOP priority, container/host namespace mapping, socket crash cleanup,
role-scoped control capabilities and audit are future release gates.
