# Testing Infrastructure Audit

**Date:** 2026-06-28 | **Audit:** Comprehensive review of all test, diagnostic, and tracing infrastructure

## 1. Test Inventory

| Category | Count | Files |
|:---|---:|:---|
| Unit test files | 33 | `tests/test_*.py` |
| E2E test files | 14 | `tests/e2e/test_*.py` |
| Diagnose scripts | 5 | `tests/diagnose_*.py` |
| Conformance tests | 5 | `tests/test_conformance_*.py` |
| Total test functions | **209** | Across all files |

### What Tests Cover

| Area | Tests | Coverage |
|:---|---:|:---|
| API contracts (HTTP semantics, OpenAPI) | 2 files | ✅ Good |
| CLI contracts (`winebotctl`) | 1 file | ✅ Good |
| Runtime policy enforcement | 1 file | ✅ Good |
| Input keyboard (unit + E2E) | 4 files | ✅ Strong |
| Input occlusion conformance | 1 file | ✅ Strong |
| Recording (unit + recovery + heartbeat) | 4 files | ✅ Strong |
| Dashboard UX compliance | 3 files | ✅ Good |
| Lifecycle hardening | 1 file | ✅ Good |
| Telemetry contract | 2 files | ✅ Good |
| Configuration validation | 2 files | ✅ Good |
| Build intent policy | 1 file | ✅ Good |
| mDNS discovery | 1 file | ✅ Good |
| Process timeout | 1 file | ✅ Good |
| UI accessibility | 1 file | ✅ Good |
| Invariants | 1 file | ✅ Good |
| Monitoring/inactivity | 1 file | ✅ Good |

### What Tests DO NOT Cover

| Area | Endpoints / Features | Risk |
|:---|---|:---:|
| **Session lifecycle** | `/sessions/suspend`, `/sessions/resume`, `/lifecycle/status` | 🔴 High |
| **Recording control** | `/recording/pause`, `/recording/resume` | 🟡 Medium |
| **Input backends** | AHK vs Hook vs Auto — only AHK tested | 🟡 Medium |
| **CV sidecar** | `/analyze`, `/batch`, `/describe`, `/ground`, `/search` | 🔴 High |
| **OCR backends** | Tesseract vs PaddleOCR vs PaddleOCR ONNX variants | 🔴 High |
| **UI detectors** | Contour vs YOLO vs OmniParser vs ScreenParser vs Wine | 🟡 Medium |
| **Session control** | `/control/grant`, `/control/challenge`, `/control/renew` | 🟡 Medium |
| **Openbox control** | `/openbox/reconfigure`, `/openbox/restart` | 🟢 Low |
| **Wine app lifecycle** | `/apps/run` with various args, error cases | 🟡 Medium |
| **Annotation WebUI** | UX test for manual labeling workflow | 🟢 Low |
| **Demo pipeline** | Full end-to-end demo automation | 🟡 Medium |
| **WinBot parity** | Parity tests never run against WineBot | 🟡 Medium |
| **Sidecar integration** | Core→Sidecar bridge communication | 🟡 Medium |

## 2. Linting & Static Analysis

| Tool | Status | Rules | Notes |
|:---|---:|---:|:---|
| **Ruff** | ✅ Configured | 0 explicit rules (defaults) | `pyproject.toml` sets line-length=100, target=py312 |
| **Mypy** | ⚠️ Configured | 0 explicit rules | Present in `pyproject.toml` but no strict mode |
| **Pre-flight CI** | ✅ Runs | Trivy, capability matrix, lint, unit tests | Containerized execution |
| **ShellCheck** | ❌ Not configured | — | Shell scripts not linted |
| **Pre-commit hooks** | ❌ Not configured | — | No .pre-commit-config.yaml |

**Issue:** Ruff and Mypy are listed as dependencies but have **no explicit rule configuration**. This means they use default rulesets, which is extremely permissive. Ruff defaults only catch syntax errors, not style issues. Mypy defaults only catch obvious type errors.

## 3. Local vs CI/CD Parity

| Tool | Local (`./scripts/wb`) | CI (`.github/workflows/ci.yml`) | Parity? |
|:---|---:|---:|:---:|
| Linting | `wb lint` → dockerized Ruff + Mypy | Dockerized lint runner | ✅ Same container |
| Unit tests | `wb test` → dockerized pytest | Dockerized test runner | ✅ Same container |
| E2E tests | Via docker compose | CI runs subset (dashboard + input) | ⚠️ CI runs fewer |
| Smoke gate | `wb smoke-test` | `reusable-build-smoke-gate.yml` | ✅ Same gate |
| Build | `wb build` | Docker Compose build | ✅ Same |
| Vulnerability scan | Trivy in CI only | CI only | ❌ Not local |

**Issue:** Trivy vulnerability scanning runs only in CI, not locally. Developers won't catch container vulnerabilities until CI fails.

## 4. Diagnostic Suites

