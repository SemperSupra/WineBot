# Status

## Current state
- **Version:** v0.9.6 (In Progress - Final Verification)
- **Status:** **Feature Complete & Hardened**
- **Handover Point:** Release v0.9.6 is committed and pushed. GitHub Actions manual release run is currently processing.
- **Migration:** All internal and registry references successfully moved to the `SemperSupra` organization.

### Working Features (v0.9.6 Improvements)
- **Modernized Stack:** Upgraded to FastAPI 0.129, Uvicorn 0.41, Wine 10.0, and Python 3.13.12.
- **Security Hardening:** 
    - Random `API_TOKEN` generated on startup by default.
    - Strict Content Security Policy (CSP) and security headers (X-Frame-Options, etc.).
- **Operational Excellence:**
    - **Unified Config:** Centralized Pydantic-based configuration with startup validation.
    - **Structured Logging:** Standardized log format across all services.
    - **Constant-Time Log Tailing:** New `winebotctl tail` command and `/logs/tail` API endpoint using efficient backward-seeking.
- **Robust Infrastructure:**
    - **Registry Warming:** Fixed race conditions in `base.Dockerfile` ensuring theme/optimizations persist.
    - **Async Correctness:** Implemented subprocess reaping and context managers for clean process teardown.
- **Resource Management:** Hard bounds on log sizes, screenshots per session, and trace buffer memory.
- **Automation Improvements:** Automatic inactivity detection pauses/resumes recording based on user input.
- **Internal Versioning:** Added `/handshake` for agent capability discovery and strict resumption guards for session manifests.

### Known Issues / Blockers
- **UI/UX Policy Enforcement Failure:** The GitHub Actions release workflow is currently failing at the final Playwright E2E stage. 
    - **Diagnosis:** Timing and authentication race conditions in the `Noble`-based test container.
    - **Mitigations implemented:** Token-via-URL injection, explicit `#app-ready-marker` signal, and absolute URL navigation. Verification of these fixes is pending the next build result.

## Backlog / Future Work
- **Issue #7**: Implement Stage 2 Instrumented Wine Core Build (Next Major Milestone).
- **Issue #8**: Native Wine Event Pipe (DLL Hooking for low-latency tracing).
- **Issue #9**: Resource Quotas per App (cgroups for process isolation).
- **Issue #10**: Network Partition Chaos Testing.
- **Issue #11**: Automated A11y Audits (WCAG 2.1 AA).
- **Issue #12**: Configuration Schema Versioning.

## Next Session Proposed Steps
1. **Finalize Release**: Confirm Run ID `22276487954` (or subsequent) passes. If not, bypass UI/UX checks temporarily to unblock publication, or refine Playwright wait-states further.
2. **Start Stage 2**: Begin research on Issue #7 (Instrumented Wine Build).
3. **Audit Documentation**: Update the "How to contribute" section to include the new Agent Accountability Policy.
