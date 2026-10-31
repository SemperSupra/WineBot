# Portable sensor/actuator toolkit — implementation and employment plan (candidate)

Status: test-only architecture/packaging plan; NOT production release or authorization. Primary runtime Wine **11.0** and native Windows. Existing owner DLE: private winebot-research#1. Do not duplicate WinInspect or WinBot authority.

## Product boundaries

One small, versioned **portable Windows executable** and Go stdlib-only offline contract/library. Win32 x64 and x86 variants run on native Windows or under pristine Wine 11 WoW64. Wine-specific observation extensions are optional, negotiated, isolated adapters. Avoid assuming UIA or native desktop semantics exist under Wine. Consumer integration is additive: standalone CLI/JSON-lines, optional WinInspect provider, optional embedded Go library. No service, admin privileges, automatic injection, screen capture, network listener, or autonomous actuator in MVP.

## Three-audience entrypoints

* Human: `toolkit.exe doctor --json`, `capabilities`, `observe --fixture --max-events N --timeout-seconds N`, `stop`; readable diagnostics and explicit degraded capabilities.
* Automation: versioned bounded JSONL stdin/stdout, documented exit classes, deterministic offline fixture, idempotent install/uninstall, machine-readable capabilities.
* Agent: same machine interface, no privileged bypass, explicit action proposal vs authorized execution, source/target epoch and verified outcome; no prompt-text authority.

Names above are candidate CLI names, not implemented commands. Existing synthetic C observer currently emits `winebot.wine.event.v1` schema/kind/sequence and requires private Q cooperative stop; Go `observer.portable.v0` is test-only.

## Install layout and lifecycle

MVP distribution is two **separate signed-or-checksummed portable ZIP variants** (win-x64, win-x86) with `bin/`, `licenses/`, `manifest.json`, `SHA256SUMS`, `README`, and `install.ps1`/`uninstall.ps1` only after scripts are tested. Never pretend checksums equal signatures. Per-user Windows install: `%LOCALAPPDATA%\\WineBotToolkit\\<version>`; Wine11: `$WINEPREFIX/drive_c/users/<user>/AppData/Local/WineBotToolkit/<version>` via the same Win32 path API. The runtime executable should not require a shell script or Python. No system PATH mutation, HKLM writes, service registration, shell extension, browser plugin or elevation. Installation is an atomic stage/verify/swap with an explicit per-user active-version pointer and rollback; reject symlinks/path traversal, zip bombs, mismatched architecture, missing manifest, SHA mismatch, downgrade without explicit approval. Uninstall removes only manifest-owned paths, never user configuration or Wine prefix. ZIP can always be run unpacked without installation. Never update while an observer session is active; refuse or side-by-side version.

Initial package qualification should build native x86/x64 synthetic observer/fixture with pinned MinGW on public Linux; validate package contents and checksums offline; run native Windows 2022 and pinned source Wine11 smoke, repeated install/uninstall/rollback in disposable per-user homes/prefixes. Windows MSI/WiX and winget metadata are **later** optional distribution surfaces, not MVP dependencies; Wine should not be assumed to support MSI behavior identically.

## Contracts and sensors

Core: `capabilities`, `snapshot`, `subscribe/poll`, `unsubscribe`, `stop`, `health`. Event status includes ready, gap, overflow, unsupported, revoked; opaque producer/session incarnation, stream cursor, optional opaque target_ref, independent target_epoch. No raw HWND/PID/window title/text/secret in default public stream. Without trusted correlation, return target unknown and trigger bounded broad reinspection. Native Windows and Wine11 must expose identical *contract semantics*, not fabricated feature parity. Per-sensor statuses available/degraded/unsupported/unauthorized/unverified.

## Actuators and authority

Actuation not in first portable observer release. Future allowlisted `window.activate`, `input.click/key`, `control.invoke/set_value`, `process.launch/stop` require authenticated principal, sole WinBot/authorized desktop lease, broker-side target generation recheck, serialized execution, bounded time, independent postcondition and `OUTCOME_UNKNOWN` for ambiguity. A cursor, target_ref, stream or WinInspect inspection capability is **not** an actuator credential. G0 security #515, WinBot #110, G2 atomic broker/registry fence and WinInspect protocol ownership remain hard holds.

## Parallel development worksets and sequential gates

A. **Package contract**: deterministic manifest schema, SHA checks, offline ZIP validation, no artifact publication; Windows x86/x64 compile.
B. **Runtime parity**: exact-current C source native Windows baseline vs pinned Wine11 source build, event loss/overflow/late Q, first-failure receipts; Wine9 comparator only.
C. **Consumer adapter**: additive WinInspect observer provider, capability discovery, two cursors, legacy events.poll unchanged, no private source projected into public repo.
D. **Lifecycle/security**: install/uninstall rollback and per-user no-elevation tests, identity ABA and desktop lease negative tests.
E. **Three-audience DX**: English/German/Thai Unicode fixture names, structured errors, offline doctor; independent accessibility/vision fallback evaluation.

Sequence: package schema + offline validation -> native Windows/Wine11 qualification -> opt-in read-only WinInspect integration -> authorized actuation after gates -> signed release and distribution admission. Each REP produces exact SHA, CI run, failures, source custody and next baton in DLE. Public GHA only for public synthetic sources, no private minutes, no runtime uploads or published release artifacts; private source remains private. Large future signed binaries belong in approved Google Drive large-file storage with hashes/provenance linked from Git/DLE, not public GHA artifacts without release authorization.

## MVP acceptance

1. Same native x86/x64 binaries and CLI schema operate under Windows and pinned Wine11, with explicit unsupported capability status.
2. Deterministic reproducible packaging; path-safe install/uninstall/rollback without admin; no leaked raw events.
3. Event sequence/gap/overflow and cooperative stop under bounded resources; two consumer cursors and target reuse fail closed.
4. WinInspect can attach as read-only consumer without changing its legacy RPC, and no control action bypasses existing owner gates.
5. All qualification evidence is exact-source, real public GHA receipts; do not claim successful Wine11 HIL until run terminal.
