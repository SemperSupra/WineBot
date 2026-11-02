# Wine 11 and portable observer — experimental qualification snapshot (2026-11-02)

This is a **public-source-safe, dated evidence index**, not a statement about the shipping WineBot image, a production release, or a default runtime upgrade. Tests were run only against public synthetic fixtures on GitHub-hosted Windows/Linux runners. Do not use these receipts to infer permission for arbitrary window targeting or input control.

## Verified results

| Experimental workstream | Exact public source head | GitHub Actions evidence | Qualification scope |
|---|---|---|---|
| Pristine source-pinned Wine 11.0, installed Win32 observer, two staged versions | `bcd8a8c69eda92b2c9d4f36b69b4a9959168bf04` | [run 41282100925](https://github.com/SemperSupra/WineBot/actions/runs/41282100925) PASS | Fixture-only installed PE, bounded window event sequence and independent cleanup |
| Installed Wine 11.0 lifecycle repeat and negative cases | `00cfdef75eadc0466b57837f39f5987e2d1978d9` | [run 41296816557](https://github.com/SemperSupra/WineBot/actions/runs/41296816557) PASS | Twelve fixture sessions (two versions), contiguous bounded events, EOF/invalid-control/Q and teardown |
| Windows x86/x64 tentative window-target epoch comparator | `bd339759bf0ba6d9a4f15acbec0680ecc141d698` | [run 41297201810](https://github.com/SemperSupra/WineBot/actions/runs/41297201810) PASS | Two sequential controlled fixture instances and fresh synthetic target epochs |
| Wine 11.0 target-correlation differential | `e6e8c47e9f19f9c43af159a2093e0b6fdd2b9963` | [run 41297439350](https://github.com/SemperSupra/WineBot/actions/runs/41297439350) PASS | Synthetic Xvfb/Wine11 comparison with same fixture oracle |
| Read-only portable two-consumer scoped relay | `f42a8cdaf22820995cd0559e097b7f4676885b64` | [run 41296742143](https://github.com/SemperSupra/WineBot/actions/runs/41296742143) PASS | Offline Windows/Linux Go race oracle for stream scoping, cursor gap and broad reinspection hints |
| PowerShell 5.1 externally pinned RDTE manifest | `249409ba4e4cc9c66ec6a428d7bb99fac325ee64` | [run 41296920047](https://github.com/SemperSupra/WineBot/actions/runs/41296920047) PASS | Synthetic Windows package tamper, SHA pin and uninstall custody; pin remains optional in RDTE |

All rows above are **experimental branch-specific**, with zero attached workflow artifacts observed at reconciliation. They do not amend release or default-image manifests.

## Capability claims and nonclaims

- Windows native and Wine 11 have different internals. Only verified event semantics and read-only, bounded consumer behavior should be compared; parity is **not implied** by identical JSON fields or passing synthetic tests.
- Opaque fixture tokens and monotonic target epochs help test stale-reference rejection, but are **not authenticated target identity, trusted process/desktop/session attestation, or authorization tokens**.
- The WinInspect-compatible bridge currently produces only broad desktop *reinspection hints*. It is **not** a live WinInspect RPC provider, a replacement for legacy `events.poll`, or a target-aware inspection service.
- An actuator **preflight negative oracle** is not a live input broker. No unattended input, injection, hooks, privileged Windows/Wine control, deployment or release is approved by these tests.
- Wine 11 experiments and software-rendering/3D draft PRs (#132, #133, #135, #143, #144) do **not** rewrite historical default-image GPU/Xvfb limitations. Software rendering must be measured under the chosen package and display configuration; old categorical notes refer to earlier evaluated configurations.
- The current public repository's GitHub Issues feature is disabled. Historical issue links in [local-backlog.md](local-backlog.md) are **citations of past plans**, not an executable current issue queue.

## Practical interfaces for three audiences

**Human operators:** Do not install experimental binaries or infer availability from CI. Consult actual deployed image version, operator guidance and reviewed release gates.

**Automation:** Gate by explicit runtime capability evidence and verified versioned contract; fail closed on missing support, gaps, unknown postconditions, and stale source or target generations.

**Agents:** Treat observer events as non-authoritative observations. A later authorized actor must separately validate principal, desktop lease, fresh target identity, approved operation and independently measured postcondition before claiming successful control.

## Next independent acceptance steps

1. Produce a **reconciled integration branch** and independent Windows/Linux oracle of combined portable sensor, fanout, target epoch and deny-by-default actuation *without* merging into production.
2. Attest real target identity on Windows and Wine with source/session/process generation binding and red-team window reuse, class spoofing, event reorder, and overflow. No target-aware capability promotion before independent falsification.
3. Integrate a separately authorized *additive* read-only WinInspect provider only after its private owner has admitted the exact protocol and source-custody steps.
4. Distinguish free-tier public synthetic CI from attended desktop/VM acceptance. Keep the release, production branch, private-source and broker authorization holds.

Preserve original first failures and corrected receipts; avoid repeating large pristine Wine source builds merely to check a documentation change.
