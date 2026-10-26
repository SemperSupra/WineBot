# Synthetic Wine WinEvent bounded soak and resource-envelope RDTE — 2026-10-26

Authoritative DLE: https://github.com/mark-e-deyoung/winebot-research/issues/1.
Parent head: `qualification/wine-events-long-lived-20261025@0386d0e9e3b2cecefd7a4dd1693ff5c8fa4ba121`.
Exact public receipt: Actions 40245086851, both jobs SUCCESS, 57 fast tests, actual Wine 14-second readiness, local Q-stop, 192-event terminal overflow and source erasure PASS, zero attached artifacts.

## Independent, smallest READY experiment

No production, release, merge, consumer API schema, source patch, external endpoint, user-program window monitoring, or per-actor authority change.

Under Wine/Xvfb on a disposable public Linux runner, after the previously-qualified real API + overflow controls:

1. Start one **fixed-argv**, synthetic `WB_RDTE_WINDOW`-class Win32 observer under the existing `OwnedWineEventProcess`, on the preexisting temporary Wine prefix; require actual internal `ready`.
2. Keep it idle 20 seconds without synthetic fixture windows. Observe no synthetic events, with a stable identity/sequence and strictly monotonic resource counters.
3. Launch the already qualified fixed Win32 GUI fixture four times, one at a time, each under a nine-second bound; verify each run exits successfully, and that all observed source sequence numbers are consecutive (no skipped or duplicated event identifiers). Require at least eight total callbacks including `show` and `location`.
4. Keep the same observer alive until a total 70-second sample horizon, with a hard Python owner deadline 94 seconds (below the admitted Wine-side 120-second lifetime) and an outer 115-second shell watchdog; no auto-restart/replay. Stop the owner and require closure and erasure.
5. Sample cgroup-v2 aggregate counters *inside the disposable container* at bounded intervals. The harness reads only `cpu.stat:usage_usec`, `memory.current`, `memory.events:oom_kill`, and `pids.current`. No `/proc` dumps, process names, titles, screenshots, token values, host identity, hardware topology or exported dataset.

The **measurement envelope covers the whole Wine/Xvfb test container**, not only the observer process and **is not process RSS**. No observer-specific CPU/RSS claim will be made. The Docker invocation remains cap-dropped, network-none, nonroot, `--cpus=2 --memory=4g --pids-limit=256`. The code enforces softer fail-closed ceilings: memory peak strictly below 3.5 GiB, PID peak below 220, memory growth below 1 GiB, no increase in OOM kills, CPU accounting delta no greater than 2.2 CPU-equivalents over the horizon, and first 20 seconds' aggregate quiet utilization below one CPU-equivalent. The test requires at least 45 strictly ordered samples over at least 60 measured seconds; an absent/unreadable cgroup-v2 metric is **UNQUALIFIED**, never a pass.

No exact resource values are published; only allowlisted stage PASS/FAIL enums. Reproducible test-case constants and source IDs may appear, but no host-side resource inventory. Machine-dependent baselines and mutable public image tag are limitations, not evidence of product capacity. A positive result establishes one bounded rep on an opportunistic free runner, not latency percentiles, memory-leak absence, 24/7 operation, native Windows, UIA/MSAA, CV, games, or multi-actor identity.

## Red/blue-team and three-audience contract

- A hard check rejects gaps, duplicate events, missing ready, source unavailable, timeout, nonzero fixture exits, too-few window callbacks, resource counter reversals, cumulative memory/pid/CPU ceilings and OOM kills. It may falsely reject due to incidental container activity; that should be reported as a scope limitation, not masked.
- All consumers have the same authenticated read-only session observer schema and the existing strict once-per-session start. Human-facing UI must distinguish `ready`, `unavailable`, `history_gap`, and unqualified capabilities, without claiming assistive technology readiness. Automation obtains the same cursor/lifecycle contract. Agents cannot select processes, submit events or acquire privileged scopes. Per-actor independent authentication and accessible UI are **not** qualified by this RDTE.
- No same-session restart or silent replay until a collector-generation identity is incorporated into versioned cursor contracts and independently consumer-tested; no new endpoint or mutable shared portable contract under this experiment.
- Source custody and security authority `SemperSupra/agent-dispatch-private#515` remain open. Existing WineBot legacy conformance is red and WinInspect, gameplay/rendering, assistive/CV and native WinBot lanes remain independent. No private runner, spending, GH artifact upload, screenshot or raw log publication.

## Verification and next baton

Run new branch-only public workflow `wine-events-soak-rdte.yml`, first nine hermetic cgroup-envelope tests plus all previously qualified lifecycle regressions, then actual Wine API/overflow/70-second soak. Check exact workflow `head_sha`, terminal job conclusions, first failing phase and attached artifact enumeration. Any red result remains RED; patch only this branch and requalify. Record all exact receipts in DLE #1 before handoff.

If green: compare across at least two bounded independent free CI runs (disclosure-safe bins) and assess a versioned `session_id + collector_generation + sequence` consumer cursor extension with adversarial handover/restart tests **without enabling restart**. Ask owners separately for per-actor identity, source/capability policy, AT/UIA and release gates. Current public base reference is tag-pinned, not digest-pinned; before a quantitative Wine10-vs-Wine11 A/B claim, obtain an immutable base digest under independent source/custody admission.
