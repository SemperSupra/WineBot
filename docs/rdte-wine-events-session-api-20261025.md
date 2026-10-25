# WineBot opt-in session observer API — 2026-10-25

Status: **RDTE / NOT production admitted**. Source branch:
\`qualification/wine-events-session-api-20261025\`. DLE:
https://github.com/mark-e-deyoung/winebot-research/issues/1.

## Evidence inherited from live Wine

- Unmodified-source Wine 11 + 64-bit Notepad + 32-bit WoW64 CMD:
  Actions 40010876411 PASS.
- Unmodified-source Wine 11 + synthetic Win32 \`SetWinEventHook\` observer,
  X11 fixture and strict JSON event validation: Actions 40045850159 PASS.
- Debian Wine + actual synthetic Win32 stream + in-memory event bridge cursor,
  close/erase and eight adversarial byte-stream regressions:
  Actions 40075822335 PASS.
- Unmodified-source Wine 11 + entire observer, validator and in-memory bridge
  chain: Actions 40076089386 PASS. Both runs produced 0 attached artifacts.
- These tests **do not** establish UIA accessibility, live arbitrary-app
  coverage, image annotation fidelity, deterministic control or game quality.

## Experimental API surface

Opt-in \`WINEBOT_WINE_EVENTS_RDTE_ENABLED=1\` **and** a nonempty
\`API_TOKEN\` (configured before server startup) are mandatory for the
router to be mounted. With the default environment the route does not
exist. Every request also enforces both conditions independent of the
legacy global API authentication dependency.

GET \`/sessions/{session_id}/observations/wine-events?after=0&limit=64\`
with \`X-API-Key\` supplies *only* the synthetic, bounded,
read-only \`winebot.wine.event.v1\` stream. A sibling GET endpoint
\`/capabilities\` reports collector state and explicit \`unqualified\` UIA
and CV status.

The request session must match both the active WineBot filesystem session
and the current Input Broker session. A missing active session is 409;
another session is 404; a broker mismatch or transition during the request
is 409. On handover, the prior in-memory bridge is closed and cleared.
A non-running or unattached producer yields the explicit
\`state=unavailable\`, not fictional events.

The registry's \`attach_internal\` is for a future trusted in-process
producer; the router includes **no** POST/PUT/PATCH/DELETE ingestion,
control grant, subscription mutation or screenshot endpoint. No producer
is started by this RDTE. No writes to disk or raw identifiers are supplied
by the current stream. Each actor that is entitled to the same session can
use the same read-only cursor without consuming another actor's view.

## Boundaries and explicit limitations

**This is not actor-specific authorization.** The current WineBot shared
API key authenticates the instance, not each human/automation/agent
separately. Before wider deployment, add an independently approved
audience-scoped authorization policy (when required), supported session
lease binding, stream provenance and producer lifecycle management;
do not infer these from the existing Input Broker mutation leases.

**This is not the production service yet.** The API/router and a
Dockerfile copy of the local adapter exist only on an isolated
qualification branch. Even if its unit tests pass, independent whole-image
build, unauthenticated deployment tests, source custody, disclosure,
conformance and review are required before inclusion in main.

The old WineBot base may have token-optional legacy routes. This optional
observer therefore requires a nonblank token **even if other routes do not**.
It must not publish when no token was configured prior to server start.
A collector not admitted by separate safety/provenance gates must stay
unavailable. Do not expose source data through raw socket, HTTP ingestion,
MCP ingestion, user scripts or telemetry.

## Discover → Observe → Plan → Apply → Verify

1. Review the exact source branch and test logs of the public
   \`wine-events-session-api-rdte\` workflow; preserve first failure and
   correct only this isolated branch.
2. Test default-off, missing/wrong token, absent session, stale Input
   Broker session, cross-session access, session handover, GET-only method
   restrictions, shared read-only cursor across all three audiences and
   capability truthfulness.
3. Validate the in-container image wiring and startup gating separately.
   Python source import tests alone **do not** prove the Docker composition.
4. Admit a trusted local Wine event producer that binds a verified
   synthetic observer to a WineBot session. Never add a public ingest endpoint.
5. Only after independent review: add per-audience UI/UX/DX consumers,
   MSAA/UIA or WinInspect semantic augmentation, scoped CV ground truth
   and action/postcondition correlation.
6. Preserve the separate WinInspect v0.4.4 RPC response-ID blocker,
   portable v1 contract red gate, security/disclosure authority
   \`SemperSupra/agent-dispatch-private#515\`, and all production
   merge/release gates.


## Next bounded local-producer boundary (implemented, not yet process-backed)

\`api/core/wine_events_source_rdte.py\` provides
\`TrustedLocalEventSource.feed_internal\` for a WineBot-owned **in-process**
consumer of a pre-existing locally qualified event stream. The method:

- checks that both active filesystem session and Input Broker session match
  its fixed creation-time session before consuming *each* record;
- accepts only complete UTF-8 JSONL records, with existing exact-schema,
  strictly sequenced EventBridge validation;
- enforces 129 records maximum (ready + 128 events) and 24,576 total bytes,
  with no title, HWND, coordinates, text or other extra fields;
- attaches the source to the in-memory registry only after a valid ready@0
  handshake, without external input or HTTP writes;
- closes, scrubs and denies further feed when a source fails or session
  changes; a replaced/stale source uses \`clear_if_owner\` and cannot erase a
  newer session's bridge;
- is tested against session and broker mismatch, callbacks raising errors,
  malformed input, gaps, byte/count limits, source close and replacement.

This component **does not launch Wine, Xvfb, WinInspect or an application**.
It also does not implement background process lifecycle, OS pipe permissions,
external identity/actor grants, replay or visual annotation. A qualified
Wine source process owner remains the next separate node, not a hidden
assumption of success.

The additional regression stage lives in
\`.github/workflows/wine-events-session-api-rdte.yml\`. Require actual
passing Actions result and exact source SHA before considering this producer
boundary qualified; continue to preserve early red/negative evidence.
