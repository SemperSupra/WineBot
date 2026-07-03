# Release Triage -- 2026-07-03

## Scope

This triage reviewed local git state, remote branches, open GitHub issues, open
PRs, local backlog files, formal-model status, test freshness, CI history, and
end-to-end build/smoke evidence.

Repository: `SemperSupra/WineBot`

Current local branch:

- `main` at `e79753c`
- Tracks `origin/main`
- Local working tree has documentation edits from this triage session:
  - `AGENTS.md`
  - `README.md`
  - `docs/DOCKER_ENGINE_ON_WSL2.md`
  - `docs/release-triage-2026-07-03.md`

## Executive Finding

Do not cut a release from current `main` until the CI lint blocker is resolved
and a fresh build/smoke run succeeds after the Docker-on-WSL2 runtime change.

There are no open PRs and no unmerged remote branches containing unique commits,
but there are many stale open issues that should be closed or consolidated so
release decisions are based on current risk rather than old backlog noise.

## Runtime Verification Status

Docker Desktop has been removed. Docker Engine is expected to run inside WSL2
`Ubuntu` using:

```powershell
wsl -d Ubuntu docker <args>
wsl -d Ubuntu docker compose <args>
```

This execution shell could not verify Docker runtime health:

- `wsl -d Ubuntu docker info` failed with `WSL_E_DISTRO_NOT_FOUND`.
- `wsl -l -v` reported no installed WSL distributions in this shell.

Implication: local build/smoke verification is blocked from this environment.
Use the real host WSL2 environment before release.

## GitHub State

### Pull Requests

Open PRs: none.

### Remote Branches

All non-main remote branches are already reachable from `origin/main`; each has
`0` commits ahead of main.

| Branch | Behind main | Ahead of main | Recommendation |
|:---|---:|---:|:---|
| `origin/doc-base-image-decision-4997628729023652350` | 156 | 0 | Delete after confirming no audit need |
| `origin/feature/recording` | 358 | 0 | Delete after confirming recording history is captured in issues/docs |
| `origin/fix/analyze-binary-upload` | 22 | 0 | Delete; fix merged via #73 |
| `origin/input-trace-improvements-16151092667313884564` | 156 | 0 | Delete after confirming no active PR references it |
| `origin/issue-analysis-9012654001753441790` | 159 | 0 | Delete; superseded by this triage |
| `origin/release/v0.9.0` | 313 | 0 | Keep only if release-history branch is intentional |
| `origin/update-winebotctl-docs-13878570105089540832` | 161 | 0 | Delete if docs are merged |

## CI and Test Freshness

### Current CI

Latest `main` CI push runs are failing. The latest checked run was:

- Run `28399266355`
- Commit `e79753c`
- Workflow `CI`
- Result: failure
- Failing job: `Pre-flight (Lint & Unit)`

Local `python -m ruff check .` reproduced the blocker:

- 183 Ruff errors
- Main categories: `SIM105`, `SIM117`, `ARG001`, `B007`, `B017`, `SIM103`, `SIM108`

This means the stricter Ruff configuration is not synchronized with the current
codebase.

### Nightly Soak

Recent nightly soak runs on `main` are passing:

- 2026-07-03: success, about 1h4m
- 2026-07-02: success, about 1h4m
- 2026-07-01: success, about 1h4m
- 2026-06-30: success, about 1h5m
- 2026-06-29: success, about 1h8m

This is useful evidence for runtime stability, but it does not replace the
failing release CI gate.

Follow-up work on PR #89 (`fix/release-ci-lint-2026-07-03`) cleared the release
CI blocker:

- Run `28671547812`
- Commit `4e7ac01`
- Workflow `CI`
- Result: success
- Passing jobs:
  - `Pre-flight (Lint & Unit)`
  - `Integration (Smoke Test) / build-smoke-gate`

Findings from the CI repair:

- Ruff and API mypy gates were restored by aligning rule scope with release
  surfaces and fixing concrete source issues.
