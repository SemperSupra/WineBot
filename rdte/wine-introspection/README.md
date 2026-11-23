# Wine Runtime Introspection R1 — no-patch live query baseline

Authority: mark-e-deyoung/winebot-research#3 and mark-e-deyoung/ghidra-tools#4.
Status: experimental public synthetic-only source; NOT a Wine source patch, runtime introspection service, production API or release.

## Question
Can a real PE64 program under unmodified distribution Wine enumerate its own executable module base, one live process heap allocation and the containing virtual memory region via supported Win32 APIs? This is a necessary but insufficient baseline for full Wine-native introspection.

## Test method
- Original MinGW C fixture creates a 256-byte block, uses GetModuleInformation, HeapWalk and VirtualQuery, then writes three ephemeral JSONL records to a dedicated file inside a disposable Wine prefix (not mixed with Wine launcher stdout).
- Offline Go verifier requires precise provenance WIN32_API_ENUMERATED, windows_process_va address domain, same process identity, memory containment and unknown object ID, generation and semantic type. Strict negative tests reject fabricated class identity, host pointers, cross-process contamination, extra fields and bad regions.
- Free public GHA Ubuntu worker compiles PE64, executes it inside a clean Wine prefix, runs Go verifier against bounded output and only publishes fixed PASS/FAIL markers. No binary or raw trace publication.
- All observations are best-effort current-state snapshots. No historical allocation site, object type, source-known wineserver pointer, per-process remote attach or virtual machine support is claimed.

## Next
1. Audit exact Wine 11 loader/ntdll heap/server source and existing no-fork APIs.
2. Build PE32/WoW64 and custom suballocator negative controls.
3. After actual no-patch coverage evidence, propose a small Wine native allocation creation/lifetime hook with bounded loss accounting and disabled-source parity.
4. Integrate a policy-scoped read-only query adapter and Ghidra/Observatory consumer only after current reversing H0/source/critic gates.

Do not merge, publish images or artifacts, deploy to private hardware, or claim product release admission on this RDTE.
