# Feature/Capability Commit Map

This document maps major WineBot feature and capability sets to the commits that introduced or hardened them.

Notes:
- This is a curated map, not a full changelog.
- Commit references are from the `main` branch history.
- Use `git show <hash>` for file-level details.

## Runtime Foundation

| Feature/Capability Set | Capabilities | Associated Commits |
| :--- | :--- | :--- |
| Modular architecture and agent map | Modular API/entrypoint split, codebase map for agents | `49ad5b6` (Refactor: Modularized API, split entrypoint script, and added Agent Map) |
| Unified lifecycle entrypoint | Unified startup flow, host user mapping, stricter startup behavior | `4490432` (upgrade dependencies + unified entrypoint), `cccc35d` (strict entrypoint consistency) |
| Startup and healthcheck resilience | Robust compose health checks, stable API readiness, root/UI routing hardening | `1b42640`, `b0575bb`, `6c4102e`, `b6d8610`, `a2e7ec5` |

## Build, Images, and Intents

| Feature/Capability Set | Capabilities | Associated Commits |
| :--- | :--- | :--- |
| Intent-staged build model | `dev`/`test`/`slim`/`rel`/`rel-runner` image intents, pinned base lifecycle | `c1219f9`, `3e07e35`, `48376b1` |
| Build-time prefix warm-up | Faster startup via pre-warmed Wine prefix template | `3a8cf3d` |
| Build performance optimization | Smaller/faster images and build reporting | `55063e4`, `fc0dd78` |

## Session and Lifecycle Management

| Feature/Capability Set | Capabilities | Associated Commits |
| :--- | :--- | :--- |
| Lifecycle API hardening | Suspend/resume/shutdown reliability and richer process reporting | `799fb61`, `4931283` |
| Session persistence model | Session artifacts, resume behavior, schema/version baseline | `b86a112`, `34a70e5` |
| Prefix/state reliability | Prefix restore hardening and registry consistency | `7913dce`, `dda563f` |

## Control, Input, and Automation

| Feature/Capability Set | Capabilities | Associated Commits |
| :--- | :--- | :--- |
| Interactive control policy | Agent control grant/revoke flow, user-priority guardrails | `f3ed04f`, `c8f4df5` |
| Input tracing reliability | Cross-layer trace lifecycle stability and diagnostics | `d53fe02`, `26270e8`, `03cb545` |
| Windows automation tools | AutoHotkey/AutoIt/Python automation paths and deterministic behavior | `12daaa2`, `cfbf12e` |

## Recording and Artifacts

| Feature/Capability Set | Capabilities | Associated Commits |
| :--- | :--- | :--- |
| Recording lifecycle | Start/pause/resume/stop reliability and idempotent behavior | `d83f09d`, `108fa8a` |
| Recording artifact validation | Segment manifests, subtitle/media validation, diagnostics hardening | `108fa8a` |
| Runtime recording performance profiling | Inactivity-aware pause/resume policy and performance metric capture | `a2e7ec5` + subsequent `main` updates in current workspace (`perf_metrics`, inactivity tuning) |

## UI, Dashboard, and UX

| Feature/Capability Set | Capabilities | Associated Commits |
| :--- | :--- | :--- |
| Dashboard state reliability | UI state persistence, cache correctness, optimistic behavior fixes | `31f8276`, `8d160b6`, `abf7aa2` |
| UI test hardening | E2E auth stability, SPA readiness and route stabilization | `ecbc007`, `a19037a`, `d1d54fb`, `9d7b873` |

## Security, Policy, and Release Governance

| Feature/Capability Set | Capabilities | Associated Commits |
| :--- | :--- | :--- |
| Security hardening | Permission tightening, API token handling, auth/health policy balance | `aaf018a`, `d107663`, `1b42640`, `e24a972` |
| Supply chain and release verification | Cosign verification workflow hardening, dependency CVE response | `2b8b033`, `7740faf`, `b39008b`, `88d9ace` |
| Repo governance and participation policy | Invite-only safeguards and policy enforcement | `f833032`, `3d974fe` |

## CI/CD and Quality Gates

| Feature/Capability Set | Capabilities | Associated Commits |
| :--- | :--- | :--- |
| Containerized CI parity | Lint/test/smoke consistency in containers | `c4ced3c`, `8ccc63a`, `3bd0c5d` |
| Workflow reliability at scale | Disk pressure mitigation, cache strategy, startup stabilization | `10d74f5`, `09c9173`, `0fcc86d`, `f6ae6b0` |
| UI/UX quality verification pipeline | Dedicated UI/UX test and release hardening path | `08cb217`, `7bfb3b2` |

## How To Refresh This Map

Generate an auto draft from recent commits:

```bash
./scripts/wb feature-map 200
```

This writes:

- `docs/feature-capability-commit-map.auto.md`

Then refine/curate updates into this file.

Manual inspection commands:

```bash
git log --oneline --decorate --max-count=200
git show <commit-hash> --name-only
```

When adding a new feature set, update:
- this file (`docs/feature-capability-commit-map.md`)
- `README.md` documentation index section
