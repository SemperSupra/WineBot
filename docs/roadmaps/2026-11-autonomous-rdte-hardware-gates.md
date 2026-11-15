# WineBot R020: Autonomous RDTE, deployment and hardware-qualification roadmap

Status: proposed execution plan, public source-only; not a release decision.
Authority at cold start (2026-11-15): `SemperSupra/WineBot@f5ba0256f330958dcf35710a822508cdb31fc40b`.
This roadmap is an independent coordination artifact, not an attempt to merge or supersede draft work. Current authority is the latest Git/DLE and exact-head CI, not this historical snapshot.

## Mission

Deliver a reproducible Windows application/game execution and research environment for:
- automated graphical and non-graphical execution, including games;
- debugging and lawful reverse engineering of authorized workloads;
- identifying and reproducing missing/incorrect Wine functionality;
- recording installation effects to author independently qualified replacement installation recipes;
- concurrent human/agent/automation observation, with explicit input ownership and human takeover;
- keyboard and assistive-technology accessible control surfaces.

No universal feature-parity promises: report capabilities and gaps explicitly.

## Non-negotiable architecture

1. Disposable, digest-pinned WineBot runtime: Wine/upstream/custom runners, display, input, control, instrumentation; container root read-only, no privileged default, ephemeral writable scratch.
2. Versioned, independently replaceable application environment: immutable app payload, dependencies, installer recipe and prefix-template lineage. Treat prefix registry and Program Files as mutable until separately proven safe to overlay.
3. User-scoped persistent state: prefix, user profile, application settings, save games, documents, config, credentials and retained evidence. Backup before migration. No `docker compose down -v` against live data.
4. Cross-cutting evidence and control planes: source-exact run identity, lifecycle, trace, artifact custody, opt-in debug sidecars, observation and control arbitration; do not expose confidential material in public CI.

Prefer a Go standard-library implementation for deployable helpers; Python is acceptable for bounded CI/tests already owned by existing code. Avoid a new orchestration platform when GitHub Actions, OCI tools and existing runtime APIs suffice.

## Authority, in-flight dependencies and holds

