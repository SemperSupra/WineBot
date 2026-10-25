# WineBot synthetic long-lived WinEvent observer — bounded RDTE

Date: 2026-10-25. Authority: [WineBot DLE #1](https://github.com/mark-e-deyoung/winebot-research/issues/1). **Not production-admitted.** Protected `main` must not change.

## Discover / Observe

The experimentally qualified upstream is `qualification/wine-events-service-lifecycle-20261025@cfcfbb96cb04b770420ca4abcb06fac63b95003c` (last *runtime tested* commit `0f81beea362fb9aab56a00580edecbb45321bb1a`, Actions 40159357875: 47 FastAPI/lifespan checks and actual Wine fixture callbacks + authenticated GET + shutdown PASS). The no-patch Wine 10 and Wine 11 hook controls already passed; upstream Wine patches are not warranted. Before this change Win32 observer expired after 12 seconds; process deadline was 18 seconds; service admitted only one process start in a session. There was no intentional terminal overflow classification, private orderly stop command, or bounded same-session renewal.

## Plan / Apply

This branch remains a **fixed-command, fixture-class-only** observability experiment. No arbitrary application selection, event injection, public HTTP producer endpoint, title/text/geometry/handle exposure, vision inference, secrets, real media, or upstream Wine source patch.

- Win32 `SetWinEventHook` remains restricted to `WB_RDTE_WINDOW`; emits only schema `winebot.wine.event.v1`, synthetic kind and monotonic sequence. Its single private stdin PIPE recognizes only the `Q` stop byte, polled from the Win32 message pump; malformed commands fail; closed pipe stops. An internal hard 120-second lifetime prevents indefinite or orphaned observation. Retain 128 callback events plus one explicit terminal overflow sentinel, which triggers a nonzero exit.
- WineBot retains sole process and group ownership, stripped subprocess environment, `close_fds`, `start_new_session`, nonpublished stdout, deadline at most 150s and default service deadline 110s. On stop it first signals the same fixed process over its private pipe; after bounded grace it signals/kills only that group. Source and cursor state is erased unconditionally.
- Source and in-memory EventBridge reject an explicit overflow sentinel as `source_overflow`, never as successfully delivered content. Sequence gaps, invalid fields, byte/record/line caps, timeout and process failures fail closed. Source overflow is classified in the owner verdict before erasure. Reads remain nondestructive with independent cursors; older history gaps are explicit, never silently replayed.
- The existing service may renew **at most once** in the same session, and only after previous worker termination and >=1 second cooldown. Session replacement gets a new two-start budget after the prior worker exits; any stopped service denies admission. This is a bounded lease experiment, not a daemon with unlimited crash retries.
- No change to the authentication, Input Broker, user/agent scopes, HTTP mutation, GET authorization, real-app observation, WinInspect RPC, portable conformance requirements or production image.

## Three-audience behavior

Humans see the same authenticated read-only session capabilities, including truthful unavailability while not attached; this is *not* screen-reader or UIA semantic qualification. Automation obtains stable JSON schema, independent `after` cursors, explicit `history_gap` and fail-closed no-events on collector loss. Agents receive the identical facts and negative capabilities with no separate privileged endpoint or access to raw Win32 identifiers. **Independent per-actor credentials and accessible visual/AT affordances remain gated**, not implemented by this experiment.

## Adversarial qualification

New self-contained Python suite covers an orderly stop during an active observer, stop before readiness, nonzero child exit, callback overflow, missing source sequence, byte exhaustion, two simultaneous readers, session takeover, stale cleanup, and capped same-session renewal. Prior 47 tests remain regression gates. Actual public Wine/Xvfb E2E must show observer still `ready` after more than 12 seconds without fixture traffic, then authenticated fixture callback → GET, and clean API lifespan shutdown.

The branch-specific, push-triggered workflow runs tests on public `ubuntu-24.04` and builds only a **disposable** derived synthetic overlay for actual Wine/Xvfb. Runtime is `--network none --cpus=2 --memory=4g --pids-limit=256 --cap-drop=ALL --security-opt=no-new-privileges`; nonroot image user. No artifact uploads, screenshot publication, image pushes, public listeners, private GH Actions or cloud spend. CI success must be verified at its **exact tested SHA**, not inferred from compilation or historical runs. Inspect outputs only for allowlisted PASS/FAIL markers and enumerate attached artifacts.

### Known uncertainty and stop rules

- Real Wine `PeekNamedPipe` behavior through inherited stdin is unqualified until the Win32 fixture CI run; a failure must be classified before changing the stop contract.
- Existing `base-2026-05-04` image is tag-pinned, **not digest-pinned**; bitwise reproducible comparison is unqualified.
- Callback delivery under a synthetic fixture is not a full Windows event reliability guarantee. Overflow may be reported as an owner failure and stream unavailable, but a per-actor loss-notification/UI contract requires independent security and consumer admission.
- This proves neither production continuous service nor memory/RSS statistics from a sustained multi-hour observation; the enforced limits are structural plus container cgroup caps. Do not report a time series without measured receipts.
- Active security/disclosure authority: `SemperSupra/agent-dispatch-private#515`; legacy conformance still red; WinInspect #136/#139/#141, game/rendering and thin portability contracts separate. No merge, release, production base promotion or disclosure-gate waiver.

## DLE verification receipt

Record branch exact head, compile/unit/live job IDs, FIRST FAIL stage and fix, artifact enumeration, and next bounded independent qualification at the owning [DLE #1](https://github.com/mark-e-deyoung/winebot-research/issues/1). For failed actual Wine stop-pipe support, retain the previous qualified lifecycle branch unchanged, correct only this isolated branch, and requalify before promoting even experimental assertions.
