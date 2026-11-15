# Agent Dispatch read-only observation admission — WineBot

Status: **candidate / source only**. GitHub project-native PR/DLE remains authoritative; this workset is not a new dispatcher or grant. Public source MUST omit real deployment host and MCP client identities. Trusted-host configuration and exact identities belong only in the private security/ops authority.

## Public trust boundary

- Exact public workset locator: `github-file:SemperSupra/WineBot@main:worksets/agent-dispatch.json`.
- Delegation: `winebot-observe`; caller class `observe` only, repository read and bounded CI reconciliation.
- Money and workflow dispatch budgets: zero, hard-enforced.
- No workflow invocation, client-credential change, host mutation, repository write, merge, release, new tunnel, service or scheduler from the delegation.
- Publication of the workset does **not** admit a client; server-side caller grants are separately governed.

## Admission and verification gates

1. Independently review the exact public candidate for source safety, permissions, disclosure and no-actuation tests, then obtain source promotion authorization. The `@main` locator is unavailable until reviewed source reaches `main`.
2. A trusted operator uses the **existing private-host** admission helper only after checking the actual caller-grant representation. Do not migrate legacy grants by simple append, silently broaden read authority, or replace existing client admissions from a one-line fragment.
3. Preview the full effective grant diff, preserve every unrelated grant and credential, apply atomically only if authorized, and reload the existing service in a controlled manner.
4. Read `get_work_projection` through the connected sidecar using the exact locator and `winebot-observe`; verify read-only scope, no dispatch, and successful fresh-process continuation before recording a sanitized receipt.
5. Save source-bound PASS/BLOCKED evidence in the owning GitHub DLE. No confidential host/client identity, credential, raw logs, machine configuration, or session identifiers in public source, comments, logs or artifacts.

Actual executor bindings, assignments, `plan_execution`, `dispatch_execution`, promotion and publication require **separate** governing authority. Nothing in this workset grants them.
