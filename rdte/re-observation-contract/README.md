# Cross-provider reverse-engineering observation metadata v0

An independent, public synthetic-only Go stdlib **adapter contract candidate**, not a new control plane, actual security attestor, runtime database, or Observatory critic replacement.

Strict, tiny flat JSON metadata envelope for WineBot Win32 self-enumeration, WinBot native NT queries (phnt) and Windows ETW (TraceEvent). It deliberately reports origin=synthetic_fixture, trust=UNVERIFIED and coverage=partial even when the source or run pointer is present. A claimed Git commit SHA is only a self-declared field; it MUST be checked against the authoritative run and exact commit externally. This v0 CANNOT label evidence production LIVE/VERIFIED or represent an app-private semantic type, stable object ID or allocation generation.

Addresses are allowed only from Win32 API observations and then only in a Windows guest process virtual address space. ETW and native-NT probe variants currently emit no pointers; the actual NT query can privately read a PEB but the v0 observation must not confuse a kernel/host pointer with guest VA. No raw memory, target paths, strings, buffer contents or user values are accepted by the schema.

Negative suite tests 3 allowed provider types, source/backend mismatches, fabricated semantic types, invalid address spaces, fake trust claims, bad provenance, duplicate keys, unexpected fields and size limits. No original target or sensitive/private fixture.

Future integration is only through the authorized WineBot/WinBot sensor owners and Ghidra/Observatory consumer, subject to exact source/run readback and the reversing workbench's R030/R126 H0/source/held-out gates. No public research result overrides private DLE, no automatic Ghidra source changes, no profile publication. The important output is an approved source of truth for what UNKNOWN still means.
