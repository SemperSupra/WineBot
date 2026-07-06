# Architecture Review: CV Extraction from WineBot

**Date:** 2026-07-06
**Reviewer:** Automated architecture assessment
**Scope:** Three-repo extraction of CV/OCR pipeline from WineBot monorepo

---

## 1. Executive Summary

The WineBot project has extracted three CV-related repositories from its monorepo:
`desktop-ui-cv`, `kv-ground-server`, and `ui-captioning`. The extraction was
mechanically correct (files were copied to new repos) but architecturally
**premature and incomplete**. Key findings:

- **desktop-ui-cv** has the strongest case for independence but its Dockerfile
  and CI workflow still reference monorepo paths — they will not build standalone.
  Its server entrypoint is a 1321-line god script that conflates 7+ distinct
  concerns (detection, OCR, CLIP search, captioning via third-party API,
  benchmarking, temporal tracking, watch loops).

- **kv-ground-server** and **ui-captioning** are too small to justify separate repos.
  Each has a single server file (~3.5KB each) with no tests, no CI, no pyproject.toml,
  and no release process. They are lightweight FastAPI wrappers around model inference
  — natural candidates for optional extras of the desktop-ui-cv package, not independent
  repos with their own lifecycle.

- The three extracted repos **do not have independent reasons to exist**.
  They share consumers (WineBot API server), runtime (Python 3.12+, CUDA Docker),
  release cadence (coupled to WineBot releases), and ownership (same team).
  No repo can be changed, tested, versioned, or deployed independently of the others
  in practice.

**Recommendation: Consolidate to two repos maximum**, or better, a single
`desktop-ui-cv` repo with optional extras and the other two as subdirectories
within it. See detailed analysis below.

---

## 2. Current-State Architecture Assessment

### 2.1 System Map

```
WineBot Monorepo (SemperSupra/WineBot)
├── api/                       # FastAPI server — orchestrates everything
│   ├── routers/automation.py  # Calls sidecar API, WinInspect API
│   ├── core/wininspect.py     # WinInspect integration
│   └── server.py              # Main entrypoint
├── docker/
│   ├── Dockerfile             # Core WineBot image (minimal — CV deps removed)
│   ├── Dockerfile.cv-analyzer       # CPU sidecar (superseded, retained)
│   └── Dockerfile.cv-analyzer-gpu   # GPU sidecar (active) — 165 lines
├── scripts/diagnostics/       # 45+ scripts, many still coupled to CV
│   ├── cv-sidecar-server.py   # GOD SCRIPT: 1321 lines, 40+ endpoints
│   ├── cv-analyze.py, cv-watcher.py, etc.  # CLI tools
│   ├── benchmark_*.py         # Benchmarking suite
│   ├── workflow_*.py          # Workflow testing
│   ├── ocr_engines.py         # LEGACY — still referenced by cohort scripts
│   ├── ui_detectors.py        # LEGACY — still referenced by cohort scripts
│   └── ... (30+ more files)
├── packages/
│   └── desktop-ui-cv/         # Source mostly .pyc only; remote source of truth
└── compose/docker-compose.yml # Deploys sidecar as service

Extracted Repos (SemperSupra/*)
├── desktop-ui-cv              # Python package + server
├── kv-ground-server           # Single-file server
└── ui-captioning              # Single-file server
```

### 2.2 Current Dependency Flow

```
WineBot API ──HTTP──> cv-sidecar (container on port 8001)
                         │
                         ├──> winebot_cv.detectors (package install)
                         ├──> winebot_cv.ocr (package install)
                         ├──> winebot_cv.registry (package install)
                         ├──> winebot_cv.embedding (package install)
                         │
                         ├──HTTP──> kv-ground-server (port 8003)
                         │              └──> KV-Ground-8B model
                         │
                         └──HTTP──> ui-captioning (port 8002)
                                      └──> Florence-2 model
```

### 2.3 What Was Extracted vs What Remains

