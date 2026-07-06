# Release Triage - 2026-07-05

## Scope

Session-start triage for release readiness after WinInspect v0.4.0 became
available upstream.

Repository: `SemperSupra/WineBot`
Branch inspected: `fix/release-ci-lint-2026-07-03`
Open PR: #89, draft, mergeable. CI was rerun after the WinInspect v0.4.0
update and read-only API integration; latest run `28753849320` is green.

## Closeout Update - 2026-07-05 PM

### Current Status

- PR #89 remains open as a draft and is mergeable.
- Local branch `fix/release-ci-lint-2026-07-03` is synchronized with origin at
  commit `5f0c0dc`.
- Latest PR #89 CI run `28753849320` passed:
  - `Pre-flight (Lint & Unit)`
  - `Integration (Smoke Test) / build-smoke-gate`
- The integration smoke includes `scripts/diagnostics/smoke-wininspect.sh`,
  which validates WinInspect CLI/daemon startup, loopback daemon readiness,
  capabilities, and top-window listing under Wine.

### Implemented Since Initial Triage

- WinInspect v0.4.0 Dockerfile pin and checksum were pushed to PR #89.
- WinInspect v0.4.0 checksum was refreshed to match the republished upstream
  portable asset:
  `83b64999fef9ab01d749ab94193899e3915774d217900ac80c3c34021ff3e416`.
- Added a read-only WinInspect client in `api/core/wininspect.py`.
- Added read-only endpoints:
  - `GET /health/wininspect`
  - `GET /wininspect/capabilities`
  - `GET /wininspect/windows`
  - `GET /wininspect/window/{hwnd}`
  - `GET /wininspect/screen`
  - `GET /wininspect/pick`
  - `POST /inspect/window` using the WinInspect backend
- Added focused tests in `tests/test_wininspect.py`.
- Updated API and WinInspect integration docs.

### Current Release-Gate Interpretation

- #86 CI lint/type gate: resolved by PR #89 if merged.
- #87 WinInspect runtime dependency check: resolved by PR #89 if merged; no
  speculative OpenSSL DLL vendoring is indicated by current smoke evidence.
- #88 WinInspect upgrade/evaluation: resolved by PR #89 if merged.
- #72 full E2E: still open. CI build-smoke is current, but a manual/operator
  E2E pass from the real WSL2 Docker host remains pending.
- #81 formal models: still deferred. No executable formal model artifacts exist.

### What Worked

- CI confirmed the updated image builds and smokes with WinInspect v0.4.0.
- The WinInspect read-only API slice gives WineBot structured HWND/window/screen
  inspection without exposing mutating WinInspect methods.
- Mutating methods are explicitly blocked in the WineBot WinInspect client until
  they can be routed through Input Broker authorization and existing traces.

### What Did Not Work

- This sandbox could not run local WSL2 Docker verification because
  `wsl -d Ubuntu` was not available here (`WSL_E_DISTRO_NOT_FOUND`).
- Local Windows-host mypy still reports a platform-only `os.statvfs` typing
  warning if run directly on `api/utils/files.py`; CI mypy runs under Linux and
  passed.
- Formal models could not be synchronized or executed because they do not yet
  exist as executable artifacts.

### Next Steps

1. Decide whether to mark PR #89 ready for review.
2. After PR #89 merges, close #86, #87, and #88 with CI run `28753849320` as
   evidence.
3. Run and document the manual WSL2 host E2E/operator smoke when the actual
   `Ubuntu` Docker host is available.
4. Keep #72 open until that manual E2E evidence exists.
5. Keep #81 open/deferred unless formal verification becomes a release promise.

## Changes Made

- Updated `docker/Dockerfile` from WinInspect v0.1.1 to v0.4.0.
- Updated the pinned portable asset URL:
  `https://github.com/SemperSupra/WinInspect/releases/download/v0.4.0/WinInspectPortable-v0.4.0.zip`
- Updated the SHA256 pin:
  `83b64999fef9ab01d749ab94193899e3915774d217900ac80c3c34021ff3e416`

Upstream release:

- `WinInspect v0.4.0`
- Published: `2026-07-05T18:10:32Z`
- Assets: portable zip, portable zip SHA256, installer, installer SHA256.

Direct asset verification passed on the host:

