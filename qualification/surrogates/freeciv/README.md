# Freeciv source-known surrogate qualification (public-safe)

**Purpose:** exercise a *real* freely licensed turn-based-strategy executable instead of fabricating original-SMAC parity. This is a bounded native Linux Freeciv server pilot, NOT a Wine, QEMU, 1999 Freeciv binary, Ghidra-native or Alpha Centauri oracle.

**Owner and DLE:** `mark-e-deyoung/ghidra-tools#4` (cross-target observatory), `mark-e-deyoung/reverse-smac#37` (SMAC acceptance and owner-deferred game work). This public WineBot runner-side implementation is independent from private `ghidra-tools` candidate code; no private source has been transferred to public CI.

**Target:** Ubuntu 24.04 official `freeciv-server` apt package (a current descendant of a 1990s turn-based Civilization-style game). Requires package and binary digest in each receipt; do not confuse with 1999 Freeciv 1.9.0, for which source archives exist. License: GPL-2.0-or-later.

**Vantage points:** source-known ELF identity, **ELF64 PT_LOAD segments correlated to actual Linux file-backed /proc/PID/maps by exact executable SHA256 and device/inode, one unambiguous ASLR load bias** (sanitized metadata only; no PC observed), native live process and Linux memory-map region count/RSS, loopback TCP listen/connect, `strace` file/IPC/network/process operations, real in-game `save` command and on-disk output digest, clean termination/cleanup. Sensor data is aggregated into a minimal, no-private-bytes JSON receipt. A positive receipt is a qualified native process/I/O sensor chain, *not* a validated game turn or semantic game-state equivalence.

**Execution:** disposable public `ubuntu-24.04` GitHub-hosted job. Build/runtime dependencies installed only inside that ephemeral runner; game binds `127.0.0.1` and does not announce itself; non-loopback IPv4 connect observations fail; process is timed out and all raw syscall paths/logs/saves are disposed. Public artifact contains only source-known version, hashes and aggregate counts; no raw game files, process memory, private paths, credentials or runtime captures.

**Local synthetic regression:** `python3 qualification/surrogates/freeciv/test_contract.py`.

**Native runner:** `python3 qualification/surrogates/freeciv/probe.py --seed 42 --output "$RUNNER_TEMP/freeciv42.json"` after installing `freeciv-server strace` in an Ubuntu 24.04 ephemeral environment. It intentionally exits nonzero if game startup, loopback, memory sensing, syscall trace, save, or clean shutdown cannot be proven. Check GitHub Actions artifacts/receipts before claiming success; do not silently mark failed native probes green.

**ELF load-map qualification:** `python3 qualification/surrogates/freeciv/test_elf_map_probe.py -v` runs six offline/public-safe tests including a real `/usr/bin/sleep` process, wrong-hash/device-inode, ASLR and malformed-ELF negatives. Success on a live Freeciv job proves the loader's file-backed mappings agree with the observed ELF; it does **not** prove program-counter sensing, Ghidra function provenance, source-line coverage, or same-era/SMAC parity. Public receipts include only status and counts, not raw addresses or paths. An ambiguous or missing map fails the native signal.

**Next independent experiment:** add a real client to generate packet payloads and UI observations; qualify Ghidra headless mapping of source-matched ELF; migrate from native Linux to Wine/PE as a separate differential workcell. Do not execute licensed SMAC/SMAX or Windows 98 binaries until `reverse-smac#37` authorizes that phase.

**Independent batches:** the public workflow qualifies seeds 42 and 43 as two separate jobs in parallel, with independent disposable process state and evidence. Their outputs are not byte-for-byte parity claims.

**Qualification status at admission:** seven offline source-neutral contract tests passed in a disposable session; GitHub native game execution is **NOT_RUN until the public PR jobs report terminal evidence**. Neither runner selection nor a dispatched workflow alone establishes gameplay or observatory integration.

## R050 state-reload semantic qualification — candidate

Alongside source-known Linux syscall tests, a separate process-level test drives
Freeciv's documented `--file` save reload path. It parses only bounded, source-defined
`[game]` fields `turn`, `year`, `phase`, `server_state`, `save_players` and
counts `[playerN]` sections; the reloaded server is required to serialize the same
semantic fingerprint. The control deliberately does not publish raw game saves,
full in-memory state, player identities, logs or filenames. Input bounds, compressed
save expansion limits and duplicate-section/key refusal are tested separately.

This proves only save/reload equality for these fields if **both real runner jobs
PASS**; it does not establish a completed new turn, map/AI identity, full binary
behavior or Windows/SMAC parity. A failed native step is `UNQUALIFIED`, not a
synthetic fixture success. Do not relax the test to match a surprising output;
classify the first concrete failure and adapt only with source-grounded evidence.

`python3 qualification/surrogates/freeciv/test_save_oracle.py -v` is safe offline
and is no substitute for the native Freeciv server workcell.