- The first PR CI rerun exposed a separate Linux-only unit failure caused by
  CRLF line endings in extensionless shell entrypoints (`scripts/wb` and
  `scripts/bin/winebotctl`).
- `.gitattributes` now applies LF normalization to `scripts/**`, and the
  affected entrypoints were normalized.
- Local Windows cannot execute these POSIX entrypoint contract tests directly
  (`WinError 193`); CI container execution is the authoritative verification for
  those tests.
- A later PR #89 run, `28672050528`, failed during image build because the
  pinned WinInspect v0.1.1 release asset no longer matched the Dockerfile
  checksum. Per release decision, do not fall back to deprecated WinSpy; wait
  for a proper WinInspect release asset and update WineBot to the new
  version/digest under #88.
- The local SBOM/license warning was diagnosed separately: the SBOM generator
  scanned every package installed in the executing Python interpreter, so a
  Windows/global Python environment could inject unrelated packages into the
  WineBot SBOM. The generator now scopes the default SBOM to the installed
  dependency closure rooted at WineBot's pinned runtime and dev/test
  requirements, with `--all-installed` retained for full interpreter audits.

### E2E Build/Smoke Evidence

Most recent documented comprehensive E2E result:

- File: `docs/e2e-test-results-2026-06-28.md`
- Branch: `feat/cv-package-extraction`
- Version observed: `v0.9.7`
- Core WineBot and CV sidecar were documented healthy
- 14 endpoint/feature checks passed after `/analyze` binary upload fix

This is not current for `main` at `e79753c` because subsequent work landed:

- stateless architecture and HF cache changes
- `/models` writable mount changes
- DVC/S3 dataset management work
- MinIO to Garage migration
- Docker runtime architecture changed from Docker Desktop to WSL2 Engine

Release implication: a fresh end-to-end build, test, and smoke run is required.

## Formal Models

Open issue #81 requests formal models using TLA+/Lean-style tooling.

Current codebase status:

- No TLA+, Alloy, or Lean model files were found.
- No model-checker execution is wired into CI.
- Executable invariants do exist:
  - `docs/invariants.md`
  - `tests/test_invariants.py`
  - `GET /health/invariants`
  - conformance suites in `tests/test_conformance_*.py`

Conclusion: implementation-level invariants are present and partly tested, but
formal models are not synchronized with the codebase because they do not yet
exist as executable formal artifacts.

Release implication: this is a release blocker only if the release criteria
require formal verification. Otherwise it should remain an explicit deferred
assurance item.

## Open Issues Triage

### Likely Release Blockers

| Issue | Finding | Recommendation |
|:---|:---|:---|
| #86 CI failing on Python linting | Confirmed blocker; fixed on PR #89 with green CI run `28671547812`. | Merge PR #89 before release |
| #87 Add OpenSSL DLLs for WinInspect runtime | Critical if WinInspect SSH key authentication is part of this release. | Implement before release if WinInspect is shipped; otherwise defer |
| #88 Upgrade bundled WinInspect and evaluate v0.3.x capabilities | WineBot pins WinInspect v0.1.1, but image builds are currently blocked because the pinned release asset checksum no longer matches. Tags through v0.3.3 exist, but no release asset was visible via GitHub API during triage. | Wait for a proper WinInspect release asset; then implement before release if WinInspect is part of the release surface |
| #72 Full E2E test run | Existing E2E evidence is stale for current main and runtime. | Implement as release verification task |

### Stale or Probably Completed Issues

These appear completed or superseded by commits/docs on `main` and should be
closed after spot-checking acceptance criteria:

