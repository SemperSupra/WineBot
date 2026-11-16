# Installer Capture RDTE — offline inventory and Wine-registry comparison

This self-contained Go 1.25 standard-library CLI is **experimental**. It is an
instrument for reasoning about the effects of an installer, **not** a replacement
installer, application-launcher, or a privilege boundary.

## Local private workflow

1. Select a **disposable, quiesced**, rights-cleared Wine prefix. Never capture
   a live prefix with `wineserver`, installers, helper processes or another
   writer still active. Make private backups before an installer experiment.
2. Snapshot its filesystem inventory with `snapshot -root PREFIX -out PRIVATE_BEFORE.json`.
   Stop the installer and quiesce the prefix before capturing
   `snapshot -root PREFIX -out PRIVATE_AFTER.json`.
3. Compare inventories using
   `diff -before PRIVATE_BEFORE.json -after PRIVATE_AFTER.json -out PRIVATE_FS_DELTA.json`.
   `verify -root RECONSTRUCTED_PREFIX -manifest PRIVATE_AFTER.json` checks
   byte-for-byte filesystem metadata/content hashes against the intended
   post-installation state without displaying changed file contents.
   For a **path-free summary** suitable for guarded review, use
   `summary -before PRIVATE_BEFORE.json -after PRIVATE_AFTER.json -out PRIVATE_SUMMARY.json`.
   This counts only fixed file-installation categories, not individual paths.
4. Copy Wine's native `system.reg`, `user.reg`, or `userdef.reg` to *private
   evidence outside the source prefix* before and after. Use
   `regdiff -before PRIVATE_BEFORE.reg -after PRIVATE_AFTER.reg -out PRIVATE_REG_DELTA.json`.
   Do not mix files with different Wine registry roots or architectures.
   Use `regsummary -before PRIVATE_BEFORE.reg -after PRIVATE_AFTER.reg
   -out PRIVATE_REG_SUMMARY.json` for fixed counts of added/removed/changed
   registry keys and values. Unlike `regdiff`, the summary contains no
   names, paths, root identity, or value digests.
5. Compare application-level postconditions with the original installer and
   reconstructed install. Only then propose a versioned, declarative recipe.

Outputs are always local, no-overwrite, owner-only (0600) JSON. Output may
contain sensitive **relative file paths, registry key paths, value names and
hashes**; keep it in private custody. Public GitHub Actions uses tiny invented
fixtures only and uploads no artifacts.

## Exactly what is and is not understood

The registry parser supports a conservative subset of Wine's native
`WINE REGISTRY Version 2` files: relative-root and architecture headers,
key sections with numeric modification times, quoted/default values,
`REG_SZ`-style quoted values, `str(type)` strings, `dword`, and
`hex`/`hex(type)` bytes with line continuations. It ignores key modification
times and source ordering and emits SHA-256 digests for typed *value text*, not
raw values. Unknown encodings or ambiguous statements fail closed. It does
**not** implement the full Windows Registry Editor 5 format, a complete
Wine/Windows string-unescaping implementation, Unicode case-folding parity,
transactional registry overlays, or ordering of installer events.

The native syntax was checked against Wine's authoritative
[server/registry.c](https://github.com/wine-mirror/wine/blob/master/server/registry.c).
Wine formats and version differences require fixture qualification before
promoting this as a reliable semantic oracle.

File traversal uses Go `os.Root`, refuses unsupported objects and treats
symlinks as *hashed target metadata only*. It does not inspect host files
outside the selected root. The tool may fail if files change during scanning;
running against active Wine is a usage error. Static output is neither a
process trace nor a proof that an application works.

## Success definition and follow-on work

The source-only offline unit workflow verifies representative synthetic
add/change/remove behavior, timestamp/ordering normalization, privacy of
registry value data, malformed input rejection, architecture/root isolation,
filesystem symlink containment and exact postcondition checks. This qualifies
only **STATIC_CONTRACT / synthetic infrastructure** evidence.

Future independent workcells: event ordering and process provenance, registry
canonicalization vs native Windows behavior, installer dependency resolution,
idempotent recipe execution/rollback, actual Wine application and game
installation using redistribution-permitted fixtures, WinInspect observation,
human/agent input arbitration and accessibility. A real Windows/Wine fixture
comparison is required before PRODUCT_QUALIFICATION.

**Hardware-readiness gate: NOT_READY_FOR_HARDWARE_TEST** until the owning
roadmap's independent requirements are satisfied.
