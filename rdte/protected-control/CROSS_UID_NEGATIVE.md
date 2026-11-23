# Independent actual cross-UID negative — R040

Source adds a separate Docker-only test to the protected-control reference.
A root-credential controller binds its synthetic Unix socket under a freshly
created /tmp directory. The test alone deliberately changes the temporary
directory/socket modes to permit numeric UID1000 to connect. A child test
process drops to UID/GID1000 using CAP_SETUID/CAP_SETGID confined to an
otherwise cap-dropped, networkless, read-only disposable Docker container.

The child must successfully establish the socket connection and receive
the fixed CONTROL_IPC=DENIED marker from kernel SO_PEERCRED authentication.
The root owner record must remain nonexistent. The probe uses neither an
actual WineBot mount, actual application, nor user secrets. Raw fixture
paths and child output are not printed in CI, and the test image is pinned
by digest with no image publication.

This qualifies a *single Linux namespace* numeric-UID mismatch only.
It does NOT prove cross-user-namespace mapped credentials, authenticated
runtime IPC, guest-vs-API principal separation, mount custody, host root
security, operation audit, or crash-safe socket re-admission. Production
WineBot still exposes its writer lock under UID1000-writable artifacts;
the release STOP remains.
