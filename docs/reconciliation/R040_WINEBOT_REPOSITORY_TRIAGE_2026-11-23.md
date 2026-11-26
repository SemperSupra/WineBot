# WineBot R040 — Repo, PR, branch, issue and worktree reconciliation

**Snapshot:** 2026-11-23. GitHub source authority `SemperSupra/WineBot@main:f5ba0256f330958dcf35710a822508cdb31fc40b`. Current DLE authority [research #3](https://github.com/mark-e-deyoung/winebot-research/issues/3); upstream pinned Wine11 source authority [research #1](https://github.com/mark-e-deyoung/winebot-research/issues/1). This is a **point-in-time remote GitHub inventory**, not an unconditional deletion/merge plan or substitute for live rescans.

| Observation | Exact observed scope |
| --- | --- |
| Remote branches | 191 |
| Open PRs | 48, all currently draft except where live API subsequently changes |
| Branches neither head nor base of an open PR | 141, all **retain pending owner/worktree evidence** |
| Standalone open WineBot code issues | 0 in REST issue list; open PRs are represented as issue records |
| WineBot research DLE issues | #1 upstream Wine11 source-build and #3 stock/instrumented/native three-backend charter; **both remain open** |
| Direct worktree/host filesystem inventory | **UNKNOWN/NOT PERFORMED** — connector provides remote refs, not local worktree access |
| Protected-main promotion | **BLOCKED** pending guest-writable writer lock and owner/pointer trust-boundary qualification |

## Verified reconciliation actions

1. Closed draft [#212](https://github.com/SemperSupra/WineBot/pull/212) **without merging** because all four original source Git blobs and the commit are carried into true two-parent [#214](https://github.com/SemperSupra/WineBot/pull/214), whose public exact-head full CI and Go race tests passed. **Source branch retained**.
2. Closed draft [#201](https://github.com/SemperSupra/WineBot/pull/201) **without merging** because its exact commit is the second parent of [#205](https://github.com/SemperSupra/WineBot/pull/205), whose public full CI and real source-built Wine11 55-minute composite HIL passed. **Source branch retained**; its cooperative writer lock is NOT adversary-safe.
3. Created controlled feature-branch two-parent integration [#219](https://github.com/SemperSupra/WineBot/pull/219) at `6a1a2ec46321ddb2ac4fc5d52188299d52e3337a`, grafting only original independent #216 formal-model blobs into #217 cross-UID kernel-peer branch, no protected main edit. Exact-head requalification and independent critic still required.
4. Docs [#218](https://github.com/SemperSupra/WineBot/pull/218) fixes stale Wine10 description, pins current Wine11.0 research, and embeds DLE-first minimal cold start. This manifest and report are added to the same docs-only draft.

## Current PR dependency graph and disposition

| Source / draft | Disposition, dependencies and release status |
| --- | --- |
| #200 / #201 → #205 → #207 → #211 → #213 → #214 | Sequential, exact-source MVP and protected controller admission. #201 closed as superseded by #205. #212 independent parent of #214 was also closed as superseded. #205/#207/#211/#213/#214 remain review anchors; do **not** delete branches that are PR bases. |
| #214 → #215 → #217 → #219, and #214 → #216 → #219 | Root-only Go owner/CAS+AF_UNIX SO_PEERCRED, real UID1000 negative, separate replay model, then two-parent research integration. No live runtime trusted writer adoption or production socket deployment. |
| #210 | Required **unsafe same-UID inode-replacement** evidence; passing a negative test proves the vulnerability, not secure runtime. Remains open and release-blocking. |
| #209 | Two-deployment interleaving + unsafe early-release proof; not a TLC proof of hostile lock custody. Preserve until formal integration review. |
| #194/#197/#203/#206 | Source-pinned Wine11 remote module and heap no-patch coverage. #206 live source tests pass; #203 broad conformance remains red. Do not promote semantic identity. |
| #202/#204/#208 | Historical inherited experiment startup repair stack; #208 broad conformance remains a separate red/unknown causal diagnosis. Do not auto-close. |
| #155 | Installer/fixture targeted public runs green, last full conformance failed. Owner branch must not be merged or rewritten by cleanup. |
| #218 | Docs-only cold-start and inventory; code main remains protected; independent review before documentation promotion. |

## Remote branches not associated with a current open PR

The `141` names are **review-only candidates**; no force updates, GitHub branch deletes, reflog expiry, bare repos or local worktree cleanup. Prefix census in this snapshot:

- `qualification/*`: 89
- `fix/*`: 19
- `rdte/*`: 7
- `integration/*`: 5
- `security/*`: 4
- `feat/*`: 3
- `mvp/*`: 3
- `docs/*`: 2
- `experiment/*`: 2
- `formal/*`: 2
- `ci/*`: 1
- `plan/*`: 1
- `reconcile/*`: 1
- `release/*`: 1
- `research/*`: 1

Before deleting any remote branch, independently prove: (a) no current open PR head/base, (b) no closed-but-needed PR or DLE reference, (c) no GitHub Actions/workflow or protection/ruleset dependency, (d) no active local worktree/actor, (e) source commit and evidence safely retained in an authoritative integration, and (f) owner approval for cleanup. These six predicates are **NOT yet all met** for any listed branch.

## Local worktrees — executable actor baton

The current GitHub connector **cannot inspect actual Windows/WSL2, bigmac, or TrueNAS local worktrees**, so their exact attachment, dirty status, unpushed commits and owners are UNKNOWN. The next authorized local actor should fetch without force and publish an allowlisted/sanitized summary to GitHub DLE (not private paths):

```sh
git fetch --all --prune --tags
git worktree list --porcelain
git status --short --branch
git branch -vv --no-abbrev
git log -1 --format='%H %cI'
```

Run only in the actor's **known** WineBot workspace; `git fetch --prune` updates tracking refs but must not delete local worktrees or alter uncommitted files. Report branch name, exact HEAD SHA, dirty/clean bit, upstream tracking, and any blocked ownership; **redact local absolute paths, usernames, private remotes and credentials** in public DLE. Reconcile at start and before closing; do not ask the user to relay long instructions.

## Next independent READY workcells

- **A — security critical path:** bind actual writer and durable owner generation to a dedicated trusted process/volume outside guest UID1000 mount; verify separate principal, bounded authenticated IPC, STOP priority, crash/ABA and host mount identity. Keep untrusted Windows PE release **STOP**.
- **B — atomicity:** classify each guest action as read-only, target-proven-idempotent, or non-retryable UNKNOWN after ambiguous ACK; do not infer exactly-once from controller CAS.
- **C — Wine11/observatory:** recover source-pinned stock/instrumented/native comparison, WinInspect and held-out semantic critic on rights-cleared synthetics; root-cause conformance red without unsafe log disclosure.
- **D — housekeeping:** after local worktree census, close only source-exact superseded drafts with durable successor links; no blind pruning of the 141 remote unreferenced names; rescan heads before any state transition.

## Secondary closed-PR provenance reconciliation

The **complete available** first-page REST list contains **84 closed PRs** (the second page was empty). Of the 141 branches not used as the head/base of an open PR, **52** are still named heads of a closed PR, and **89** have no observed open-head/base or closed-PR-head relationship. The latter group is **NOT presumed disposable**: it includes experiment source authority, historical automated qualification, possible actor worktrees, and unregistered workflow references. See the machine-readable `closed_pr_head` field in the adjacent JSON snapshot. Neither category is cleared for deletion.