| Component | In desktop-ui-cv repo? | Still in WineBot? |
|:----------|:-----------------------|:-------------------|
| winebot_cv.detectors.engines | ✅ (54KB) | ❌ Removed |
| winebot_cv.ocr.engines | ✅ (25KB) | ❌ Removed |
| winebot_cv.registry.model_registry | ✅ (37KB) | ❌ Removed |
| winebot_cv.embedding.clip | ✅ (20KB) | ❌ Removed |
| winebot_cv.dataset.generator | ✅ (108KB) | ❌ Removed |
| winebot_cv.classification | ✅ (stub) | ❌ Removed |
| winebot_cv.tracking | ✅ (stub) | ❌ Removed |
| server/cv-sidecar-server.py | ✅ (50KB, same file) | ✅ (still entrypoint) |
| ocr_engines.py (legacy) | ❌ | ✅ (cohort scripts need it) |
| ui_detectors.py (legacy) | ❌ | ✅ (cohort scripts need it) |
| Benchmark scripts | ❌ | ✅ (21 scripts) |
| WineBot-specific CLIs | ❌ | ✅ (cv-analyze, cv-watcher, etc.) |

---

## 3. Extraction Justification Analysis

### 3.1 Does Each Proposed Repo Have an Independent Reason to Exist?

| Criterion | desktop-ui-cv | kv-ground-server | ui-captioning |
|:----------|:-------------|:-----------------|:--------------|
| Independent deployment | ⚠️ Could, but always deployed alongside WineBot | ❌ Single endpoint, no standalone use case | ❌ Single endpoint, no standalone use case |
| Independent release cadence | ⚠️ Could version independently, but never has | ❌ Versioned with WineBot | ❌ Versioned with WineBot |
| Distinct ownership | ❌ Same team | ❌ Same team | ❌ Same team |
| Distinct consumers | ⚠️ Could be used by WinBot/others | ❌ Only WineBot | ❌ Only WineBot |
| Distinct security boundary | ❌ Same container network | ❌ Same container network | ❌ Same container network |
| Distinct runtime/toolchain | ❌ All Python 3.12+ | ❌ All Python 3.12+ CUDA | ❌ All Python 3.12+ CUDA |
| Reuse outside WineBot | ✅ Possible (general CV) | ❌ Too narrow (specific model) | ❌ Too narrow (specific model) |
| Separable lifecycle | ⚠️ Possible but coupled in practice | ❌ Must coordinate with WineBot | ❌ Must coordinate with WineBot |
| Separate API/contract surface | ✅ Yes (HTTP API) | ✅ Yes (HTTP API) | ✅ Yes (HTTP API) |

**Verdict:** Only `desktop-ui-cv` has a plausible independent reason to exist.
`kv-ground-server` and `ui-captioning` fail on most criteria.

### 3.2 Three-Repo Smell Test

> *"The biggest repo-design smell to watch for is three repos that must always change together."*

If WineBot adds a feature that requires a new detection model, a new grounding
query, or a new captioning prompt — does it touch all three repos?

- Adding a new detector → change desktop-ui-cv only ✅
- Adding a new grounding strategy → change kv-ground-server only ✅
- Adding a new captioning mode → change ui-captioning only ✅

However:
- Updating the sidecar server API → changes desktop-ui-cv, and WineBot's
  callers in api/routers/automation.py ❌ (two repos)
- Changing the analyze → ground → caption pipeline → potentially touches all
  three + WineBot ❌❌❌
- Changing the Docker base image or CUDA version → all three Dockerfiles
  independently updated ❌❌❌
- Adding a feature that needs both grounding and captioning results → two
  repos + WineBot ❌❌

The **coordinated change risk is real** for infrastructure (Docker, CUDA,
Python version) and cross-cutting features. The risk is low for individual
model changes.

---

## 4. Recommended Target Architecture

### 4.1 Recommendation: Two Repos with Optional Extras

