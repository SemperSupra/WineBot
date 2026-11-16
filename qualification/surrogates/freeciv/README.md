# Freeciv source-known surrogate qualification (public-safe)

**Purpose:** exercise a *real* freely licensed turn-based-strategy executable instead of fabricating original-SMAC parity. This is a bounded native Linux Freeciv server pilot, NOT a Wine, QEMU, 1999 Freeciv binary, Ghidra-native or Alpha Centauri oracle.

**Owner and DLE:** `mark-e-deyoung/ghidra-tools#4` (cross-target observatory), `mark-e-deyoung/reverse-smac#37` (SMAC acceptance and owner-deferred game work). This public WineBot runner-side implementation is independent from private `ghidra-tools` candidate code; no private source has been transferred to public CI.

**Target:** Ubuntu 24.04 official `freeciv-server` apt package (a current descendant of a 1990s turn-based Civilization-style game). Requires package and binary digest in each receipt; do not confuse with 1999 Freeciv 1.9.0, for which source archives exist. License: GPL-2.0-or-later.

**Vantage points:** source-known ELF identity, native live process and Linux memory-map region count/RSS, loopback TCP listen/connect, `strace` file/IPC/network/process operations, real in-game `save` command and on-disk output digest, clean termination/cleanup. Sensor data is aggregated into a minimal, no-private-bytes JSON receipt. A positive receipt is a qualified native process/I/O sensor chain, *not* a validated game turn or semantic game-state equivalence.

**Execution:** disposable public `ubuntu-24.04` GitHub-hosted job. Build/runtime dependencies installed only inside that ephemeral runner; game binds `127.0.0.1` and does not announce itself; non-loopback IPv4 connect observations fail; process is timed out and all raw syscall paths/logs/saves are disposed. Public artifact contains only source-known version, hashes and aggregate counts; no raw game files, process memory, private paths, credentials or runtime captures.

**Local synthetic regression:** `python3 qualification/surrogates/freeciv/test_contract.py`.

**Native runner:** `python3 qualification/surrogates/freeciv/probe.py --seed 42 --output "$RUNNER_TEMP/freeciv42.json"` after installing `freeciv-server strace` in an Ubuntu 24.04 ephemeral environment. It intentionally exits nonzero if game startup, loopback, memory sensing, syscall trace, save, or clean shutdown cannot be proven. Check GitHub Actions artifacts/receipts before claiming success; do not silently mark failed native probes green.

**Next independent experiment:** add a real client to generate packet payloads and UI observations; qualify Ghidra headless mapping of source-matched ELF; migrate from native Linux to Wine/PE as a separate differential workcell. Do not execute licensed SMAC/SMAX or Windows 98 binaries until `reverse-smac#37` authorizes that phase.

**Independent batches:** the public workflow qualifies seeds 42 and 43 as two separate jobs in parallel, with independent disposable process state and evidence. Their outputs are not byte-for-byte parity claims.
