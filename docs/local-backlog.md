# Local Backlog

This file tracks in-flight and planned work items that are not yet fully delivered in a single PR.

## Recording Program

- `DONE` Phase 1: Timeline id + artifact manifest contract.
  - Commit: `957fba4`
  - Scope: `recording_timeline_id` in API responses/session artifacts, `recording_artifacts_manifest.json`, tests and docs.

- `OPEN` Phase 2: Markerized timeline and markers API.
  - GitHub issue: https://github.com/SemperSupra/WineBot/issues/41

- `OPEN` Phase 3: Segmented rotation and retention policy.
  - GitHub issue: https://github.com/SemperSupra/WineBot/issues/39

- `OPEN` Phase 4: Privacy controls for recording and traces.
  - GitHub issue: https://github.com/SemperSupra/WineBot/issues/38

- `OPEN` Phase 5: Timeline-correlated playback and diagnostic UX.
  - GitHub issue: https://github.com/SemperSupra/WineBot/issues/40

## Conformance Program

- `DONE` Baseline conformance suite integrated in CI.
  - Scope: OpenAPI validation, HTTP semantics checks, OCI/runtime policy checks, CLI contract checks, mDNS service-type checks.
  - References: `docs/conformance.md`, `tests/test_conformance_openapi.py`, `tests/test_conformance_http_semantics.py`, `tests/test_conformance_runtime_policy.py`, `tests/test_conformance_cli_contract.py`, `tests/test_conformance_mdns.py`.

- `OPEN` Advanced API conformance fuzzing.
  - GitHub issue: https://github.com/SemperSupra/WineBot/issues/43

- `OPEN` SBOM schema and license-policy conformance gates.
  - GitHub issue: https://github.com/SemperSupra/WineBot/issues/44

- `OPEN` Real-network DNS-SD/mDNS integration conformance.
  - GitHub issue: https://github.com/SemperSupra/WineBot/issues/42

## Invariant Hardening Program

- `DONE` Phase A: canonical invariants + executable invariant checks + runtime invariant health endpoint.
  - Scope: `docs/invariants.md`, `tests/test_invariants.py`, `/health/invariants`, fail-closed atomic writes for critical state files.

- `DONE` Phase B: session resume transition markers and rollback-safe marker cleanup.
  - Scope: `api/routers/lifecycle.py` transactional transition markers.

- `OPEN` Advanced durability and CAS transition guards (grouped deferred scope).
  - GitHub issue: https://github.com/SemperSupra/WineBot/issues/45

## Understandability Hardening Program

- `DONE` Phase A: magic-number/string consolidation and safe configuration upgrades.
  - Scope:
    - centralized lifecycle/control constants (`api/core/constants.py`)
    - non-hidden runtime atomic temp file handling (`api/utils/files.py`)
    - configurable runtime timing guards (`api/utils/config.py`, `api/server.py`, `api/routers/lifecycle.py`)
    - strict fail-closed config parsing with explicit errors (`api/utils/config.py`)
    - strict validation tests (`tests/test_config_strict_validation.py`)

- `OPEN` Phase B (deferred): machine-readable config metadata and `winebotctl config describe`.
  - Tracking: local backlog (docs/CLI UX enhancement)

- `OPEN` Phase B (deferred): static guardrail for magic literals in critical modules.
  - Tracking: local backlog (lint/test enhancement)

- `OPEN` Phase C (deferred): XDG runtime/state path migration with compatibility fallback.
  - GitHub issue: https://github.com/SemperSupra/WineBot/issues/46
