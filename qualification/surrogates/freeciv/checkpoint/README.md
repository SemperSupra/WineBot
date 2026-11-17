# R056 — source-known breakpoint + checkpoint proof (public, disposable)

**Owning runtime:** SemperSupra/WineBot draft PR #157. **Shared evidence authority:** mark-e-deyoung/ghidra-tools#4. **SMAC acceptance:** mark-e-deyoung/reverse-smac#37 (original game R3/R4 remains held). This adds no private source, proprietary assets or actual original game execution.

## What this specifically proves

The native Linux x86_64 direct-child ptrace workcell compiles a public C fixture under `-fno-pie -no-pie`, pins the ELF SHA256 and verifies the live `/proc/PID/exe` identity. It plants two software breakpoints (`INT3`) at fixed source-known functions and captures read-only snapshots of one watched 8-byte value **at each stop**. It restores the original instruction word at each hit, rewinds `RIP` by one to execute the genuine instruction and checks clean exit. Two separate launches produce the same baseline and post-action digests. Non-PIE ELF type is verified; a PIE with unknown load bias fails closed.

The tool handles only a process it spawns itself and only three symbol names from the fixture. It has no general-purpose write API or external PID control. All state and machine addresses remain ephemeral. Uploaded metadata is a small allowlisted JSON; no raw trace, registers, payloads, screenshots, file contents, maps, paths, game binaries or source-byte patches. The software breakpoint temporarily changes **fixture** executable text and perturbs scheduling; it is not passive.

This is a **two-value state checkpoint**, not a full-process snapshot or VM restore. An actual VM checkpoint must capture coherent RAM, disk and device state; a savegame checkpoint must verify serialization and reload separately. The current Freeciv turn/save/reload RDTE provides separate proof of the latter. Do not represent a pair of hashes as a complete checkpoint or replay proof.

## External, internal and hypervisor boundaries

- **Internal process hooks:** Wine/Win32 debugger callbacks, Frida Interceptor, Ghidra/GDB attach, game engine assertions, serializer/draw/audio API boundary probes. Require explicit process custody and bounded code mutation approval.
- **External process debugger:** GDB or `ptrace` software or hardware breakpoints; hardware memory watchpoints (`rwatch`, `awatch`, `watch` if supported), loader identity and ASLR controls; snapshots of selected state and exact clock domains. Current fixture exercises **software execution breakpoints** only, no data watchpoints.
- **External VM:** QEMU gdbstub break/watchpoints, QMP lifecycle and VM snapshots; PANDA/QEMU record-replay for reverse stepping if supported by the selected machine/configuration. A QEMU breakpoint must be placed in **guest** coordinates, not the host address of `qemu-system-*`. Check RAM+disk coherence, vCPU race, virtual devices and guest symbol/module load identity.

## Native qualification and falsification

`python3 -W error test_bridge.py -v` compiles real native ELF fixtures and tests: two genuine breakpoints and state digests; repeatability across launches; wrong exact SHA; symlink input; PIE without proven load bias; changed game state; absent symbol. An unqualified case must never be promoted to a pass. The `surrogate-checkpoint-breakpoint.yml` public workflow additionally runs the standalone CLI and inspects its final scrubbed receipt. No private hosted Actions minutes, privileged service, remote MCP exposure, secret, owner host, merger or release authority is needed.

**Next real Freeciv step after source-native acceptance:** Select a function target from public Freeciv/Ghidra intervals using source-backed save/turn cross-references; arm a single per-process breakpoint at the independently verified actual load bias + RVA; execute one command, capture bounded RIP/stack/function event; restore original bytes and restart from known game save in an independent process; correlate event with actual save-file/turn change. Add wrong SHA, wrong bias, thread-hit, missed breakpoint, resource-budget, accidental re-entry and readback negatives before calling action attribution verified. The R055 passive 1/180 function hit remains historical evidence, not proof that a particular function caused a game event.

**Do not attach to original SMAC / Windows 98, publish private observatory source to public CI, or expose raw GDB/QMP/Frida endpoints via a public tunnel without separate explicit authority.**
