# Conservative external-volume identity preflight (offline RDTE)

An eighth root-owned protected `WINEBOT_CONTROL_VOLUME` is necessary
but not sufficient to isolate controller authority. Docker users can
configure different external volume names that alias the same backing
host path (e.g. local driver bind options). A runtime UID1000 could
then alter root-control authority despite different Compose names.

This candidate validates all eight volume names and requires:
- Docker volume driver exactly `local`;
- `Options == null` or `{}` (rejects bind/device aliases);
- Docker-reported absolute non-root mountpoint;
- unique Docker-reported mountpoint for every requested external volume;
- all requirements checked before any Compose runtime starts.

Unsupported storage plugins, ZFS driver extensions and bind options
**fail closed pending independent validation**. Deployment preflight
prints bounded enumerated statuses, never mountpoints or host paths.

The negative CI uses a fake Docker API executable (no real Docker
volumes, network, user data, or mount operations) to prove alias,
driver, device options and missing control rejection. Existing public
disposable Docker replay tests the real positive local-volume path.
This is a **conservative admission check**, not cryptographic evidence
of host path identity. The Docker daemon/rootful host, mount namespace,
symlink/path aliases and kernel overlay behavior require separate
host-side critic and malicious-host qualification. It also does NOT
move the old guest-writable runtime writer lock or Python owner CAS
out of `/artifacts/sessions`. The security STOP remains in effect.
