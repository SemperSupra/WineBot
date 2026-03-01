# Conformance Testing and Standards

This project runs explicit conformance checks for the standards and contracts used by WineBot.

## Standards and specs in scope

- OpenAPI 3.1 and JSON Schema for API contract documents.
- HTTP semantics (RFC 9110) for method behavior, status codes, and content headers.
- mDNS/DNS-SD naming rules (RFC 6762/6763) for discovery service type formatting.
- OCI image metadata and annotation conventions for container artifacts.
- Sigstore/cosign signing and verification checks in release workflows.
- SBOM/provenance generation requirements in release workflows.
- WCAG 2.1 AA and ARIA baseline checks for dashboard accessibility.
- Internal Input Pipeline Conformance Policy for mouse/keyboard delivery and control arbitration:
  - `policy/input-pipeline-conformance-policy.md`

## Public conformance tooling used

- `openapi-spec-validator` to validate the generated OpenAPI document.
- `pytest` for executable conformance assertions against API, CLI, and workflow policy.
- `playwright` + UX/a11y suites for user-facing behavior and accessibility regressions.

## Conformance suites

- `tests/test_conformance_openapi.py`
- `tests/test_conformance_http_semantics.py`
- `tests/test_conformance_runtime_policy.py`
- `tests/test_conformance_cli_contract.py`
- `tests/test_conformance_mdns.py`

Input pipeline conformance is validated across:

- `tests/e2e/test_comprehensive_input.py`
- `tests/e2e/test_input_quality.py`
- `tests/test_policy.py`
- `tests/test_input_lifecycle_regression.py`
- `tests/test_ui_accessibility.py`
- `tests/e2e/test_ux_keyboard_accessibility.py`
- `tests/e2e/test_zz_dashboard_ux_compliance.py`

These suites are included in `scripts/ci/test.sh` and run in CI.

## Best-practice implementation notes

- Keep OpenAPI strict and machine-validated on every change.
- Keep response/version/security headers stable to avoid agent breakage.
- Treat Docker health checks and `/health` API contract as a single invariant.
- Require signed, provenance-enabled release artifacts.
- Keep accessibility and keyboard support in e2e gating for interactive mode.
- Treat input delivery, human-priority arbitration, and UI non-occlusion as release gates.