```
SemperSupra/WineBot                          (monorepo, slimmer)
├── api/, docker/, scripts/                  (orchestration)
├── scripts/diagnostics/cv-sidecar-server.py (entrypoint, stays here)
└── docker/Dockerfile.cv-analyzer-gpu        (installs desktop-ui-cv from git)

SemperSupra/desktop-ui-cv                    (the CV package — single repo)
├── src/winebot_cv/                          (Python package core)
│   ├── detectors/
│   ├── ocr/
│   ├── registry/
│   ├── embedding/
│   ├── dataset/
│   ├── classification/
│   └── tracking/
├── server/                                  (sidecar server entrypoint)
├── extras/                                  (NOT separate repos — subdirectories)
│   ├── grounding/                           (kv-ground-server server.py)
│   └── captioning/                          (ui-captioning server.py + florence2)
├── docker/
│   ├── Dockerfile                           (GPU image with everything)
│   └── Dockerfile.4bit                      (KV-Ground 4-bit variant)
├── pyproject.toml                           (all deps, extras groups)
├── tests/
└── .github/workflows/ci.yml
```

### 4.2 Rationale

**kv-ground-server → extras/grounding/ inside desktop-ui-cv:**
- Single file (server.py, 3.5KB) — not worthy of its own repo
- Only consumer is WineBot
- Depends on the same CUDA/PyTorch runtime as desktop-ui-cv
- Can be a pip extra: `desktop-ui-cv[grounding]`
- Same Docker image can serve both

**ui-captioning → extras/captioning/ inside desktop-ui-cv:**
- Two files (server.py + florence2_captioner.py, ~13KB total)
- Same analysis as grounding above
- Can be a pip extra: `desktop-ui-cv[captioning]`
- Shares Florence-2 model dependency with desktop-ui-cv's omni parser

### 4.3 Alternative Considered: Consolidate All Three

A three-into-one merge where kv-ground-server and ui-captioning become modules
of desktop-ui-cv. This would create a single `winebot_cv.serving.grounding` and
`winebot_cv.serving.captioning`. While cleanest for code sharing, it requires
refactoring imports and may not be worth the churn given the small code sizes.

### 4.4 Alternative Considered: Status Quo (Three Repos)

If you want to keep three repos (e.g., because kv-ground-server and ui-captioning
may gain independent consumers later), then at minimum they need:

- pyproject.toml with proper metadata
- CI workflows
- Tests
- Dockerfiles that build standalone
- An integration test that validates cross-repo compatibility

This is doable but adds CI/maintenance overhead for ~17KB of code.

---

## 5. Component and Subsystem Boundary Findings

### 5.1 God Script: cv-sidecar-server.py

**Finding:** `scripts/diagnostics/cv-sidecar-server.py` (1321 lines, 50KB) is a
god script that mixes 7+ concerns:

| Lines | Concern | Should Be |
|:------|:--------|:----------|
| 1-72 | Imports + setup | Core module |
| 74-112 | State classifier loading | winebot_cv.classification |
| 114-140 | State classification logic | winebot_cv.classification |
| 142-189 | Element matching (IoU, persistence) | winebot_cv.tracking |
| 191-230 | Temporal filtering | winebot_cv.tracking |
| 234-306 | Main analyze_image() function | winebot_cv core |
| 310-333 | Click target finding | Should be in automation, not CV |
| 335-355 | Batch job runner | server module |
| 358-720 | FastAPI app + ALL endpoints | server module |
| 720-800 | Wait-for-window (polls WineBot API) | Should be in WineBot, not sidecar |
| 796-900 | Ground endpoint (calls kv-ground) | server module |
| 891-970 | Describe endpoint (calls captioning) | server module |
| 1001-1060 | CLIP search endpoint | server module |
| 1161-1200 | Benchmark endpoint | server module |
| 1208-1295 | CLI mode + main | server module |

**Severity:** High
**Impact:** Hard to test, hard to modify, any change risks breaking unrelated
features. New developers must read 1300 lines to understand any single feature.
**Recommendation:** Split into modules: `server/routes/health.py`,
`server/routes/analyze.py`, `server/routes/ground.py`,
`server/routes/describe.py`, `server/routes/search.py`, `server/routes/benchmark.py`,
`server/cli.py`, and `server/__init__.py`.

### 5.2 Dockerfile Scope Creep

