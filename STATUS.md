# Status

## Current state
- **Version:** v0.9.3 (Stable)
- **Linting:** Massive reduction in lint debt across `api/` and core scripts.
- **Image Optimization:** Refactored Dockerfile with multi-stage builds, reducing `rel` image size by ~35% (to ~4.3GB).
- **API Hardening:** Fixed concurrency races and path validation in session lifecycle (`suspend`/`resume`) endpoints. Added rigorous regression tests.
- **Stability Monitoring:** Integrated `scripts/diagnose-trace-soak.sh` into a new GitHub Actions nightly workflow (`nightly-soak.yml`).
- **Wine 10.0 Hardening:** Verified full-desktop input handling and 1920x1080 virtual desktop enforcement.

## Validation so far
- **Image Build:** `verify-rel` and `verify-rel-runner` targets build successfully with reduced footprint.
- **API Tests:** New `tests/test_lifecycle_hardened.py` passes, covering concurrent state transitions and path traversal prevention.
- **Soak Testing:** Diagnostic scripts validated locally; CI workflow ready for nightly execution.

## Known quirks
- `docker-compose` v1 may error with `ContainerConfig` on recreate; use `down --remove-orphans` before `up`.
- `stable` tag on GHCR needs manual alignment to `0.9.2` digest (pending auth refresh).

## Next steps (pick up here)
1. Monitor the first run of the nightly soak workflow.
2. Perform the one-time GHCR retag for `stable`.
3. Further prune `base-runtime` layers if needed.