# Differential Windows/Wine Compatibility Qualification — implementation plan

Status: **PROPOSAL / DRAFT ONLY**. Updated 2026-10-24. No new runtime qualification, native Windows oracle, public artifact admission, merge, or release is asserted by this document.

## Objective and boundaries

Provide repeatable, evidence-based comparison of the **same admitted Windows executable and scenario** executed on native Windows (WinBot) and Wine (WineBot). Report functionality, API behavior, GUI/accessibility behavior, rendering, performance, and stability **separately**. A Linux/Wine-only result is never native-Windows compatibility proof. Windows native application differences (e.g. modern Windows Notepad versus Wine's replacement Notepad) cannot be treated as same-binary differential tests.

Follow **Discover -> Observe -> Plan -> Apply -> Verify**. Preserve portable required core versus claimed capability versus implementation-specific semantics in winebot-contracts. Do not add general orchestration, proprietary game distribution, privileged mutators, implementation-specific shims, or another control plane to winebot-contracts.

Existing, separately gated work:
- WineBot #123: provisional vNext contract evidence, draft.
- #124: pinned WinInspect packaging repair, draft; #125/#127/#129: public artifact/token/provenance repairs, draft.
- #131: real Wine GUI/window-screenshot probe, disposable RDTE, **not** Windows parity.
- #132: software-renderer probe, disposable RDTE, **not** game parity.
- #133/#135: OpenTTD/SuperTux Windows executable Wine-only probes, disposable RDTE, **not** native Windows reference.
- #134/#136/#138/#139/#140: in-flight WinInspect semantic bridge work, independently gated.
- Private security authority: SemperSupra/agent-dispatch-private#515. Treat unqualified public logs, screenshots, historical artifacts, build history, and reports as unsafe for publication.

## Ownership

| Concern | Owner | Contract |
|---|---|---|
| Qualification plan, Wine execution, WineTest under Wine, Linux capture, renderer matrix | SemperSupra/WineBot | Wine-specific adapter; no release admission |
| Native Windows execution, native UIA, native WineTest, guest/session capability proof | mark-e-deyoung/WinBot | Windows adapter; interactive desktop must be proven |
| Portable scenario/result semantics **only if** genuinely shared | mark-e-deyoung/winebot-contracts | Small versioned schemas; no shared runtime or fleet manager |
| CV inference and labels | SemperSupra/desktop-ui-cv | Optional sensor, not oracle; prevent fixture/training leakage |
| Bounded dispatch, scheduling, admission, resume ledger | Existing Agent Dispatch/DLE | Idempotent work keys, resource locks, retry classification |
| WinInspect | SemperSupra/WinInspect | Read-only observation initially, independently accepted protocol |

## Result states (never collapse to a pass rate)

- PASS: measured assertion passes with a qualified oracle, input identity, and capabilities.
- FAIL: reproducible behavioral incompatibility on admitted target; link first divergent assertion.
- INCONCLUSIVE: conflicting/flaky observations; repeat under controlled environment.
- UNQUALIFIED: absent oracle, unavailable interactive desktop, missing renderer, unsupported architecture, source-admission failure, missing capture capability, or missing evidence.
- INFRA_ERROR: build, acquisition, execution, or observer failure before test outcome.
- SKIP: scenario explicitly outside capabilities; not an implied pass.

Keep **Wine-only observation** distinct from matched Windows/Wine comparative evidence. No acceptance denominators from skipped/unqualified cases.

## Proposed minimal manifests (v0; exact JSON Schema to follow)

Scenario:
- schema_version, scenario_id, scenario_revision, test_class [api, workflow, accessibility, visual, renderer, performance, stability]
- application: source_url-or-admitted-internal-id, executable_sha256, license/provenance, architecture, immutable data-fixture SHA256
- requirements: OS architecture, capabilities, display mode/viewport/DPI/locale, renderer, allowed network/services, runtime budget and isolation
- steps: stable semantic action IDs with target element selectors and fallback strategy, explicit assertions and tolerances
- policy: allowed capture surfaces, publication tier, allowed diagnostic categories, consent/source-distribution constraints
- sequence expectations: preparation -> launch -> ready -> act -> assert -> clean up, with timeouts and deterministic resets

Observation:
- immutable scenario digest, identical executable+fixture digests, run ID and idempotency key, lane [windows, wine], tested checkout SHA **and** PR source-head SHA, OS/runtime name + version, renderer/software versions, viewport/DPI/locale, capabilities actually proven, step IDs and outcomes, bounded duration buckets, reason-code taxonomy, allowlisted artifact digests (if qualified), source/observer version
- no raw host identity, machine inventory, absolute filesystem paths, credential locations, actual network identity, arbitrary GUI titles or error strings in **public projection**
- raw private/source-controlled records remain within their authorized custody; no unsolicited upload
- record data lineage and observer capability so UIA versus Wine OCR fallback is not confused with true semantic equivalence

Comparison:
- key by scenario digest + executable digest + fixture digest + compatible env profile, **not** by run number alone
- demand qualified Windows reference before differential PASS/FAIL
- normalize only nondeterministic IDs, locale-independent time values, dynamic process handles and equivalent semantic fields; do not normalize away substantive errors
- compare assertion outcomes and semantic events first, image regions and accessibility structure second, performance distributions only with controlled repetitions and matching hardware-performance context
- versioned tolerance policy; visual comparison masks only preapproved dynamic regions, and both raw masked images and differences remain unpublished until policy-qualified
- classify probable root cause [API, window/input, filesystem/registry, COM, installer, Wine driver, GDI, Direct3D/OpenGL/Vulkan, CV/observer, harness/infra] as a **hypothesis**, not a verified fix
- fail closed on unsupported schema, duplicate conflicting run IDs, unsigned/untrusted candidate input, mismatched binaries, missing native oracle, or public projection error

## Phased implementation and falsifiable acceptance

### Phase 0 — reconcile gates and probe runner capabilities
1. Independently inspect exact heads/runs for #124/#125/#127/#129 and active #131–#140, without modifying their branches or promoting draft content.
2. Verify WineTest executable location and module list against the **actual** Wine package/custom build. Do not assume Debian Wine 10 includes the test runner.
3. Qualify free public Linux runner: Xvfb, isolated fresh Wine prefix, headless test execution, bounded memory/CPU/time.
4. Qualify public hosted Windows runner for console/API/reference tests separately. Interactive input and screenshot tests need an explicit interactive-desktop capability probe; unavailable/locked => UNQUALIFIED; route to separately admitted native interactive WinBot guest only when available.
5. Perform public-artifact policy check against private security #515 before any new workflow, report upload or public runtime job.

**Exit:** exact-source and runner capability receipts; no secrets or real host identifiers disclosed.

### Phase 1 — schemas, comparator, synthetic falsification (CPU-only)
1. Add schemas and self-contained fixture corpus on a distinct branch; review placement with contracts owner. No new generalized implementation in contracts.
2. Build a Python standard-library comparator taking TWO local observation JSON files, emitting normalized private result and allowlisted public projection. It MUST reject wrong app/fixture/scenario, missing oracle, wrong capability, and malformed data.
3. Property/adversarial tests: identical success, mismatched action, missing Windows reference, swapped executable hash, inaccurate screenshot comparability, flaky replay, hostile free-form text, path/host/secret injection, integer-count inconsistency, duplicate idempotency key.
4. Run locally on synthetic fixtures without Wine or native Windows; validate failure reason codes.

**Exit:** deterministic PASS/FAIL/UNQUALIFIED fixtures with no raw output leak and a written semantics review.

### Phase 2 — WineTest API conformance (native and Wine)
1. Pin upstream Wine source commit/test-binary digest and architecture. Build or obtain the **same WineTest Windows binary** for both lanes with verified custody.
2. Run one small module on disposable Wine/X11 and native Windows (e.g. user32 or dinput after availability probe); capture JUnit privately, publish allowlisted counts+stable IDs only after security admission.
3. Distinguish upstream WineTest API results from portable WineBot/WinBot API contracts. Keep these as distinct suites.
4. Re-run one controlled historical failure and prove regression attribution to exact Wine binary under test.

**Exit:** one matched same-binary same-test API result pair and normalized delta report. Windows reference does not require an interactive desktop for tests that never exercise it.

### Phase 3 — application functional equivalence
1. Compile one tiny redistributable **Windows PE test application** with deterministic file open/save, edit, dialog, keyboard input and screenshotable state; pin exact binary and fixture digest. Run precisely those bytes on both substrates.
2. Use WinBot native UIA/WinInspect observations and WineBot read-only WinInspect plus X11/OCR/CV fallback. Declare unavailable capabilities explicitly; do not infer UIA equivalence from visual pixels.
3. Replay semantic actions through each runtime's own policy-checked broker; preserve control leases and human priority, bounded timeouts, cleanup, and no unmediated input in accepted behavioral qualification.
4. Compare file readback/output hashes and state-machine transitions before visual presentation.
5. Require >=2 identical accepted repetitions per lane for deterministic assertions; different outcomes => INCONCLUSIVE pending flake analysis.

**Exit:** native-vs-Wine executable scenario qualification with feature-by-feature delta, first failure, and exact provenance.

### Phase 4 — visual, accessibility and CV qualification
1. Freeze comparable display settings (DPI, resolution, font, theme, scaling and locale) using opt-in visual profiles; explicitly record deviations.
2. Capture window-scoped frames only; align regions using stable controls/semantic anchors, not hardcoded pixel positions.
3. Compare structural target availability, accessibility navigation, image differences, OCR semantic accuracy, click hit rates and task completion. Accessibility cannot be certified from image similarity.
4. Use desktop-ui-cv as a measured observer; keep train/validation/test partitions separated by application/version/scene, and never train on confidential or disallowed assets.
5. Human review required for ambiguous image differences and accessibility claims.

**Exit:** blinded paired acceptance cases with observation-quality metrics, no unauthorized frame publication.

### Phase 5 — games and renderers
1. Reuse the already pinned OpenTTD/SuperTux Wine-side candidates #133/#135 only after exact-source reconciliation; obtain matched Windows-lane executions before declaring parity.
2. Compare startup, deterministic menu navigation, input round trips, save/load, fixed scripted gameplay, crash/hang rates and sanitized frame deltas.
3. Test LLVMpipe OpenGL and Lavapipe Vulkan separately from GPU adapters; mark absent renderer UNQUALIFIED. Report FPS only with documented bounds and comparable conditions.
4. No game asset publication, redistribution, or model-training admission without explicit license/source clearance.

**Exit:** one accepted game end-to-end scenario per renderer lane, with unsupported paths reported honestly.

### Phase 6 — Wine build A/B and regression loop
1. Treat distro Wine 10 baseline, upstream Wine 11, and any custom WineBot Wine build as separate, immutable candidates; record package/source SHA and effective patches.
2. Run the **same** admitted corpus, configurations and Windows reference; compare Wine A vs Wine B independently of Windows/Wine deltas.
3. For reproducible failures, bisect only if source and compute budget admitted; introduce a targeted failing test, corrective patch, all relevant regression suites, then independent requalification.
4. No automatic merge, default-image promotion or upstream Wine contribution without review and release/security gates.

**Exit:** measured compatibility delta, confidence, first regressions and a reproducible rerun command (with no secret parameters).

## Scheduled work / parallelism

Parallel once input/schema gates are fixed:
- Synthetic comparator and adversarial security tests.
- WineTest binary/module discovery on disposable Linux and Windows runners.
- Existing Wine-only application/game probe reconciliation and manifest generation.
- WinBot Windows runner interactive capability probe and lawful sample-program build.

Sequential:
- Admit public artifact surfaces **before** new public runtime CI/log publishing.
- Define and verify scenario/result format **before** cross-run aggregation.
- Verify same executable/fixture/test source and native Windows oracle **before** parity claims.
- WinInspect bridge and policy-mediated control **before** claiming accessibility semantics or autonomous interaction.
- Independently qualify custom Wine A/B results **before** recommending default image changes.

## First planned acceptance demonstration

The first full vertical slice is a self-owned synthetic Win32 PE app exercising text entry, file save/readback and a message/dialog. Test one immutable binary in a WinBot native Windows guest and a disposable WineBot Wine/Xvfb instance, with common scenario digest and independent adapters. A comparator emits: exact assertion-by-assertion agreement/difference, explicit unavailable-capability fields, two-source provenance, sanitized summary, and a DLE baton. Passing Wine-only smoke never substitutes for Windows parity.

## Durable handoff format

Every bounded action should record: authority; objective; exact repo/ref/source SHA; planned and actual executor; $0/custody/security admission; test inputs and checksums; what ran; raw result custody; allowlisted published result; first failure; evidence links/run/job IDs; decision; blockers; next READY action with acceptance and rollback. No publishable data is assumed safe merely because it was generated on a public runner.

Status as of this plan: **architecture and work decomposition only**. No compatibility comparator, matched native-Windows/Wine run, WineTest paired result or custom Wine build A/B result is claimed by this document.
