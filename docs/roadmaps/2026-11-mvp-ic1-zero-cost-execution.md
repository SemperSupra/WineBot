# WineBot MVP-IC1 — zero-cost public-cloud executable delivery plan

**Owner intent:** narrow the existing WineBot effort to the shortest path to one usable, reproducible MVP, retaining the three-layer disposable runtime, lawful Windows application/game workloads, shared human/automation/agent control, persistent user state, and accessible user experience. Do **not** expand the MVP to universal installer reconstruction, advanced Ghidra/SMAC instrumentation, GPU parity, or autonomous Wine patch development.

**Status:** OWNER-APPROVED PRIORITIZATION / PLANNED EXECUTION; not a release decision. **Hardware:** `NOT_READY_FOR_HARDWARE_TEST`. **DLE:** Durable / Legible / Executable. This file describes actions, not proof that those actions have happened.

**Cold-start authority at plan creation (2026-11-17):** accepted `SemperSupra/WineBot@main f5ba0256f330958dcf35710a822508cdb31fc40b`; draft #150 `8c5ed8019a3518cf534b158662755172bfce7c59`, #123 `3acc219a1627a74bdcea6388144cc391ec2b57b4`, #154 `913f08b517a580484c7b1a55ced0c17e98e92c1b`, #155 `8d5ff84756b88de59f6941e3cc4d35fc7ca5a7ac`. Another actor may update heads; reread live refs and workflows before each write. Independent source-exact proofs already exist; **none of these draft components is merged into main**.

## Mission and minimum acceptance contract

An agent or a human can reproducibly create a disposable Wine11 WineBot session from pinned images; acquire and exercise exclusive input; install or provision one rights-cleared genuine Windows GUI application and one genuine Windows game; see meaningful observable results; save and recover user state across disposable-runtime replacement; and reproduce deployment, recovery and known failures using safe, source-bound evidence.

Every MVP acceptance claim must name the **same integration commit**, the runtime/app image *digests* or local no-publication content IDs, source/fixture hashes, GitHub run/job IDs, test stages, evidence type and security disposition. Never combine independently green PR runs into a synthetic release PASS. No frozen contract waiver. No scope expansion because a new reverse-engineering capability becomes interesting.

The minimum acceptance suite, `mvp-ic1`, must test on an integration commit:
- full required CI lint, real startup and **pinned frozen-v1** API conformance;
- immutable runtime/application boundaries; state/app initialization; 55-minute layered trace/resource/health soak; SIGKILL/Openbox fault recovery and runtime destroy/recreate without deleting named volumes;
- one real rights-cleared Windows GUI application and one Windows game: exact upstream acquisition/hash/license, startup, deterministic input action, visible/semantic effect, save/reopen/persistence and no artifact leak; note CPU software-rendering limits and unqualified GPU features;
- human, automation and agent as distinct consumers: same-session read-only observation, one active writer, reject unauthorized/conflicting commands, bounded human takeover, clean release and keyboard-only/focus/accessible Web UI automation. Manual real screen-reader/device checks are explicitly **hardware gates**, not fabricated public-GHA passes;
- app setup/restore and versioned payload/recipe proof, backup/restore of a *Wine-generated disposable prefix* (not merely the already-passed synthetic six-volume fixture), fail-closed corrupt archive and rollback for a failed migration;
- clean source provenance, no private artifacts or raw logs uploaded, source license/privacy review, dependency/security scans, deployment/start/teardown runbook, image hashes and rollback manifest.

## Exactly free cloud venues and custody policy

1. **Primary execution: public GitHub standard hosted GHA** `ubuntu-24.04` / `windows-2025`, with isolated jobs and `contents: read` by default; pinned action SHAs, pinned upstream fixture hashes, short step budgets and `timeout-minutes`. Standard public runners are free; **larger runners and private-repository jobs are excluded**. Expected public runner resources are 4 vCPU / 16 GB RAM / 14 GB disk; avoid large game packs, GPU-dependent jobs, OS snapshot uploads and self-hosted/paid resources.
2. Build + run locally **inside ephemeral GHA runner containers**. Use local Docker images/Compose for all work prior to publication review. Native Windows hosted runner is an *independent Windows reference oracle*, not the remote deployment host. CPU rendering: Xvfb + explicit Mesa LLVMpipe/Lavapipe; no hardware GPU claims.
3. Cache only public licensed dependencies after source/hash checks. Prefer per-run recomputation or validated public caches when small; do not put private prefixes, installed game assets, identifiers, screenshots or raw traces into GitHub cache, Actions artifacts or public GHCR.
4. **Only after security/publication approval**, public GHCR may carry approved, redistribution-permitted OCI runtime and application images by immutable digest. Until then image publication is **DENIED**; use job-local content-addressed images. GHCR current public-container storage/bandwidth policy must be rechecked before promotion. Never publish a Wine prefix containing secrets or personal state.
5. Existing free-tier external VPS infrastructure is **optional and not a prerequisite**. Do not rely on unverified Oracle/other free VM capacity, private credentials, tunnels, free LLM model quotas, or user hardware to claim cloud acceptance. Hosted GHA runners are ephemeral and **cannot be treated as a persistent interactive 24/7 service**. A continuously hosted interactive offering requires a separately authorized and verified always-free host or later local/hardware deployment. The cloud-only outcome is a tested deployable bundle plus temporary acceptance instances, not a falsely claimed hosted product.
6. No private GHA minutes, paid GPU, paid API calls, unpinned proprietary downloads, secret-bearing public issues, uncontrolled upload, unattended external side effects or private machine identifiers. Any violation is a release-blocking failure, not an exception.

