# WineBot synthetic declarative recipe RDTE

This is an **independent source implementation** of the tiny rights-cleared
Windows API fixture. It is designed to prove the possibility of replacing an
installer with a versioned, inspectable recipe, not to replace general-purpose
Windows installers or become a production package manager.

- `recipe.json` names exactly one synthetic fixture, a relative `%APPDATA%`
  file and a single HKCU REG_SZ value, plus their expected literal contents.
- `main_windows.go` parses the JSON, rejects additional/unrecognized fields,
  validates every value against a fixed fixture allowlist, and directly invokes
  WinAPI file and registry functions. It **does not call** the original
  installer. A synthetic-CI-only environment gate prevents casual execution.
- `install` refuses an existing fixture directory or registry value;
  `verify` checks file SHA-256 and typed registry contents;
  `uninstall` refuses unexpected files and removes only its own fixture.
  This is not transactional and does not yet handle installer dependencies,
  scheduled reboot actions, privileges, services, DLL registration or rollback
  after partial failure.
- `.github/workflows/windows-fixture-recipe-rdte.yml` compares the original
  fixture and this recipe replayer on **native Windows** and on an **isolated
  distribution-Wine public runner** using the existing WineBot file snapshot
  and native-Wine-registry semantic delta tooling. No user prefixes, binaries,
  registry contents or other artifacts are uploaded.

The CI result must be tied to an exact source SHA. Only a successful terminal
Windows and Wine result warrants a **bounded synthetic reconstruction** claim.
Distro Wine is not the pinned Wine11 layered runtime. A general reusable
recipe engine, installer dependency graph, side-effect/event capture,
production restore, digital-signature verification and real application/game
compatibility qualification remain separate development and security gates.

Do not run this fixture on actual user hardware or profiles.
