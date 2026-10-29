# Upstream Wine hooks and fencing prior art — 2026-10-29

## Scope and custody
Source-oriented review of public upstream Wine paths and external prior art; no Wine patch, source redistribution, binary release, or owner-gate bypass. Verify pinned upstream SHA and actual target Wine build before adopting implementation details.

## Wine implementation seams
- `dlls/user32/hook.c`: `SetWinEventHook` delegates to `NtUserSetWinEventHook`; `User32CallWinEventHook` dispatches callback. https://github.com/wine-mirror/wine/blob/master/dlls/user32/hook.c
- `dlls/win32u/hook.c`: `NtUserSetWinEventHook` registration and `NtUserNotifyWinEvent` event delivery, with server `get_hook_info` / `finish_hook_chain` requests. https://fossies.org/dox/wine-11.19/dlls_2win32u_2hook_8c_source.html
- `server/hook.c`: hook owner, handle and chain lifecycle; `remove_hook`, `start_hook_chain`, `get_hook_info`. https://fossies.org/dox/wine-11.18/server_2hook_8c_source.html
- Windows API semantics: `SetWinEventHook` requires a message loop on the installing thread, supports out-of-context callbacks, and may reenter callbacks. https://learn.microsoft.com/en-us/windows/win32/api/winuser/nf-winuser-setwineventhook

## Prior art to qualify, not blindly copy
- Kubernetes stale-controller mitigation: resource-version freshness checks at consequential decisions. https://www.kubernetes.dev/resources/keps/5647/
- EtcFS generation guard: stale generations rejected at transaction commit; process self-fencing is not by itself sufficient to prevent already-issued writes. https://pkg.go.dev/github.com/etcfs/etcfs/pkg/fencing

## Candidate corrective action
1. Keep broker incarnation and admission in WineBot. An upstream Wine hook handle is not a WineBot session authority.
2. Gate attach/feed/observe publication by immutable broker incarnation at the mutation boundary, not merely on process startup.
3. Preserve exact-bridge `clear_if_owner` and bounded EventBridge overflow/gap behavior.
4. Instrument synthetic hook registration, callback entry/exit, reentrancy, unhook and message-loop termination as separate typed events.
5. Red/blue test stale callback after unhook, s→other→s ABA, nested callbacks, hook removal during callback, message-loop starvation, and shutdown without global cleanup.
6. Evaluate custom Wine instrumentation only if stock Wine cannot provide required evidence; pin version, patch, license, regression tests, and public source custody first.

## Gate
No upstream patch is authorized or proven necessary. Next executable step is to implement broker incarnation and source fence on independent branches, then run public GHA actual-code tests and real Wine/Xvfb fixtures.