- Downloaded `WinInspectPortable-v0.4.0.zip` to `C:\tmp`.
- `Get-FileHash -Algorithm SHA256` matched the published checksum.
- Note: the upstream v0.4.0 portable asset was republished during this triage.
  The current pin matches the current `.sha256` sidecar.
- Zip contents:
  - `wininspect.exe`
  - `wininspectd.exe`
  - `wininspect-gui.exe`
  - `config.default.json`
  - `LICENSE`

## Current Findings

The findings below record the initial triage state. Where they conflict with
the closeout update above, the closeout update is authoritative.

### Critical Release Items

1. WinInspect image-build blocker (#88)
   - Status: implemented locally by updating the Dockerfile pin to v0.4.0.
   - Verification: direct asset checksum passed.
   - Remaining risk: Docker build could not complete in this session because
     Docker Hub timed out while resolving `debian:trixie-slim`.
   - Recommendation: implement. Push to PR #89 and rerun CI.
   - User options:
     - Implement: keep this change, push PR #89, rerun CI.
     - Defer: leave PR #89 red and block release.
     - Ignore: only acceptable if WinInspect is removed from the release image.

2. Fresh end-to-end build, test, and smoke (#72)
   - Status: not current.
   - Latest documented comprehensive E2E result remains
     `docs/e2e-test-results-2026-06-28.md`, which predates later runtime,
     Docker, dataset-registry, and WinInspect changes.
   - Local targeted Docker build was attempted three times and failed before reaching
     the WinInspect layer due Docker Hub network timeouts.
   - Recommendation: implement before any runtime release.
   - User options:
     - Implement: run WSL2 Docker build, containerized tests, health smoke,
       input smoke, invariant smoke, and lifecycle shutdown smoke.
     - Defer: acceptable only for a non-runtime documentation release.
     - Ignore: high risk; release would lack current end-to-end evidence.

3. WinInspect runtime dependency check (#87)
   - Status: unresolved.
   - v0.4.0 portable zip does not bundle OpenSSL DLLs or other DLLs.
   - The release notes include Wine 10.0 compatibility fixes, so the dependency
     issue may be fixed upstream or may rely on the existing Wine/runtime image.
   - Recommendation: implement as a smoke-test item, not as speculative DLL
     vendoring. Prefer established OS/MinGW packages if DLLs are actually
     missing; do not add ad-hoc binary downloads.
   - User options:
     - Implement: build image and smoke `wine wininspectd.exe --help`.
     - Defer: acceptable if WinInspect SSH/TCP features are not advertised in
       the release.
     - Ignore: acceptable only if WinInspect is not part of the release surface.

4. PR #89 release CI path (#86)
   - Status: PR #89 previously had a green CI run `28671547812`.
   - Latest branch CI run `28695030403` failed because the old WinInspect
     v0.1.1 checksum no longer matched; the smoke job was skipped.
   - Recommendation: implement by pushing the v0.4.0 update and rerunning PR
     CI. Merge only after current CI is green.
   - User options:
     - Implement: push current branch and rerun checks.
     - Defer: blocks release.
     - Ignore: only acceptable if releasing without CI gates.

### Formal Models

No TLA+, Alloy, Lean, PlusCal, Apalache, Spin, or SMV model files were found.
The `models/` directory contains ML/model artifacts and datasets, not formal
models. No formal model checker is wired into CI.

Executable implementation invariants are present:

- `docs/invariants.md`
- `tests/test_invariants.py`
- `/health/invariants`
- conformance tests under `tests/test_conformance_*.py`

Conclusion: formal models are not synchronized with the codebase because they
do not yet exist as executable formal artifacts. Issue #81 remains the tracker.

Recommendation: defer unless formal verification is a release promise. If
implemented, use TLA+ with TLC for lifecycle/input-broker state machines first;
do not build a custom checker.

User options:

- Implement: create a small TLA+ model for the input broker/lifecycle state
  machine and wire TLC into CI.
- Defer: recommended for the current runtime release; keep #81 open.
- Ignore: only if formal methods are explicitly out of scope and #81 is closed.

### Test Freshness

Current session checks:

- `python -m ruff check .`: passed.
- `python scripts/ci/verify-capability-matrix.py`: passed.
- Direct WinInspect v0.4.0 checksum verification: passed.
- `python -m pytest tests/test_invariants.py ...`: failed on Windows because
  importing runtime modules requires Linux `fcntl`.
- Targeted Docker build: failed three times before reaching project layers due Docker
  Hub timeouts resolving `debian:trixie-slim`.

Current CI evidence:

- PR #89 CI `28671547812`: success on 2026-07-03.
- PR #89 CI `28695030403`: failure on 2026-07-04 due the old WinInspect
  v0.1.1 checksum mismatch.
- Main nightly soak `28731307845`: success on 2026-07-05.

Conclusion: portable local checks are current, but release-grade containerized
tests, image build, and smoke are not current after this WinInspect update.

### Branches

Only one remote branch is ahead of `origin/main`:

| Branch | Behind main | Ahead of main | Release relevance |
|:---|---:|---:|:---|
| `origin/fix/release-ci-lint-2026-07-03` | 0 | 8 | Active PR #89; should receive the WinInspect update. |

Other remote branches are fully merged or historical:

| Branch | Behind main | Ahead of main | Recommendation |
|:---|---:|---:|:---|
| `origin/doc-base-image-decision-4997628729023652350` | 156 | 0 | Delete after audit confirmation. |
| `origin/feature/recording` | 358 | 0 | Delete after confirming recording history is captured. |
| `origin/fix/analyze-binary-upload` | 22 | 0 | Delete; merged/superseded. |
| `origin/input-trace-improvements-16151092667313884564` | 156 | 0 | Delete after confirming no active references. |
| `origin/issue-analysis-9012654001753441790` | 159 | 0 | Delete; superseded by release triage docs. |
| `origin/release/v0.9.0` | 313 | 0 | Keep only if used as release-history branch. |
| `origin/update-winebotctl-docs-13878570105089540832` | 161 | 0 | Delete if docs are merged. |

### Open Issues and Backlog

Release-critical or decision-gated:

| Item | Related tracking | Recommendation | Trade-off |
|:---|:---|:---|:---|
| WinInspect v0.4.0 upgrade | #88, PR #89 | Implement | Fixes current image-build blocker; needs CI rerun. |
| WinInspect runtime dependency smoke | #87 | Implement as smoke | Avoids speculative DLL vendoring; requires built image. |
| Full E2E run | #72 | Implement | Required for runtime release confidence; costs host build time. |
| CI sync/lint gate | #86, PR #89 | Implement/merge after green | Release without this weakens CI discipline. |

Recommended defer:

| Item | Tracking | Recommendation |
|:---|:---|:---|
| Formal models | #81 | Defer unless formal verification is release-gated. |
| Dataset/model lineage | #84/#85 | Defer/update around Garage+DVC; avoid stale MinIO wording. |
| Real desktop frame annotation | #74 | Defer unless CV claims are release-gated. |
| Dashboard trace explorer | #55 | Defer as UX feature. |
| XDG migration | #46 | Defer; compatibility-sensitive migration. |
| Durable broker CAS | #45 | Defer unless multi-agent durability is release target. |
| OpenAPI fuzz tests | #43 | Defer; use Schemathesis/Hypothesis if selected. |
| Real-network mDNS tests | #42 | Defer; environment-dependent. |
| Recording timeline UX | #40/#41 | Defer as feature backlog. |

Local backlog remains aligned with GitHub issues for recording, conformance,
invariant hardening, and understandability hardening. Keep local-only backlog
items local unless they need cross-session release tracking.

## Proposed Strategy

Recommended release path:

1. Implement: keep the WinInspect v0.4.0 Dockerfile update on PR #89.
2. Implement: push PR #89 and rerun CI.
3. Implement: run a fresh WSL2 Docker build and smoke once Docker Hub is
   reachable:
   - `wsl -d Ubuntu docker compose -f compose/docker-compose.yml --profile interactive --profile test run --rm test-runner scripts/ci/test.sh`
   - `wsl -d Ubuntu docker compose -f compose/docker-compose.yml --profile interactive up --build`
   - health, `/health/invariants`, `/health/input`, screenshot/input smoke,
     WinInspect `wininspectd.exe --help`, and lifecycle shutdown.
4. Defer: formal models #81 unless release notes promise formal verification.
5. Defer/update: dataset issues #84/#85 so they reflect Garage rather than
   MinIO.
6. Implement after release gate: close completed stale issues and delete merged
   stale branches.

Do not combine runtime dependency fixes, stale-issue cleanup, and formal-model
work in the same PR. They have different risk profiles and review criteria.
