# RDTE — WineBot-owned local WinEvent observer process

Date: 2026-10-25. Scope: public synthetic fixture-class Win32 program
only. This is **not** admission for production event capture, real
applications, externally accessible endpoints or input mutation.
Durable workset: https://github.com/mark-e-deyoung/winebot-research/issues/1

## Discover / Observe

The following are independently verified:

- Original pristine source Wine 11.0 WoW64/Notepad smoke:
  Actions 40010876411 **PASS**.
- Wine 11.0 WinEvent synthetic observer+X11:
  Actions 40045850159 **PASS**.
- Debian Wine 10-style public base WinEvent + bridge cursor:
  Actions 40075822335 **PASS**.
- Custom Wine 11.0 complete synthetic WinEvent→EventBridge:
  Actions 40076089386 **PASS**.
- Session-observation FastAPI authorization, collector state, stale
  session rejection: 11 tests **PASS**, plus 10 local-source lifecycle
  tests and 3 server import/mount gates **PASS** in Actions 40150194533.
- Disposable public-base derived-image server startup, default disabled
  vs token admission: Actions 40150322980 **PASS**.

None of the above launched a WineBot-owned observer process *via the
same session-bound adapter*. That is the remaining gap this experiment
is designed to falsify. Existing WinInspect v0.4.4 draft #136 remains
separately RED; proposed upstream RPC fix already exists (WinInspect
PR #18) and must not be duplicated or presumed merged.

## Plan and Apply

A strictly internal process owner, \`api/core/wine_events_process_rdte.py\`,
launches exactly \`wine /opt/winebot/rdte/win_event_observer.exe\`.
There is **no program path, executable or argument supplied by an HTTP
caller**. The Win32 observer only accepts callbacks from fixture class
\`WB_RDTE_WINDOW\`; it emits only \`schema/kind/sequence\`.

The owner:

- requires matching current active WineBot session and Input Broker
  session before launch and before every read, including across
  handover;
- passes the Wine child a minimal whitelisted environment (not
  \`API_TOKEN\`, credentials or arbitrary runner variables);
- uses no shell, stdin, log files, screenshots, network calls,
  credential payloads, process ID recording or raw event publication;
- reads stdout using bounded incremental bytes and finite UTF-8 JSONL
  frames, then delegates exact schema validation, source sequence,
  overflow and lease-bound cleanup to the already-qualified adapter;
- enforces maximum 256 bytes per line and the existing 24 KiB total
  budget; a monotonic hard deadline no greater than 22 seconds;
- terminates the observer's process group and scrubs retained event
  state on EOF, nonzero exit, timeout, malformed input, handover and
  unexpected child failure; status is a fixed allowlisted string;
- is single use. A new observer requires a new owner and a valid
  current session.

The test injection of a subprocess factory is for trusted Python unit
tests only; it is not a controllable API parameter or public gateway.

The disposable Wine runtime builds the same publicly licensed Win32
observer and synthetic fixture under MinGW \`-Werror\`, uses the public
WineBot base (tag **not yet digest pinned**), ephemeral Wine prefix,
Xvfb with no TCP listener and a network-disabled, capability-dropped
container. It verifies observer readiness, X11 fixture presence,
show/location semantics observed *while* the process is alive,
clean-EOF event erasure, new-process restart and session handover
termination/erasure.

## Verify and negative controls

Workflow:
\`.github/workflows/wine-events-owned-process-rdte.yml\` under branch
\`qualification/wine-events-owned-process-20261025\`:

1. **Fast unit lane:** synthetic child controls validate clean EOF,
   ready/initial-state, restart, timeout, error exit, missing ready,
   truncated and malformed events, oversized records, source gap,
   hardcoded argv and withheld \`API_TOKEN\`, in-flight session changes.
2. **Actual Wine lane:** only runs after fast unit PASS; builds a new
   ephemeral test container, then tests the real Windows synthetic
   observer and GUI fixture. No production WineBot image change or
   WinInspect dependency.
3. Failures are retained, not weakened. First status from the actual
   job controls the next change; never infer a result from the
   previously passing unit lane or predecessor builds.
4. Run-artifact enumeration separately verifies zero attachments;
   it cannot certify that logs, source history or base images are
   disclosure-free.

## Remaining boundaries

The API itself remains disabled by default and requires a nonempty
instance token; independent authorization for human, automation and
agent identities is **not** yet implemented. This owner does not
automatically start in the actual WineBot server. Mounting the optional
API is not proof of the daemon lifecycle, a full application or UIA
accessibility semantics. Real-world CV/visual ground truth, games,
renderer stress, WinInspect RPC and native Wine patch decisions are
separate qualified workstreams.

Next baton after runtime PASS: independently review a strictly opt-in
session startup/shutdown integration for the owner; verify that the
actual service can see the synthetic fixture without exposing raw
frames, adding public ingress or changing input leases. Preserve
private security and disclosure gate
\`SemperSupra/agent-dispatch-private#515\`, general v1 conformance,
source provenance and all merge/release gates.
