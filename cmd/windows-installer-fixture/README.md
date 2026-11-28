# Windows installer fixture — public, original, disposable RDTE

This fixture is original source in WineBot. It is not a third-party application,
installer-repackaging mechanism, rights-restricted game or production program.

The Go stdlib `windows` target creates a genuine Windows PE executable using
the Windows file APIs and native Advapi32 registry APIs. It changes only:

- One newly created fixture-specific directory under the current user's
  `%APPDATA%`, containing `installed.txt` with the constant `synthetic-v1`.
- `HKCU\Software\WineBotInstallerFixture\InstallState` as `REG_SZ`, with the
  same synthetic value.

The fixed argument `install` creates both and fails if the directory already
exists. `uninstall` refuses to remove unrecognized content and deletes only
the fixture file/directory and its own key. The binary will not run unless
`WINEBOT_FIXTURE_PERMIT=synthetic-ci` is explicitly supplied. Never use this
fixture against an existing user prefix or persistent personal registry.

## Qualification

`.github/workflows/windows-installer-fixture-rdte.yml` executes two isolated
public GitHub Actions workcells:

1. **Native Windows reference** on the standard public Windows hosted runner:
   compile from source; install; verify both HKCU and file postconditions;
   uninstall; verify cleanup. Only fixed-category results are printed.
2. **Wine observed compatibility** on a disposable Ubuntu 24.04 public runner:
   build the same PE from source, initialize a fresh temporary Wine prefix
   using distribution Wine, snapshot Wine's native `user.reg` before and
   after executing the PE, then run WineBot's `regdiff` and `regverify`.
   Require a changed `InstallState` entry under the fixture's key. Do not
   publish the PE, registry files, process traces, or converted snapshot data.

The Wine runner uses **distribution Wine**, not the independently pinned
Wine 11 candidate. Its result is an infrastructure/semantic fixture test, not
a Wine11 layered-runtime or game/installer-reconstruction acceptance result.
The Ubuntu APT package version is not currently digest-pinned; record this
as a reproducibility limitation until an exact packaged Wine runtime is
qualified in a separate source-bound workflow.

No actual user hardware, connected local machines, private CI minutes,
secrets, persisted user data, third-party installer downloads, browser
screenshots or image publication are used. Do not interpret a PASS as
eligibility for release or hardware tests. Compare the exact Git commit and
Actions run ID before accepting any claim.

Future work: actual installer event/process timeline, executable/registry
transaction capture, WinInspect program behavior, independent reconstruction
from a declarative recipe and native Windows vs Wine semantic postconditions.