**Finding:** `docker/Dockerfile` in the desktop-ui-cv repo is the full GPU
sidecar Dockerfile from the monorepo (165 lines, 9KB). It installs **every
possible dependency**: PyTorch, ultralytics, transformers, Florence-2 via
transformers, PaddleOCR via ONNX, CLIP via open-clip-torch, FAISS, RF-DETR,
bitsandbytes, peft, accelerate.

**Severity:** Medium
**Impact:** Image is ~3.7GB+ and builds everything regardless of what the user
actually needs. If someone only wants contour detection + Tesseract, they still
get a full DL stack.
**Recommendation:** Multi-stage Dockerfile with target stages:
- `base` — OpenCV + Tesseract + FastAPI
- `gpu` — adds PyTorch + CUDA
- `full` — adds everything else
- `slim` — base + specific extras

### 5.3 Legacy Scripts Still in WineBot

**Finding:** 10 scripts in `scripts/diagnostics/` still import from the legacy
files `ocr_engines.py` and `ui_detectors.py`, rather than from `winebot_cv`.
These legacy files were kept in WineBot for backward compatibility.

**Affected scripts:**
- `benchmark_definitive.py`, `benchmark_runner.py`
- `cv-analyze-demos.py`, `pipeline_replacements.py`
- `ocr_accuracy_bench.py`, `workflow_evaluator.py`, `workflow_test_harness.py`
- Plus the legacy files themselves: `ocr_engines.py`, `ui_detectors.py`

**Severity:** Medium
**Impact:** Two copies of detection/OCR logic exist (one in WineBot legacy,
one in desktop-ui-cv package). They'll drift over time. New developers won't
know which to use.
**Recommendation:** Migrate these cohort scripts to use `winebot_cv` imports.
Once done, delete `ocr_engines.py` and `ui_detectors.py` from WineBot.

### 5.4 Empty or Stub Modules

**Finding:** Several `winebot_cv` subpackages are empty stubs (28-byte `__init__.py`):
- `winebot_cv.classification` — stub only, no actual code
- `winebot_cv.dataset` — has `generator.py` (108KB!) but empty `__init__.py` exports nothing
- `winebot_cv.tracking` — stub only

**Severity:** Low
**Impact:** Misleading package structure. Classification and tracking are
defined inline in cv-sidecar-server.py rather than in these modules.
**Recommendation:** Either populate these modules with the server's inline logic,
or remove them and document that classification/tracking live in the server module.

### 5.5 Interface and Handoff Gaps

| Interface | Owner | Consumer | Documented? | Tested? | Versioned? |
|:----------|:------|:---------|:-----------|:--------|:-----------|
| Sidecar /health | cv-sidecar | WineBot API, Docker | ✅ | ✅ | ❌ |
| Sidecar /analyze | cv-sidecar | WineBot API | ⚠️ Partial | ⚠️ (1 test) | ❌ |
| Sidecar /ground | cv-sidecar → kv-ground | WineBot API | ❌ | ❌ | ❌ |
| Sidecar /describe | cv-sidecar → captioning | WineBot API | ❌ | ❌ | ❌ |
| kv-ground /ground | kv-ground-server | cv-sidecar | ❌ | ❌ | ❌ |
| captioning /caption | ui-captioning | cv-sidecar | ❌ | ❌ | ❌ |
| Environment variables | All | All | ⚠️ Partial | ❌ | N/A |

**Key finding:** The handoffs between cv-sidecar, kv-ground-server, and
ui-captioning are **not tested at all**. If the ground endpoint changes its
response format, there's no contract test to catch the breakage.

---

## 6. Architecture Metrics Scorecard

