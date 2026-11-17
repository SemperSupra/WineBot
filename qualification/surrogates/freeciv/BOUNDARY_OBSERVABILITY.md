# Boundary-first game observability (public qualification candidate)

Scope: reverse engineer application behavior by connecting *resource operations* to meaningful objects; no private binary, dump, original SMAC, secret, unreviewed capture or host access is authorized. This workcell is a source-known Freeciv **Linux server** control. It does not exercise GDI, DirectDraw, Win32 input, mouse, controllers, video or sound; dedicated WineBot/OpenTTD/SDL/legacy Windows workcells are required for those modalities.

## Inventory, topology, and sensor contracts

1. Discover executable/imports/loaded modules and probable framework/resource boundaries with `readelf`, static Ghidra, ELF load maps and library signatures. Use direct evidence: import/symbol, source-defined callsite or observed stack, not a guessed engine label. On Windows: PE imports/DelayLoad, COM/DirectX/Winsock registrations; on Wine: Win32 relay and host syscall correlation. On native Linux: VFS/glibc/SDL/GL/EGL/OpenAL entry points. Unknown library → `UNKNOWN`, not inferred from a screenshot.
2. Capture file `openat/read/pread64/readv/write/pwrite64/writev/mmap/lseek/close`, archive/decoder hook, engine virtual-resource manager, serializer and game object usage. FD/handle identity must include process lifetime/generation to avoid reuse. Preserve read/write byte span and exact offset **only when observed** (e.g. `pread64`), not inferred from a bare `read`. Distinguish memory-mapped clean/dirtied pages from read/write and append metadata; `strace -yy` path decoration is a hint, not authenticated object identity.
3. Capture input raw hardware events → OS/window/SDL/DirectInput messages → hit testing → intent/command → game state. Preserve device class, scan code/binding, modifier, focus ownership, control mode and allowed action/postcondition. No blind coordinate clicking acceptance.
4. Capture audio buffers (creation, decode, queue, play/stop, mixer, output callback) and frames/graphics (surface/texture creation, draw primitive, source/destination rectangles, transforms, clip, shader/ROP/blit, framebuffer evidence). Correlate decoded asset hash to object-pointer lifetime and eventual output. A draw call may batch many objects; one object may generate many calls. Claims remain hypotheses until controlled perturbation and independent pixel/resource oracle.
5. For each event, distinguish **intended application state** (memory/logic), **presented state** (pixels/audio/UI) and **externalized state** (file/network/device). Use `experiment_id`, `run_id`, module/build hash, process/thread/generation, resource FD/handle, correlation/causal parent, vantage, clock-domain and uncertainty. Raw evidence stays private/ephemeral as required; sanitized digest/counters only in public CI.

## Executable file-I/O control

`io_boundary.py` aggregates annotated `strace -ff -yy` file I/O call classes and counts, rejecting absent, oversized or unsafe traces. `run_io_native.py` runs an actual public Freeciv ELF with scripted AI/game/save commands, observes native I/O metadata and output save, then deletes raw syscall logs/save bytes with the ephemeral runner. This is a producer for evidence classes, not a byte-format decoder. Keep raw source-to-sink provenance inside an authorized private workcell if actual asset bytes are involved.

`python3 qualification/surrogates/freeciv/test_io_boundary.py -v` covers raw-path leak prevention, FD unknown, success vs failed syscall, mmap metadata, bounded traces, invalid/missing files and hostile symlinks. A native PASS can show syscall boundary observability, not game asset format inference or exact byte offsets.

## Automated critique, learning and lower human toil

Treat each inference as a falsifiable claim `{subject, predicate, object, evidence_refs, method, uncertainty, counterevidence, next_action}`. Deterministic oracles reject impossible offsets, corrupt archive lengths, wrong hashes, enum/clock/FD collisions and stale state; statistical critics flag drift/inter-run instability; model critics infer likely formats, decoder libraries, command semantics, draw groups and next experiment, citing *present* evidence refs. An experiment controller chooses a high-information, authorized one-variable change, reruns independent sensors, tests the hypothesis, and converts only verified findings into durable format schemas, signatures, regression tests and Ghidra annotations. Models may suggest and prioritize; they never confer execution, DLE promotion or release rights.

Cross-validation should include reversed control (no action), changed one input/asset, intentionally wrong binary/offset/frame order, repeat across Wine/QEMU/native where eligible, and comparison to source-known Freeciv ground truth. Do not imply a synthetic SDL frame, empty audio baseline or screen classifier is proof of legacy SMAC behavior.

## Current gate

Public Freeciv source-known GHA may execute. Private `ghidra-tools` prototype remains unmerged and not admitted to public runners. Original SMAC/SMAX binary and local/sovereign workcells are deferred under `mark-e-deyoung/reverse-smac#37`. Sidecar/Pandora caller admission is not established. No arbitrary script MCP, public tunnel, private hosted minutes, merge or release.