- [#154](https://github.com/SemperSupra/WineBot/pull/154): independent opt-in three-layer architecture; focused public replay passed at `bddf3e7a6d2a53ad43871abecd9379983a585ff3`; full CI failed. Draft/unmerged; do not overlap its owned files.
- [#150](https://github.com/SemperSupra/WineBot/pull/150): Wine 11 prefix/startup recovery; focused public startup workflow passed at `d2304d2b2e096a097ffa76b79aeaeef85b72d702`; full CI failed. Long-soak, fault recovery and independent review separate.
- [#123](https://github.com/SemperSupra/WineBot/pull/123): portable contracts and provisional vNext evidence; focused checks passed at `cf9da472bcb82b044ae6f6a945dc5c1e79a5513d`; full CI failed; no legacy conformance waiver.
- [#132](https://github.com/SemperSupra/WineBot/pull/132), [#133](https://github.com/SemperSupra/WineBot/pull/133), [#135](https://github.com/SemperSupra/WineBot/pull/135), [#143](https://github.com/SemperSupra/WineBot/pull/143), [#144](https://github.com/SemperSupra/WineBot/pull/144): isolated CPU graphics/game experiments; retain their RDTE-only, nonmerge status until qualified.
- [#151](https://github.com/SemperSupra/WineBot/pull/151): read-only Agent Dispatch proposal on security review hold; do not assume authority to run a remote workset.
- Separate private publication/disclosure authority controls any sensitive evidence or deployment identity. Do not cross-post private findings to this public repository.
- Retired WineBotAppBuilder is not a packaging platform to resurrect; `winebot-contracts` remains thin portable behavioral conformance only.

## Phased plan, dependencies and gates

| Phase | Independent deliverables | Free-cloud actions | Entry / exit gate |
| --- | --- | --- | --- |
| P0: Discover / baseline | Exact main, PR heads, workflow IDs, first failures, risks, copyright/source rights, no-duplicate DLE map | GitHub connector + public GHA observations | Every live task assigned owner and acceptance evidence; never close a live dependency without proof |
| P1: Disposable core | Runtime/application/persistent state separation, idempotent seeding, external volumes, immutable image IDs | #154 public Linux GHA replay | PASS: restart/replacement preserves user data; destructive operations refused; security review required for promotion |
| P2: Packaging and installation | Runner catalog, offline application manifests, isolated per-app prefix templates; installer before/after inventory and deterministic recipe compiler | Public Ubuntu runner, real redistributable open-source fixtures | PASS: pristine install and reconstructed install independently satisfy application postconditions with exact source hashes |
| P3: Diagnostic instrumentation | Quiesced prefix snapshots, file/registry delta, process tree, ordered event trace, API relay, crash & DLL/COM probes, source-bound evidence | Independent focused public CI workcells | PASS: minimally sufficient reproducible evidence, privacy redaction, bounded memory/size and failure taxonomy |
| P4: Compatibility research | Differential Wine 10/11/current/custom; Windows reference where available; repro minimizer; capability matrix and upstream-ready bug records | Public GHA Linux plus Windows public-runner bounded native oracles | PASS: a real workload failure classified, repeated and isolated from WineBot infrastructure or instrumentation |
| P5: Human/agent/a11y | Input leases, read-only observers, atomic takeover and release, audit semantics; semantic inspection, keyboard/focus and web accessibility | Public GHA synthetic E2E + a11y audits | PASS: no conflicting input, no hidden state changes, keyboard-only tasks and screen-reader hardware/manual gate retained |
| P6: Hardware candidate | Exact digest pair, repeat fault/restart/55-minute soak, Windows GPU/input/audio/controller and actual assistive hardware checklist | Free cloud for preflight only, sovereign/local GPU & native Windows HIL later | PASS: pre-hardware gate below; only then label READY_FOR_HARDWARE_TEST, never READY_FOR_RELEASE |
| P7: O&M | Managed updates, backup restore, compatibility drift, regression triage, quota/cost guard, garbage collection and lifecycle runbook | Scheduled public GHA on bounded source, human-approved releases | PASS: repeatable rollback, retention, alerting and post-upgrade conformance without destructive cleanup |

Parallel cells: P1 state contracts, P2 synthetic installer capture, P3 event schema, P4 public test-matrix design and P5 input/a11y contracts can proceed independently. Serial gates: application snapshot/reconstruction depends on P2 inventory; differential compatibility depends on evidence integrity; hardware admission depends on P1 runtime readiness, P3 diagnostics, P5 safe control and passing exact-candidate integration.

## First bounded workcell: installer prefix inventory

A source-only Go stdlib CLI captures deterministic quiesced Wine-prefix inventory before/after installation and emits a local delta. It does NOT record installer sequencing/process activity or reconstruct installers yet; these are subsequent workcells. It must avoid raw contents in output, avoid following symlinks, omit host root paths and reject traversal/duplicate manifest entries. Treat all outputs as potentially private: do not upload them from public GHA. Synthetic CI fixtures only.

Follow-on recorder: Wine registry `.reg` semantic parser, `reg query` snapshots, Linux inotify/fanotify/strace where permitted, process tree, wineserver/winedebug logs, MSI and setup metadata, time-ordered events. Capture network behavior only with explicit privacy/legal authorization. Reconstructor: manifest + dependency graph + idempotent recipe + rollback snapshot + Windows/Wine application-level postcondition oracle. Replaying clicks alone is not reconstruction.

## Qualification levels and evidence custody

Use ordered, non-interchangeable evidence classes:
STATIC_CONTRACT -> MOCKED_BEHAVIOR -> INFRASTRUCTURE_SMOKE -> PRODUCT_QUALIFICATION -> RELEASE_QUALIFICATION.
A focused PASS does not imply full CI, public source qualification does not imply user hardware qualification, and synthetic fixtures do not imply Windows-game compatibility. Bind every claim to: source SHA, workflow/run/job ID, image digest, fixture hash, runner/capability, test name, first failure and privacy-reviewed result. Do not expose tokens, raw transcripts, host IDs, user profiles, proprietary installers or unreviewed screenshots in public artifacts.

Public Actions only for ordinary automated tests; no private Actions minutes. Use minimal permissions (`contents:read`), pinned checkout/actions, offline tests where feasible, cancel superseded runs and enforce CPU/memory/time quotas. Do not automatically promote experimental images, authorize external host access or merge unresolved security holds.

## Pre-hardware readiness checklist — all mandatory

- [ ] Exact candidate runtime/app manifest and image hashes published to permitted custody with source/license review; runtime launch on immutable layers passes on GHA.
- [ ] Wine 11 or explicitly selected runner passes real service health, repeated long soak, recovery and instrumentation controls; known failing full CI investigated and either fixed or separately accepted with source-scoped rationale.
- [ ] Disposable container recreation, idempotent app seeding, immutable-package rollback and persistent prefix/profile/file restore pass without privileged mounts or destructive operations.
- [ ] At least one real Windows application and one rights-cleared Windows game complete deterministic first launch/input/observable postconditions on available cloud software graphics; failures accurately classified, not hidden.
- [ ] Installer capture passes independent before/after/replay tests for a distributable real fixture; sensitive paths/state never published.
- [ ] Human/agent input arbitration, read-only observation, human emergency takeover and accessible Web UI keyboard/focus checks pass; screen reader and device-specific checks are explicitly reserved for hardware.
- [ ] Dependency pinning, supply-chain scan, public artifact inventory, resource policy, rollback/backup runbook and source-exact evidence pass.
- [ ] A bounded hardware-test manifest states GPU/display, driver, audio, gamepad, Windows reference, accessibility hardware and rollback instructions; no production deployment assumptions.

When **all** above are checked against exact evidence, post `READY_FOR_HARDWARE_TEST` with hashes, known limitations, instructions and a verification link in the owning DLE and notify the owner. Until then status is `NOT_READY`. Hardware-ready is not a production release.

## Autonomous loop, housekeeping and handoff

Each wake: Discover current owning DLE/main and PR heads -> Observe first failing jobs and resource/quotas -> Plan independent READY cells -> Apply bounded authorized changes -> Verify exact-head public CI -> reconcile comments/checklists/branches and close or merge only resolved healthy work with rights/security authority. Preserve RDTE-only draft PRs until gates explicitly permit. Scope failures exactly; never write to a deployment host or consume paid resources without independent authorization. Post minimal next executable baton and cite exact evidence; do not ask user to copy/paste a wall of text.

The task may continue via a scheduled ChatGPT automation if enabled. Do not imply tools continue running after a session merely because this document exists.

## Evidence reconciliation — 2026-11-15 16:38 Europe/Berlin

- Accepted `main@f5ba0256f330958dcf35710a822508cdb31fc40b` unchanged at this observation.
- #155 installer inventory at `ffed1bc33a38915bd51411c181c579ac34af4532`: focused public [run 43729947166](https://github.com/SemperSupra/WineBot/actions/runs/43729947166) **PASS**, full [run 43729947208](https://github.com/SemperSupra/WineBot/actions/runs/43729947208) **FAIL** solely at conformance job; preflight and integration smoke passed. Not an installer reconstruction or hardware pass.
- #154 layered architecture at `af0988d14a408c31a7a1dfdcf3278df2152908f3`: focused disposable contract [run 43729612837](https://github.com/SemperSupra/WineBot/actions/runs/43729612837) **PASS**; [composite Wine11 HIL 43729612802](https://github.com/SemperSupra/WineBot/actions/runs/43729612802) **FAIL** at `startup`; full [CI 43729612729](https://github.com/SemperSupra/WineBot/actions/runs/43729612729) **FAIL** conformance only. Composite failure is a *GitHub-hosted Linux container integration* test, not actual physical hardware. A subsequent #154 source change adds safe, enumerated per-service startup failure classification, pending exact-head rerun.
- #150 Wine11 recovery at `d2304d2b2e096a097ffa76b79aeaeef85b72d702`: focused [startup 43702228758](https://github.com/SemperSupra/WineBot/actions/runs/43702228758) **PASS**; full [CI 43702228722](https://github.com/SemperSupra/WineBot/actions/runs/43702228722) **FAIL** conformance. Standalone startup pass does not prove composite layer startup.
- #123 vNext contracts at `cf9da472bcb82b044ae6f6a945dc5c1e79a5513d`: focused evidence checks pass, full [CI 43701175123](https://github.com/SemperSupra/WineBot/actions/runs/43701175123) **FAIL** conformance. Do not waive frozen legacy-v1 requirements.
- **Hardware gate remains NOT_READY**: composite Wine11 startup fails; full conformance fails; long soak/recovery, real installer reconstruction, human/agent input control, accessibility and game qualification not complete. No candidate digests or hardware test authorization issued.

Next exact independent READY cells: (a) observe #154 diagnostic rerun and fix first classified startup failure without raw public logs; (b) isolate conformance failures by pinned contract and lifecycle/automation/health semantics; (c) implement rights-cleared installer semantic inventory and event capture with private evidence handling; (d) update hardware checklist only after source-exact proof.

## R021 reconciliation — 2026-11-15 continuation

- Authority: accepted `main@f5ba0256f330958dcf35710a822508cdb31fc40b`; #154 and #155 still draft/unmerged. Preserve independent #150 Wine11 and #123 conformance ownership.
- First *observed* composite failure at #154 `488871a41f75fdbcef3e9be8f175d43da7d76248`: [public run 43731051207](https://github.com/SemperSupra/WineBot/actions/runs/43731051207) reported `app-seed exited 1`, `state-init exited 1`, `winebot-interactive created`, `stage=startup`. Wine did not start, so this does **not** establish a Wine API defect. Focused layer contracts passed while full CI still failed conformance.
- Corrective #154 work at `35dbde040b7075af489eb7334aea402f85fc4207` adds strict per-service allowlisted initialization-log categorization with unit/privacy regression tests and pre-build source gate; the prior candidate exposed Ruff import issues, now corrected. Source-exact composite [run 43753063914](https://github.com/SemperSupra/WineBot/actions/runs/43753063914) and [full CI 43753063941](https://github.com/SemperSupra/WineBot/actions/runs/43753063941) were IN PROGRESS when this record was authored; neither can be counted as PASS until terminal evidence is observed.
- Independent #155 installer inventory current `14ed4eda13efe86f9ece4a26254e36cd367e72dd`: safer final-component file opening with O_NOFOLLOW and nonblocking detection of substituted FIFOs; synthetic [run 43752988668](https://github.com/SemperSupra/WineBot/actions/runs/43752988668) PASS. This does not protect malicious concurrent ancestor-directory replacement; actual prefix inspection requires trusted quiesced state. The CLI still does **not** recover installer process sequence, registry-value semantics or reconstruct installers.
- Hardware-readiness checklist **unchanged, all items unverified**. Composite layered initialization, full legacy conformance, real installer reconstruction, long soak, shared control, a11y and games remain acceptance holds. Status: `NOT_READY_FOR_HARDWARE_TEST`; no test manifest or candidate image digest promoted.

Next independent READY cells: observe exact startup reason categories and repair their verified cause in #154; review first conformance mismatch in #123 without waivers; extend #155 to ordered event and semantic registry capture only after private evidence custody and rights-cleared fixture semantics are qualified. Maintain public free-tier-only CI and no destructive volume cleanup.