| Metric | Score | Evidence |
|:-------|:------|:---------|
| Cohesion | ⚠️ **Weak** | cv-sidecar-server.py (7 concerns), Dockerfile (everything-in-one) |
| Coupling | ✅ **Low** | HTTP between services, clean Python package boundary |
| Separation of concerns | ⚠️ **Weak** | Server script mixes CLI, API, domain logic, infra |
| Boundary clarity | ⚠️ **Weak** | Unclear what belongs in which repo, legacy files unclear status |
| Interface quality | ❌ **Poor** | No contract tests, no OpenAPI specs, no schema versioning |
| Dependency direction | ✅ **Good** | winebot_cv ← cv-sidecar ← kv-ground/captioning (one way) |
| Change locality | ⚠️ **Weak** | Docker/CUDA updates touch 3 Dockerfiles; god script changes risky |
| Change coupling | ❌ **Poor** | 10+ WineBot scripts still coupled to legacy files |
| Duplication | ⚠️ **Medium** | ocr_engines/ui_detectors exist in two places (legacy + package) |
| Modularity | ✅ **Good** | Package splits into detectors/ocr/registry cleanly |
| Repository fit | ❌ **Poor** | Three repos for ~17KB of server code in two of them |
| Data ownership | ✅ **Good** | winebot_cv owns models; sidecar owns server state |
| Testability | ❌ **Poor** | No tests for ground/describe/benchmark/search endpoints |
| Observability | ✅ **Good** | Health checks, env-var config, structured prints |
| Security boundaries | ✅ **Good** | All internal network, no external exposure |
| Operational simplicity | ⚠️ **Medium** | Three Dockerfiles to maintain, coordinated updates |
| Documentation | ⚠️ **Medium** | Architecture docs exist but are stale; no interface docs |
| Human/agent usability | ❌ **Poor** | God script, unclear repo boundaries, no "where does this go" guide |

---

## 7. Extraction Risk Register

| Risk | Cause | Impact | Likelihood | Severity | Mitigation |
|:-----|:------|:-------|:-----------|:---------|:-----------|
| Repos drift apart | Different maintainers, no cross-repo tests | Inconsistent API behavior | Medium | High | Contract tests before cutting boundaries |
| Git history lost | Copy-paste extraction | Can't trace bug origins | Certain | Medium | Current state (already happened) |
| CI burden | 3 repos × N jobs | Slow iteration, missed failures | High | Medium | Consolidate small repos |
| Duplicate Dockerfiles | CUDA/Python updates touch all 3 | Stale base images, security gaps | High | Medium | Single Dockerfile with stages |
| Legacy file drift | ocr_engines/ui_detectors still in WineBot | Two sources of truth | Medium | High | Migrate cohort scripts, delete legacy |
| God script resistance | cv-sidecar-server too big to refactor | Nobody splits it | High | Medium | Incremental module split |
| kv-ground/captioning never grow | No independent use case emerges | Dead repos | High | Low | Acceptable if consolidated |

---

## 8. Migration and Extraction Plan (Recommended)

### Phase 0: Fix the Current Repos First (PRs to each)

Before any structural changes, make each repo minimally viable:

1. **desktop-ui-cv:** Fix Dockerfile paths (remove `COPY packages/` monorepo refs),
   fix CI workflow paths, add ruff config, verify tests pass standalone.
2. **kv-ground-server:** Add pyproject.toml, CI, basic health test.
3. **ui-captioning:** Add pyproject.toml, CI, basic health test.

This is the "make it work standalone" phase — about 1-2 PRs per repo.

### Phase 1: Consolidate (Recommended)

Move kv-ground-server and ui-captioning into desktop-ui-cv as extras:

```
desktop-ui-cv/extras/grounding/server.py
desktop-ui-cv/extras/captioning/server.py
desktop-ui-cv/extras/captioning/florence2_captioner.py
```

Update pyproject.toml with extras:
```
[project.optional-dependencies]
grounding = ["transformers>=4.45", "accelerate", "bitsandbytes", ...]
captioning = ["transformers>=4.45", "opencv-python-headless", ...]
full = ["desktop-ui-cv[grounding,captioning]"]
```

**Do NOT delete the old repos yet.** Keep them as remotes, add a README
pointing to desktop-ui-cv.

**Do NOT merge kv-ground-server and ui-captioning into the cv-sidecar.py
god script.** Keep them as separate server entrypoints that can be launched
independently.

### Phase 2: Refactor the God Script

