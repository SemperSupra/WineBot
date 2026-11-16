# Source-known Freeciv real instruction-pointer → Ghidra interval bridge

This independent *public-source* R054 RDTE probe extends the already qualified
Freeciv 3.1.0 real-game and Ghidra 12.2 controls. It cannot access private
Reversing/SMAC source, game binaries, licenses, or user workcells.

## One independently proven coordinate system

1. Pin the actual Ubuntu 24.04 Freeciv ELF SHA and independently pin the
   original Ghidra release ZIP SHA. The Ghidra headless script exports a **private
   ephemeral** list of half-open *relative virtual address* function body intervals,
   with an exact SHA and image base; the interval list never becomes a public
   artifact. Its entries can be non-contiguous and overlapping; preserve ambiguity.
2. Launch a Freeciv server as an unprivileged *direct child* of a disposable
   public Linux x86-64 runner. Use `ptrace(PTRACE_ATTACH/GETREGS/DETACH)` for
   **read-only** RIP sampling. Never patch code, set registers, or alter child memory.
3. Independently verify `/proc/PID/exe` identity by device/inode, executable
   content SHA and coherent ELF PT_LOAD-to-`/proc/PID/maps` load bias. Convert
   actual RIP to ELF virtual address by subtracting that verified bias.
4. Distinguish RIP in the executable and inside precisely one Ghidra function body,
   RIP inside executable but outside recovered functions, RIP outside the main
   executable, and ambiguous body overlap. Require at least one *actual* unambiguous
   function match and no ambiguous ones for a positive acceptance. Do **not**
   mistake a file-backed memory mapping or a static Ghidra function count for PC
   evidence.
5. Discard real PC values, function positions, names, memory layouts, process logs,
   raw Ghidra intervals and other paths. Publish *only* counts, exact public ELF
   digest, typed classification, and limitations. No raw code/images/game content.

## Negative and operational gates

`test_pc_bridge.py` proves wrong SHA, deliberately wrong load bias, outside-body
and ambiguous-overlap cases, malformed duplicate JSON keys, bool/integer type
confusion and unsafe interval path. On a Linux x86-64 with gcc it also samples a
real *source-known self-built* disposable C child to qualify ptrace separately.

If Ghidra's ELF virtual coordinate base differs from our documented ELF PT_LOAD
coordinate, or if sampled RIPs do not land in a uniquely mapped function body,
report `UNQUALIFIED` with the first failure. Do not artificially rebase results,
create a fabricated function match, or weaken any negative control to obtain green.

Inputs: exact public Freeciv ELF and official release Ghidra 12.2, official Ubuntu
public hosted runner, same existing public WineBot DRAFT #157. Run consumes no
private hosted Actions minutes. No production deploy, merge or original game.

Authority: `mark-e-deyoung/ghidra-tools#4` generic evidence semantics,
`SemperSupra/WineBot#157` runtime/surrogate receipt,
`mark-e-deyoung/reverse-smac#37` owner-held SMAC R3/R4. This is a source-known
public experimental probe and does not authorize original SMAC execution.

## R054 follow-on: idle-loop counterexample and targeted correction

The first real Freeciv head produced **180 read-only RIP register samples**,
all classified `OUTSIDE_IMAGE`, despite verified SHA/inode/mapping and a real
Ghidra interval index. Do not promote this negative to a function match.
The source-known, test-only corrective experiment may attach to its **own**
unprivileged Freeciv child and perform at most 2400 single-step instructions,
while posting one bounded command to wake the event loop. This modifies
execution **timing** but never writes code, memory, registers or files outside
scratch. The runner records passive and targeted classes separately and refuses
any ambiguous or absent match. A ten-test synthetic/native ptrace qualification
covers live attach and single-step/detach on a self-built test ELF.

This is not a timing-faithful observational baseline; compare passive and
stepped experiments and treat instrumentation perturbations as material.

### Repeatability and limitations

The same exact public Ghidra/Freeciv R055 commit passed **two** separate
Actions job attempts: each saw 1 unambiguous function match among 180 actual
RIP samples, with no ambiguous hits. Both public evidence artifacts remain in
GitHub; those runs did **not** invoke the single-step fallback. A separate
source-known *local idle stdin-read* test attempted up to 2400 debugger steps
but did not reach the application text segment; this is a useful warning that
single-stepping a blocking runtime call does not ensure bounded progress into
application code. Do not claim targeted stepping is a native Freeciv success.
The deterministic bounded-abstention test therefore verifies that no function
hit is manufactured when the step budget expires. Use stronger explicit
application-event breakpoints/triggered sampling, independently qualified,
if a future scenario demands guaranteed code-path observation.