## Parallel execution workcells

| Cell | Owner/source | Apply (work) | Verify (exit evidence) | Dependency |
| --- | --- | --- | --- | --- |
| **A — IC1 integrator / top priority** | New **dedicated draft candidate** from exact #154 head, do not mutate main or the running long-soak branch; use independently qualified #150 and #123 SHAs | Create fail-closed bounded cherry-pick/merge plan; union conflicting test manifests without omissions; fold only the minimum #155 installer tooling needed; fix source-only Ruff import order at `scripts/ci/resolve-conformance-units.py` first; keep commit ancestry and exact fixture pins; design minimal build/test/release manifest | Entire ordinary CI GREEN on same commit, pinned frozen-v1 GREEN, regression focused GREEN; no waiver and no unknown merge conflicts | Highest-priority, serial integration of dependencies, runs parallel to B/C/D fixture preparation |
| **B — real GUI and game** | New focused PR based on a pin of IC1 candidate, reuse prior #133 OpenTTD and bounded GUI app evidence without inheriting their old RDTE-only branches | Choose one small rights-cleared Windows **GUI app** (e.g. upstream signed/hashed Notepad++ portable or another license-cleared fixture) and **OpenTTD Windows** game with redistributable graphics; inspect licenses and artifacts, pin exact SHA and versions; boot under **same layered Wine11+Xvfb**; scripted input through WineBot broker, WinInspect observation, deterministic content/save/relaunch; force runtime replacement and confirm save | Stage-gated public replay: acquisition hash → app-layer seed → executable launch → real input → program-specific effect → persistent save/reopen. No mere “visible window=PASS” | Candidate runtime API and writable application state |
| **C — input / 3-audience / accessibility** | Independent branch and existing broker/UI owner | Enforce exactly one writer lease, authenticated audit trail, observer read-only semantics, takeover priority for human, stale lease expiry and emergency stop. Add both API race tests and real UI-driven synthetic task with two competing clients; use browser accessibility audit, keyboard-only focus order and no inaccessible takeover path | Deterministic no-double-writer, blocked nonowner effects, human emergency takeover, focus/readability/a11y automated gates on public runner; reserve real assistive device/screen reader manual qualification for hardware gate | API model established; independent test design in parallel with A/B |
| **D — installer + real-prefix recovery + release evidence** | Narrow selected #155 components, existing #154 state/recovery owner | Run the already qualified synthetic independent WinAPI recipe on the **exact layered Wine11 candidate**; compare genuine Windows PE original vs independent recipe, one clean prefix and recovered prefix; quiesce via wineserver, take six-volume backup, verify hash/tamper, restore into fresh state volumes, test failed app update rollback and idempotency. Add SBOM/license scan, provenance ledger, digest manifest and guarded cleanup | Windows/Wine11 file/registry/postconditions match on exact runtime; meaningful Wine prefix opens after restore; no destructive mount or owner change; public-safe acceptance manifest and rollback recipe | Selected candidate/image, approved fixture and security review for anything publishable |

**Independent tasks:** acquisition/legal fixture matrix; broker negative tests; backup/tamper oracle; static security/provenance; contract conflict resolution. **Serial dependencies:** source-integrated candidate → full CI → real workload + control/recovery convergence → frozen commit/digests → whole-system acceptance → security admission → preview or release decision.

## Test/run topology and work batching