Split cv-sidecar-server.py into modules:
```
server/
├── __init__.py          # create_app(), main()
├── cli.py               # CLI mode entrypoint
├── analyze.py           # /analyze endpoint logic
├── ground.py            # /ground endpoint logic
├── describe.py          # /describe endpoint logic
├── search.py            # /search, /search/build
├── benchmark.py         # /benchmark
├── monitoring.py        # /watch/*, temporal
└── models.py            # state classifier, model registry setup
```

Each module < 200 lines. Each independently testable.

### Phase 3: Add Contract Tests

For the three HTTP handoffs:
- cv-sidecar → kv-ground (grounding)
- cv-sidecar → ui-captioning (description)
- WineBot API → cv-sidecar (analyze)

Contract tests verify request/response format without needing real models
or GPUs. Use pytest + FastAPI TestClient + mock responses.

### Phase 4: Delete Legacy Files

Once cohort scripts (benchmarks, workflows) are migrated to `winebot_cv` imports:
- Delete `scripts/diagnostics/ocr_engines.py`
- Delete `scripts/diagnostics/ui_detectors.py`
- Delete `scripts/diagnostics/clip_embedder.py` (if exists standalone)

---

## 9. Documentation and Governance Recommendations

| Document | Where | Priority |
|:---------|:------|:---------|
| Repo map (current state) | Each repo's README | Immediate |
| Interface catalog | desktop-ui-cv/docs/interfaces.md | Immediate |
| ADR: why two repos vs three | docs/ | This PR |
| "Where does this change belong?" | CONTRIBUTING.md | Phase 2 |
| API contract specs (OpenAPI) | desktop-ui-cv/docs/ | Phase 3 |
| Release process | Each repo's RELEASE.md | Phase 1 |

---

## 10. Open Questions

1. **Is there a concrete plan to make kv-ground-server or ui-captioning
   independently useful?** If yes, the separate repos make sense. If they're
   always WineBot accessories, consolidate now.
2. **Who would own each repo if they're separate?** Same team = weak boundary.
3. **Is the 1321-line cv-sidecar-server.py worth splitting now?** The risk of
   breaking it is low (few callers), so incremental splitting is safe.
4. **Should the legacy scripts (ocr_engines, ui_detectors) be migrated before
   or after the god script refactor?** Before — simpler, less risk.
5. **Is there a timeline for making desktop-ui-cv public?** If yes, the
   package structure and docs should be cleaned up first.

---

## 11. Recommended First PR

**Do not merge the three repos.** Instead:

**PR #1 (to desktop-ui-cv main):** "Standalone Dockerfile and CI fix"
- Fix Dockerfile to use local `src/` and `server/` instead of monorepo paths
- Fix CI workflow paths
- Add `[tool.ruff.lint]` section to pyproject.toml
- Add basic README with install and run instructions

**PR #2 (to kv-ground-server main):** "Minimal standalone hardening"
- Add pyproject.toml with dependencies
- Add basic health test
- Add CI workflow

**PR #3 (to ui-captioning main):** "Minimal standalone hardening"
- Same as PR #2

**PR #4 (decision PR to WineBot):** "Architecture decision: consolidate
kv-ground-server and ui-captioning into desktop-ui-cv"
- Proposes the consolidation with evidence from this review
- If accepted, implement as Phase 1 above
- If rejected, the Phase 0 fixes from PRs #1-#3 are sufficient

These PRs are small, safe, and improve the current state regardless of
whether the consolidation is accepted.


---

## Implementation Status (Updated 2026-07-06)

| Phase | Status | Repo | PR |
|:------|:-------|:-----|:---|
| Phase 0a: pyproject.toml, tests, CI | ✅ Merged | kv-ground-server | #2 |
| Phase 0b: pyproject.toml, tests, CI | ✅ Merged | ui-captioning | #2 |
| Phase 0c: Standalone Dockerfile + CI | ✅ Merged | desktop-ui-cv | #2 |
| Phase 1: Consolidation | ✅ Merged | desktop-ui-cv | #4 |
| Redirect READMEs | ✅ Merged | kv-ground-server #3, ui-captioning #3 | Both |
