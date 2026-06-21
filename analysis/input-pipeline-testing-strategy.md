# Input Pipeline Testing & Diagnostics Strategy

**Date:** 2026-06-21
**Context:** Post-`/input/key` endpoint implementation assessment.

## 1. Current State Summary

### What's in place

| Layer | Testing | Diagnostics | Tracing |
|:---|:---|:---|:---|
| **API endpoints** | `test_input_validation.py` (click bounds), `test_api_contracts.py` (contracts) | `diagnose-input-suite.sh` (CV-based, 3 apps) | `/input/events` (query JSONL logs) |
| **X11 (xdotool)** | `test_input_lifecycle_regression.py` (trace lifecycle), e2e comprehensive input | `diagnose-input-trace.sh` 5-layer bisect | XI2 trace, x11 core trace, Wine debug (`+event,+win`) |
| **Windows (AHK/autoit)** | e2e input trace verification | `diagnose-ahk.ahk`, `diagnose-wine-hook.py`, `diagnose-wine-input.py` | Windows trace layer (AHK hooks), Wine hook observer |
| **Client (noVNC)** | `test_input_quality.py` (Playwright noVNC canvas clicks) | `playwright-client-trace.py` | Client trace layer |
| **Network (VNC)** | e2e VNC RFB probe (mouse, drag, scroll, modifier chords) | VNC RFB raw probe in diagnose-input-trace.sh | Network trace layer (VNC proxy) |
| **Conformance** | OpenAPI, HTTP, CLI, mDNS, runtime policy suites | - | - |
| **UI/UX** | Dashboard e2e, keyboard accessibility, occlusion conformance | - | - |
| **Latency** | - | `analyze-trace-latency.py` (VNC→X11→Win) | Cross-layer timestamp correlation |

### What's missing / weak

1. **New `/input/key` endpoint has zero CI coverage** — not in `scripts/ci/test.sh`, no dedicated conformance test
2. **Keyboard trace pipeline is incomplete** — the endpoint emits trace events but `analyze-trace-latency.py` only tracks VNC→X11→Windows for mouse input, not API→AHK→Wine for keyboard
3. **Diagnostic suite uses xdotool keyboard** — `diagnose-input-suite.sh` tests keyboard via `xdotool type`/`xdotool key` which is BLOCKED by explorer.exe/desktop in headless mode; it doesn't exercise the new `/input/key` API at all
4. **No always-on trace pipeline** — traces must be manually started via API; there's no persistent health signal
5. **Conformance policy R3 (keyboard semantics) lacks a dedicated test** — keydown/keyup pairing, modifier combos, and ordering aren't programmatically verified
6. **No public conformance standard exists** for Wine input pipelines — the project's `policy/input-pipeline-conformance-policy.md` is the only spec
7. **Dashboard trace viewer is read-only text log** — no structured explorer, no latency visualization, no cross-layer correlation UI

---

## 2. Recommended Action Items

### Item A: Add `/input/key` to CI test suite (and API-level keyboard conformance test)

**What:** Create `tests/test_input_keyboard_conformance.py` — a fast unit/integration test that validates the `/input/key` endpoint's contract, error paths, and key translation correctness. Add it to `scripts/ci/test.sh`.

**Specific tests:**
- `POST /input/key` with valid payload → 200, `status: "sent"`
- `POST /input/key` with empty keys → 400 validation error
- `POST /input/key` with invalid backend → 400
- `POST /input/key` without session → 409
- `POST /input/key` with mocked broker denial → 423
- Verify trace events are written (phase="request", phase="complete")
- Verify telemetry emission on success and error paths
- Verify `_xdotool_to_ahk_keys` coverage for all documented key patterns (already partially covered in `test_input_validation.py`)

**Recommendation:** **IMPLEMENT** — this is the most critical gap. It puts the new endpoint under CI guard and validates the API contract, error handling, and trace/telemetry side effects without requiring a running Wine instance.

**Trade-offs:** Mock-based tests won't catch real Wine/AHK failures, but they will catch regressions in endpoint logic, validation, and telemetry. Real Wine testing remains in e2e.

---

### Item B: Update diagnostic suite to use `/input/key` API instead of xdotool for keyboard