- Run static Go/Python/shell source tests and broker concurrency first, usually as 5–15-minute bounded standard runners; use matrix axes for independently fail-able fixtures, not sequential per-file commits.
- Run real GUI/game/Windows native parity in independent 15–45-minute bounded public standard jobs; initialize one new ephemeral prefix per matrix cell, not the user's existing prefix. Default no network during executable runtime; allow temporary network only to fetch pinned public source/artifacts before isolation.
- Only after source+unit+workload checks on exact candidate SHA are green, run one expensive **55-minute** layered-soak/fault test; do **not** restart this test on documentation-only changes. Use workflow path restrictions, actor-safe concurrency keys, `cancel-in-progress` for superseded short runs, but do not cancel a still-relevant exact-source expensive run merely to edit DLE metadata.
- Emit fixed-category stage verdicts, integer counts and hashes only; raw screenshots/registry contents/trace/host identity and tokens remain runner-local; verify zero unapproved artifacts. Publish no registry secrets.
- For each workcell use Discover → Observe → Plan → Apply → Verify. CI first-failure must be classified (source/test/env/dependency/runtime/product/security); a different unrelated PR's PASS cannot unblock a failing current head.
- Keep **one** active candidate integration branch plus focused experimental PRs. When a child is proven and integrated into its owning draft, close it with a receipt; avoid proliferation of unresolved PRs and worktrees. Preserve independent security and owner-promotion holds.

## Minimal release gates

| Gate | Required before moving forward |
| --- | --- |
| **G0 — source authority** | Pin main + owners, first failures, frozen contracts; PR/DLE status current; disclose only public-safe details |
| **G1 — candidate builds** | One composite head compiles, lint/unit/CI/conformance pass, immutable runtime/app state verified; all known source errors fixed |
| **G2 — real product tasks** | Real Windows GUI app + game pass input/action/output/save/relaunch on **same exact candidate**; repeatability and precise failure taxonomies |
| **G3 — safe operation** | Three-audience leases/takeover/a11y automated tests, nonroot persisted state restoration, corrupted-backup rejection, installer replay and rollback |
| **G4 — distributable candidate** | Fully pinned build/image hash manifest, SBOM/license/security review and clean install/upgrade/rollback docs; release authority explicitly granted; no secret/publication incidents |
| **G5 — hardware-admission** | Existing roadmap's complete pre-hardware checklist with exact proof, expected GPU/input/audio/display/assistive-device matrix and rollback instructions. Mark `READY_FOR_HARDWARE_TEST` only when every G0–G5 prerequisite is met; **not** a release decision |
| **G6 — MVP release** | Human-approved tagged immutable release, repeatable clean deployment, product security/privacy checks, supported workload declarations, rollback and operational O&M. Manual device/hardware testing cannot be claimed under cloud-only execution |

Developer preview is a *separate*, explicitly labeled milestone after G1/G2 and reviewed distribution constraints; it is never silently treated as a supported MVP release. A fail at G0–G4 means no tag/push or `READY_FOR_RELEASE`.

## Roadmap reprioritization and exclusions

**70% engineering attention:** A+B+C together, measured by closure of integrated acceptance gates, not repeated synthetic fixtures. **20%:** D reliability, security and release docs. **10%:** research such as Freeciv/Ghidra, generic reversing, novel critics, universal installer synthesis, model benchmarking, GPU optimization, additional engines. These RDTE PRs may proceed in isolated public free-tier jobs without modifying the IC1 candidate or stealing its long-build acceptance venue.

Do not block IC1 on general-purpose MSI/EXE reconstitution, perfect graphics, CV model training, hardware FPS or all Windows application compatibility. One explicitly supported application and game with rigorous input/output/postconditions is sufficient to establish a narrow MVP envelope.

## DLE receipt schema and actionable follow-through

For each merged/closed/held workcell write:
`{owner, source_sha, base_sha, workflow_run_id, job_id, test/fixture_sha, environment, result(PASS|FAIL|UNQUALIFIED), first_failure, evidence_class, public_custody_check, next_READY, blocker, PR/issue_disposition}`.

First independent READY actions:
1. **A:** lint-only fix in a bounded candidate, pinned source merge from #154 and #123; do not edit their existing held branches. Fail closed for unexpected conflicts.
2. **B:** build a low-disk, verified rights-cleared Windows GUI + OpenTTD fixture matrix on new disposable standard Ubuntu runners; program postconditions, not just windows.
3. **C:** broker takeover/concurrent observers/keyboard UI race test against frozen API.
4. **D:** rerun verified original-vs-declarative fixture under exact layered Wine11, plus quiesced Wine-created state backup/restore and tamper/rollback.
5. **Acceptance:** freeze integration SHA after source tests, run full suite, 55m soak and release/publication guards; report pass/fail per gate and keep release blocked until verified.

Authority remains owning Git/DLE and live CI—not this plan's historical SHAs. No background tasks promised without an existing enabled scheduler/explicit workflow execution; all published claims must be actual terminal results.