| Diagnostic | What It Tests | Coverage |
|:---|---:|:---|
| `diagnose-master.sh` | Orchestrates all sub-diagnostics in phases | ✅ Comprehensive |
| `diagnose-input-suite.sh` | All input backends and injection paths | ✅ Strong |
| `diagnose-mouse-input.sh` | Mouse click accuracy at multiple coordinates | ✅ Good |
| `diagnose-wine-registry.sh` | Registry key verification for Wine config | ✅ Good |
| `diagnose-trace-soak.sh` | Long-duration trace stability (soak test) | ✅ Good |
| `diagnose-fault-injection.sh` | Process crash recovery, timeout handling | ✅ Strong |
| `soak-resource-bounds.sh` | Memory, CPU, disk bounds under load | ✅ Good |
| `health-check.sh` | DEPRECATED — points to API endpoints | ⚠️ Deprecated |

**Strength:** The diagnostics are comprehensive and cover failure modes not tested elsewhere (fault injection, resource bounds, soak testing).

## 5. Tracing Infrastructure

| Trace Layer | Events Captured | Status |
|:---|---:|:---|
| **X11 core** | Mouse button press/release, motion, key press/release | ✅ Active |
| **Client (noVNC)** | Canvas mouse, keyboard events from browser | ✅ Active |
| **Windows (AHK)** | Window-level input events via AutoHotkey hook | ✅ Active |
| **Network (VNC proxy)** | VNC protocol-level input trace | ✅ Active |
| **Recording events** | Session video + input event correlation | ✅ Active |

All trace layers write structured JSONL to `{session_dir}/logs/`. Correlation between layers uses session ID + timestamp alignment.

## 6. UX Testing

| UI Component | Test Coverage | Status |
|:---|---:|:---:|
| noVNC Dashboard | `test_dashboard_e2e.py` — loads, renders | ✅ Basic |
| noVNC Dashboard UX | `test_ux_quality.py` — toasts, health, responsive | ✅ Good |
| noVNC Dashboard UX compliance | `test_zz_dashboard_ux_compliance.py` — palette, badges, state machine | ✅ Good |
| noVNC keyboard accessibility | `test_ux_keyboard_accessibility.py` — tab order, focus | ✅ Good |
| noVNC input pipeline UX | `test_input_occlusion_conformance.py` — hit testing | ✅ Good |
| **Annotation WebUI** | **No UX tests** | ❌ Not tested |
| **Openbox window manager** | **No UX tests** | ❌ Not tested |
| **tint2 taskbar** | **No UX tests** | ❌ Not tested |

## 7. Key Findings Summary

### Strengths
1. **209 test functions** across 52 files is substantial
2. **Diagnostic suites** cover failure modes (fault injection, soak, resource bounds) that most projects skip
3. **Tracing** captures 4 independent layers with correlation
4. **Local and CI share the same container** for lint/test, ensuring parity
5. **Dashboard UX** has dedicated compliance and accessibility tests
6. **Conformance tests** (HTTP semantics, OpenAPI, CLI contracts) validate API surface rigorously

### Critical Gaps

1. **CV sidecar has zero test coverage** — `/analyze`, `/batch`, `/describe`, `/ground`, `/search` all untested at the unit/E2E level
2. **OCR backends untested** — No test validates Tesseract vs PaddleOCR output differences
3. **UI detector variants untested** — Contour, YOLO, OmniParser, ScreenParser, Wine all untested in isolation
4. **Session lifecycle endpoints untested** — `/sessions/suspend`, `/sessions/resume`, `/lifecycle/shutdown`
5. **Ruff/Mypy run with default rules** — No custom rule configuration, so most issues pass silently
6. **No ShellCheck** for shell scripts (60+ shell scripts)
7. **No pre-commit hooks** — No local gate before commit
8. **Trivy only in CI** — Container vulnerabilities not caught locally
9. **WinBot parity tests never run** — 71 tests designed for cross-platform parity never executed
10. **Annotation WebUI has no UX tests**

### Recommendations

| Priority | Action | Effort |
|:---|---:|:---:|
| 🔴 High | Add CV sidecar unit tests (`/analyze`, `/health`, OCR backends) | 1 day |
| 🔴 High | Configure Ruff with explicit ruleset (not defaults) | 1 hour |
| 🔴 High | Configure Mypy with `--strict` for API code paths | 1 hour |
| 🟡 Medium | Add ShellCheck to lint pipeline for `scripts/*.sh` | 1 hour |
| 🟡 Medium | Add Trivy to local `wb` tooling | 1 hour |
| 🟡 Medium | Test session lifecycle endpoints (`/sessions/suspend`, `/resume`) | 2 hours |
| 🟡 Medium | Run WinBot parity tests against WineBot API | 2 hours |
| 🟡 Medium | Add pre-commit hook config (Ruff + ShellCheck) | 1 hour |
| 🟢 Low | Add annotation WebUI smoke test (loads, renders image list) | 1 hour |
| 🟢 Low | Add `/apps/run` error case coverage (invalid path, missing exe) | 1 hour |
