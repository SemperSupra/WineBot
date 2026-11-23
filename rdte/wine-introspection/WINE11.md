# R2: Pinned Wine 11.0 native source qualification

This independent research workcell derives from the earlier experiment/wine11-ui-observer-20261024 Wine 11 source-build branch, NOT from production main. It reuses the exact R1 rights-cleared PE64 witness and offline Go contract source blobs, then compiles and executes that witness against the locally built pinned upstream Wine 11.0 WoW64 runtime.

This is a no-source-patch control, not yet an instrumented Wine fork. If successful, it confirms that the Win32 module/heap/memory-current-state query works under the custom-built Wine 11 runtime. The later lifecycle provenance and Wine-owned structure descriptor work remains separate.

Runner: public ubuntu-24.04 GitHub Actions, Docker build, nonroot run, network disabled for execution, bounded resources, no uploads, no image push, no private inputs and no user state.

First-failure phase classification: source tar/checksum, toolchain/configure, compile, PE fixture compile, Wine prefix or architecture, Wine execution, query schema/coverage. Never pass an unsupported result by weakening the Go contract.

Owning DLE: mark-e-deyoung/winebot-research#3. Ghidra/reversing consumer gating: mark-e-deyoung/ghidra-tools#4. No release or main merge authorization.
