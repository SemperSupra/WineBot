# Real Wine new-session generation handover — 2026-10-27 (RDTE only)

Parent: local cursor source branch at fb6e93eec23424a8cbd9b2c868c69f9168eb228c.
Owning DLE: https://github.com/mark-e-deyoung/winebot-research/issues/1

## Question

Does the already qualified fixed Win32 Wine/Xvfb observer produce a genuinely
new session stream whose sequence starts again at 1, and will the new local
version-1 cursor discriminator refuse an earlier collector's cursor even
after source sequence 1 is reused?

## Exact bounded test

- Build only the existing synthetic WineBot API/observer overlay, then a
  disposable local Docker overlay containing the new local cursor module,
  test harness and launch shell; do NOT push or release images.
- Run offline as unprivileged winebot, with caps dropped, no new privileges,
  2 CPUs, 4GiB, 256 PIDs and no network.
- Set up one fresh isolated Wine prefix, Xvfb and the pinned fixed-class
  WB_RDTE_WINDOW Win32 observer+GUI fixture already qualified by predecessor.
- Start owner A, attach local GenerationCursorView to its already admitted
  internal source bridge, run real Wine GUI fixture, require actual events
  including show and location with first source sequence 1. Retain cursor
  after event 1; cooperatively stop owner and assert scrubbing/cancellation.
- Admit a **different** owner session B. This is NOT same-session auto-restart.
  Require a new Wine observer ready and the actual synthetic Win32 GUI
  fixture producing show/location again starting at sequence 1.
- Check old cursor fails via session_mismatch; even when a hostile test
  changes only its session label, old generation fails as stale_generation.
  Read concurrently or independently for human/automation/agent; no special
  actor privileges, observer selection or individual actor authentication.
- Stop the second owner, require event erasure, no source leak or child
  orphan. Fail-closed on missing fixture, first source gap, bad output,
  stale owner takeover or thread/child cleanup.
- Emit only fixed pass/fail stage codes; never print Wine logs, events,
  titles, PIDs, executable paths, hardware identifiers or screenshots.

This validates only fixture-class source and local cursor behavior, not a
production HTTP endpoint, cross-process generation registry, cryptographic
authorization, general Windows GUI apps, UIA/AT, CV training or real games.

## Red-team and controls

Do not enable same-session restart or per-actor privileges. Fail on a new
session with absent Wine callbacks or unexpectedly continuing old source
sequence. Historical observer soaks, software renderer and WinInspect PRs
retain their independent evidence and are not rerun here.

The workflow is public branch-only, push-triggered, checkout SHA-pinned,
repo read-only, zero upload actions, non-root runtime and no reusable
production-image promotion. Check actual Actions run/job and artifacts
before calling real Wine PASS. Mark any failed phase explicitly RED.

Security #515, source custody, v1 conformance, owner review, merge and
release gates remain unchanged.

Next baton if qualified: design atomic trusted generation creation and
lease-scoped handover under the actual session/broker owner, then evaluate
consumer migration with independent three-audience identity controls.
