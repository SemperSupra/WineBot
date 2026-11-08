# Pandora Agent Dispatch admission — WineBot

Status: **proposed / source only**. This is a least-authority materialization of WineBot's authoritative PR/DLE state, not a second control plane. The project-owned workset is `worksets/agent-dispatch.json`.

## Trust boundary

- Caller: existing **`openai-tunnel`** MCP client on **Pandora** (not the disconnected legacy Sidecar).
- Exact workset locator: `github-file:SemperSupra/WineBot@main:worksets/agent-dispatch.json`.
- Delegation: `winebot-observe`, caller class `observe` only.
- No public/private runner dispatch, credential change, host mutation, repository write, merge, or release.
- No new tunnel, service, credential, scheduler, or database.

## Admission and verification

1. Merge the reviewed WineBot workset into `main` after its source and safety checks pass. The locator is **not** valid on `main` until then.
2. On the trusted Pandora host, use the repository-supported grant helper. **Existing exact admission entries must be preserved**; the `--admissions-file` mode replaces the selected client's full admission list and is *not* safe with a one-line fragment.
3. Preview first, apply exact grant atomically, then perform a controlled existing-sidecar reload/restart (it loads credential claims at initialization).
4. Using **Pandora MCP**, call `get_work_projection` with the locator above and delegation `winebot-observe`. Verify grants are read-only; run `resume_delegation` only after observation is accepted.
5. Record redacted PASS/BLOCKED receipt in the owning WineBot PR and Agent Dispatch DLE. Keep all WineBot execution assignments on hold pending separate exact `plan` / `actuate` decisions.

The host-side helper should retain all existing `openai-tunnel` grants, refuse wildcard/ambiguous identities and never print token keys or secret-bearing client configuration. Its preview must show the exact narrow change before application.

**Executor activation is a separate phase**: Pandora's `plan_execution` and `dispatch_execution` need a project-owned assignment, a qualified exact target, and an independently admitted caller class with specific assignment IDs. This document grants neither.