| Issue | Evidence | Recommendation |
|:---|:---|:---|
| #83 `/models` writable mount | Commit `b0b2491` directly fixes model storage mount. | Close if verified |
| #70 Core image minimal verified | Title says verified; later build-intent work exists. | Close or convert to release note |
| #69 Extract captioning sidecar | Commits `f7d234b`, `d87757b`; E2E doc says package repo/tag exists. | Close if external repo exists |
| #68 Extract kv-ground-server | Commits `b214d73`, `7fcc43d`, `73a1051`; E2E doc says repo/tag exists. | Close if external repo exists |
| #67 Extract desktop-ui-cv | Commits `d1fa595` through `b3a8691`; E2E doc says package installed. | Close if package repo is healthy |
| #66 desktop-ui-cv CI/CD pipeline | Commit `81f4a96`; E2E doc says package extraction verified. | Close if downstream CI exists |
| #63 Extract CV/OCR pipeline | Extraction phases merged in `48ca7ca`. | Close after package import check |
| #57 Add LICENSE file | `LICENSE` exists. | Close |
| #5 Stripped custom Wine build | Issue body says superseded by #7. | Close as superseded |

### Defer as Backlog / Enhancement

| Issue | Recommendation | Notes |
|:---|:---|:---|
| #81 Formal system model | Defer unless formal verification is release criterion. | Prefer TLA+ with TLC for state machines; wire to CI later. |
| #85/#84 Dataset management | Consolidate around Garage+DVC. | #84 still says MinIO; update or close in favor of Garage-era issue. |
| #74 Annotate 30 real desktop frames | Defer unless CV quality claims are part of release. | Useful research validation, not core release blocker. |
| #56 Wine UIA support for pywinauto | Defer. | Feature request. |
| #55 Dashboard trace explorer | Defer. | UX feature; not blocking. |
| #54 Input pipeline health endpoint | Verify; likely partially implemented via `/health/input`. | Close if complete, otherwise defer. |
| #46 XDG runtime/state migration | Defer. | Large compatibility migration. |
| #45 Durable broker state + CAS | Defer unless multi-agent/session durability is release target. | Correctness hardening. |
| #43 OpenAPI property-based fuzz tests | Defer; good assurance item. | Prefer Hypothesis rather than custom fuzzing. |
| #42 Real-network mDNS integration tests | Defer. | Environment-dependent. |
| #41/#40 Recording timeline UX | Defer. | Feature program backlog. |
| #35 Recorder checkpointed finalization | Evaluate risk; defer if current finalization is acceptable. | Could become blocker for long recordings. |
| #34 Detached job TTL/cancel controls | Defer unless exposed automation runs untrusted jobs. | Operational safety. |
| #26 Mypy untyped-body checks | Defer or group with static analysis hardening. | Not a release blocker after Ruff passes. |
| #25 Atomic log cap/write surfacing | Defer unless log loss is release-critical. | Correctness hardening. |
| #23 Bound `/recording/perf/summary` memory | Consider implement before release if endpoint can scan unbounded artifacts. | Small correctness fix if confirmed. |
| #20/#19/#18/#17/#16/#15/#14 Telemetry | Consolidate. | Too fragmented for release gating. |
| #13 Human-visible agent-control indicators | Defer unless human-in-the-loop safety is release headline. | UX safety hardening. |
| #12 Config schema versioning | Defer unless config compatibility is release criterion. | Useful for ops safety. |
| #11 Automated a11y audits | Defer or implement as non-blocking CI. | Prefer axe-core/Lighthouse, not custom scanner. |
| #10 Network partition simulation | Defer. | Prefer toxiproxy/pumba if implemented. |
| #9 Resource quotas per app | Defer. | Feature request; use cgroups rather than custom resource manager. |
| #8/#7 Native Wine event pipe / instrumented Wine | Defer. | Major research/architecture epic. |

## Local Backlog

Tracked local backlog files:

- `docs/local-backlog.md`
- `future_work/BACKLOG.md`
- `issue_analysis.md`
- `issues.json`

The local backlog is broadly aligned with GitHub issues for recording,
conformance, invariant hardening, and understandability hardening.

Recommended cleanup:

1. Move stale local-only items into GitHub issues only if they affect release or
   cross-session tracking.
