# R052 — source-known Ghidra 12.2 static-analysis workcell (public RDTE)

This qualification uses a **real Ghidra headless analyzer** on the publicly packaged Freeciv 3.1.0 Ubuntu 24.04 Linux ELF. It exercises the *static-tool* side of the Reversing observatory without publishing private framework code or game assets.

## Inputs and authority

- Official Ghidra **12.2** release (October 16, 2026) asset `ghidra_12.2_PUBLIC_20261016.zip`, SHA-256 `2c2cd776db3c1f6a097ba418922378ac3649cadd5e844a6f5f088ae628a7be67` as reported by the upstream GitHub release API.
- **JDK 25**, required by Ghidra 12.2, provided by an explicit pinned `actions/setup-java` step.
- Ubuntu 24.04 package `freeciv-server=3.1.0+ds-1build5`, executable SHA-256 `33a15db1dc9a250c7ecf215c3fe6d50c34409301f4bb783914a6b16f3b3e8472` accepted from previous R048–R051 real native workcells.
- Source and status owned by `SemperSupra/WineBot` draft PR #157. Reusable observability contracts owned by private `mark-e-deyoung/ghidra-tools#4`, original SMAC authority by private `mark-e-deyoung/reverse-smac#37`. No cross-publishing or rights expansion.

## Independent observation

Run `analyzeHeadless` in disposable runner scratch with `PublicFreecivWitness.java` as the post-analysis script. It checks the program's original imported SHA-256, iterates FunctionManager functions and **disjoint** AddressSet body intervals, then writes a tiny JSON witness. `validate.py` independently verifies the game executable's raw SHA and the output's exact schema/capacity constraints. Only an allowlisted report containing digest, counts, and `pc_correlated=false` may be uploaded; original ELF, disassembly, functions, addresses, scripts' raw logs and game state never leave the runner as artifacts.

The stand-in tests exercise malformed/forged reports and wrong digest. They **do not authenticate a native Ghidra run**; the exact-head Actions job, checksum gates, script execution, and reviewed provenance are required. Native result remains `NOT_RUN` until the Actions job actually completes.

## Truth boundary and next experiment

A pass would prove a genuine Ghidra 12.2 analysis of the source-known ELF with original-asset identity and a bounded function/range inventory. It would **not** mean a Freeciv instruction pointer was observed or mapped to a particular Ghidra function; the current output explicitly asserts `pc_correlated=false`. The next independent workcell must observe an **actual runtime PC** under a source-known debugger, authenticate the PIE/ASLR module mapping and match it to a non-overlapping Ghidra function interval; wrong digest, wrong ASLR base, unmapped PC and ambiguous function bodies are required adversarial tests.

No licensed SMAC executable, Win98 guest, public private-source copy, private hosted GitHub Actions, merge, release or production deployment is authorized by this experiment.