**What:** Modify `scripts/diagnostics/diagnose-input-suite.sh` (or create a parallel script) so the keyboard tests exercise the `/input/key` API endpoint rather than `xdotool type`/`xdotool key`. This tests the actual production path agents will use.

**Specific changes:**
- Replace `xdotool type --window "$win_id" "Test"` with `curl POST /input/key {"keys": "Test", "window_title": "Notepad"}`
- Replace `xdotool key --window "$win_id" Alt+f` with `curl POST /input/key {"keys": "alt+f", "window_title": "Notepad"}`
- Add assertion that the response contains `"status": "sent"` and `"backend": "ahk"`
- Verify visual change (existing screenshot diff) after API injection

**Recommendation:** **IMPLEMENT** — ensures the diagnostic suite exercises the same code path agents use. Without this, the suite is testing xdotool keyboard (which is known-broken with the desktop barrier).

---

### Item C: Add keyboard latency analysis to trace tooling

**What:** Extend `scripts/diagnostics/analyze-trace-latency.py` to support the keyboard path: `API /input/key → AHK script execution → Wine Send → trace event`. Add a keyboard-specific latency mode.

**Specific additions:**
- New mode: `--mode keyboard` that matches `agent_key` (API input events) → `key_down/key_up` (Windows trace layer) events
- Measure: API request time → AHK script execution time → Windows key event time
- Works with existing `diagnose-input-trace.sh` framework (which already starts all trace layers)

**Recommendation:** **IMPLEMENT** — latency is the primary health indicator for the input pipeline. Without it, regressions are invisible until users report "it feels slow."

---

### Item D: Create conformance test for input pipeline policy R3 (keyboard semantics)

**What:** Create `tests/e2e/test_input_keyboard_conformance_e2e.py` that programmatically validates the normative requirements in `policy/input-pipeline-conformance-policy.md` section R3.

**Specific tests:**
- Keydown/keyup pairing: inject a key chord, verify both `key_down` and `key_up` appear in Windows trace
- Modifier ordering: `ctrl+shift+a` should produce events with modifiers in correct state
- Modifier combos: `ctrl+c`, `alt+F4`, `ctrl+shift+Escape` all verify in trace
- Focus bypass: keyboard input to dashboard text fields should NOT reach Wine (R3.3)
- Rapid-fire: 5 rapid keystrokes should all arrive in order

**Recommendation:** **IMPLEMENT** (tracked together with Item A or as a follow-on) — this directly addresses the conformance policy's requirements and provides the "proof" that R3 is satisfied.

---

### Item E: Always-on input pipeline health endpoint

**What:** Add `GET /health/input-pipeline` that returns a summary of the input pipeline's current state without requiring manual trace starts.

**What it reports:**
```json
{
  "status": "healthy|degraded|unavailable",
  "layers": {
    "x11": {"running": true, "events_last_60s": 42},
    "windows": {"running": true, "backend": "ahk", "events_last_60s": 38},
    "client": {"enabled": false},
    "network": {"running": false}
  },
  "key_backend": "ahk",
  "key_backend_latency_p50_ms": 320,
  "key_backend_latency_p99_ms": 850,
  "desktop_barrier": "active",
  "last_self_test": {"timestamp": "...", "result": "ok"}
}
```

This requires a lightweight background task that periodically sends a test keystroke and measures round-trip time through the trace layers.

**Recommendation:** **DEFER** — open a GitHub issue. This is valuable but adds persistent overhead. The existing on-demand diagnostic tools are sufficient for now. Track as enhancement issue.

---

### Item F: Structured trace explorer in dashboard

**What:** Upgrade the dashboard's input debug log from a raw text dump to a structured trace explorer with:
- Cross-layer event correlation (match client click → X11 event → Windows event by trace_id)
- Latency visualization per event
- Filtering by layer, event type, origin (agent/human)
- Export capability

**Recommendation:** **DEFER** — open a GitHub issue. This is UX polish. The raw log + `analyze-trace-latency.py` covers the diagnostic need. Track as enhancement.

---

### Item G: Self-test on container startup

**What:** Add a startup self-test in `scripts/init/30-start-services.sh` (after API is ready) that:
1. Launches a test app (e.g., `wine notepad`)
2. Sends a test key via `/input/key` (`{"keys": "x", "window_title": "Notepad"}`)
3. Checks Windows trace layer for the event
4. Logs result to session startup log
5. Kills the test app
6. If failing, sets a degraded status flag

