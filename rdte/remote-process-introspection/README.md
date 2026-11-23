# R1 out-of-process read-only Windows application observation

An original rights-cleared two-process fixture tests a capability needed for WinBot and WineBot application recovery that the earlier self-enumeration baseline does not establish: metadata-only inspection of a distinct, self-launched synthetic child process.

The parent creates an inheritable private shared page and two private events. The child reserves/commits 8192 bytes and privately exposes only its address, size and PID through inherited shared memory. The parent confirms child identity, queries the region with VirtualQueryEx, and enumerates child modules with EnumProcessModules and GetModuleInformation. The child is signaled to free memory and exit. The application emits only a fixed PASS marker; no raw addresses, PIDs, executable paths or memory contents are logged.

Two independent public cloud jobs compile and run the same original fixture on Windows 2022 (MSVC) and Ubuntu 24.04 Wine (MinGW PE64). A failure on Wine does not invalidate the native Windows result; evaluate each job separately.

This does not certify Wine 11 custom source instrumentation, private application object semantics, allocation provenance, or WinBot production release. The scope excludes arbitrary PID arguments, cross-user process inspection, drivers, elevated privilege and injection. Source, control lease, human preemption, host/H0 and product release gates must be reviewed before production adaptation.

Source authority: mark-e-deyoung/winebot-research issue #3; native adapter: mark-e-deyoung/WinBot issue #55; semantic consumer: mark-e-deyoung/ghidra-tools issue #4. No private GitHub Actions spending.