2. Keep speculative future work in `future_work/BACKLOG.md`.
3. Close or update GitHub issues that were already completed on `main`.

## Dependency / Implementation Guidance

Prefer established tools rather than custom infrastructure:

- Lint fix: use Ruff's rule guidance and Python stdlib `contextlib.suppress`;
  no new dependency.
- Formal models: use TLA+ / TLC for state-machine verification, not a custom
  checker.
- OpenAPI fuzzing: use Hypothesis / Schemathesis if property-based API fuzzing
  is selected.
- A11y: use axe-core or Lighthouse CI.
- Shell linting: use ShellCheck.
- Vulnerability scanning: use Trivy.
- Dataset/model lineage: use DVC with Garage S3-compatible storage; avoid
  reviving custom MinIO TrueNAS app definitions.
- Network chaos: use toxiproxy or pumba.
- WinInspect OpenSSL runtime: prefer OS/distribution-provided or MinGW-sourced
  OpenSSL DLLs pinned in the build, rather than ad-hoc downloads in release
  images.

## Proposed Release Strategy

### Recommended Minimal Release Gate

1. Merge PR #89 for #86 lint/CI synchronization.
2. Run full CI on `main` after merge and confirm green.
3. Verify Docker Engine through the real WSL2 `Ubuntu` runtime.
4. Run a fresh build and smoke:
   - `wsl -d Ubuntu docker compose -f compose/docker-compose.yml --profile interactive --profile test run --rm test-runner scripts/ci/test.sh`
   - `wsl -d Ubuntu docker compose -f compose/docker-compose.yml --profile interactive up --build`
   - health, screenshot, `/health/invariants`, `/health/input`, and lifecycle shutdown smoke
5. If WinInspect is part of the release, implement #87 and smoke
   `wine wininspectd.exe --help`.
6. Close stale completed issues and delete merged stale branches.

### Decision Menu

| Item | Recommendation | User options |
|:---|:---|:---|
| Fix #86 Ruff/CI blocker | Merge PR #89 | Ignore only if releasing without CI is acceptable; defer blocks release. |
| Fresh WSL2 Docker build/smoke | Implement | Ignore only for docs-only release; defer blocks runtime release. |
| #87 OpenSSL DLLs | Implement if WinInspect ships | Ignore if WinInspect is out of scope; defer if SSH auth is not advertised. |
| #88 WinInspect upgrade/evaluation | Wait for release asset, then implement | Defer with #87 if WinInspect is optional; ignore only if removing WinInspect from the image. Do not fall back to deprecated WinSpy. |
| Formal models #81 | Defer | Implement only if formal verification is a release promise; ignore only if issue is closed as out of scope. |
| Stale issue cleanup | Implement | Defer if release code is priority; ignore leaves noisy backlog. |
| Stale branch deletion | Implement after confirmation | Defer if branches are retained for audit; ignore leaves clutter. |
| Dataset management #84/#85 | Defer/update | Implement only if model/data reproducibility is release-critical; update MinIO wording to Garage. |
| CV real-frame validation #74 | Defer | Implement if release claims real desktop CV generalization. |
| A11y audits #11 | Defer | Implement if dashboard accessibility is release-gated. |
| ShellCheck/Trivy local parity | Defer | Implement as quality hardening after CI unblock. |

## Recommended Branching / Tracking Discipline

If the user chooses to implement release blockers:

1. Create `fix/release-ci-lint-2026-07-03` from `main`.
2. Fix #86 in one PR with no behavior changes.
3. After CI is green, create `release/v0.9.8-readiness` or a release checklist
   issue to track the WSL2 build/smoke, #87 decision, and stale issue cleanup.
4. Use issue comments/closures for stale issues, not code commits, unless an
   acceptance criterion is missing.

Do not combine lint cleanup, OpenSSL runtime dependencies, and issue pruning in
one PR; they have different risk profiles and reviewers.