**Recommendation:** **IMPLEMENT** — this is the "smoke alarm" for the input pipeline. It catches configuration issues (missing AHK, desktop barrier changes, trace breakage) at startup rather than at 3am when an agent tries to use it. Low overhead (~5s at startup).

**Trade-off:** Adds ~5-8 seconds to container startup. Mitigatable with a `WINEBOT_INPUT_SELF_TEST=0` escape hatch.

---

### Item H: Trace documentation and agent guide

**What:** Document the full trace event schema (every field, every event type, every layer) so agents and operators can interpret trace output. Currently the trace format is discoverable only by reading source code.

**Add to:**
- `docs/api.md` or new `docs/tracing.md` — trace event schema reference
- `AGENTS.md` — add a "Diagnosing Input Issues" section with trace query examples
- Include the cross-layer correlation pattern (trace_id matching)

**Recommendation:** **IMPLEMENT** — low effort, high value for operators and agents debugging input issues. Without this, trace data is opaque.

---

## 3. Summary Table

| # | Item | Recommendation | Effort | Impact |
|:---|:---|:---|:---|:---|
| A | `/input/key` CI test + API conformance | **Implement** | Medium | Critical — guards against regression |
| B | Diagnostic suite uses `/input/key` API | **Implement** | Small | High — tests real agent path |
| C | Keyboard latency analysis in trace tool | **Implement** | Small | High — primary health indicator |
| D | Conformance test for policy R3 (keyboard) | **Implement** | Medium | High — proves policy compliance |
| E | Always-on health endpoint | **Defer** (issue) | Large | Medium — nice-to-have |
| F | Structured trace explorer UI | **Defer** (issue) | Large | Low — UX polish |
| G | Startup self-test | **Implement** | Small | High — catches config issues early |
| H | Trace documentation & agent guide | **Implement** | Small | Medium — enables self-service debugging |

### Grouping

**Batch 1 (this session, high priority):** Items B, C, G, H — small effort, high impact, all diagnostic/trace improvement.

**Batch 2 (follow-on PR):** Items A + D — medium effort, these are the formal conformance tests. Can be a single PR adding `test_input_keyboard_conformance.py` (API-level) and extending existing e2e.

**Deferred (track as issues):** Items E + F.

---

## 4. Public Conformance Standards Assessment

There are **no publicly available conformance test suites** for Wine-based input pipelines. The project's `policy/input-pipeline-conformance-policy.md` is the only specification in this domain.

Relevant external standards that support this work:

| Standard | Relevance | Used? |
|:---|:---|:---|
| **WCAG 2.1 AA** | Dashboard keyboard accessibility | ✅ E2E tests (`test_ux_keyboard_accessibility.py`) |
| **OpenAPI 3.1** | API contract validation | ✅ `test_conformance_openapi.py` |
| **RFC 9110 (HTTP semantics)** | Status codes, method behavior | ✅ `test_conformance_http_semantics.py` |
| **RFC 6762/6763 (mDNS)** | Service discovery naming | ✅ `test_conformance_mdns.py` |
| **OCI image spec** | Container metadata/annotations | ✅ Runtime policy checks |
| **Sigstore/cosign** | Artifact signing | ✅ Release workflow |
| **X11/RFB protocols** | Input event wire format | ⚠️ Implicit (VNC probe tests behavior) |
| **Wine input architecture** | Event queue, message pump, hooks | ⚠️ Implicit (hook observer, Wine debug) |

No external conformance body certifies "Wine input pipeline correctness." The project's internal policy is the conformance standard. The best practice is to make that policy machine-verifiable (Items A, D above).

### Best practices for implementing standards in this project:

1. **Make policies executable** — every normative requirement (R1-R6 in input-pipeline-conformance-policy.md) should map to at least one automated test assertion
2. **Version the policy** — the conformance policy should have a version field so tests can declare which version they validate against
3. **CI-enforce the policy-test mapping** — the test capability matrix already does this; keep it updated
4. **Self-documenting diagnostics** — diagnostic output should reference which policy requirement it validates (e.g., `"R3.2: modifier combo verified"`)
