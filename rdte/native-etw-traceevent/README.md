# Native Windows ETW source-qualified minimal workcell

Objective: prove a real ETW user-mode event flow from an original rights-cleared EventSource through Microsoft's open-source TraceEvent library, with a bounded consumer and a fixed pass/fail receipt on a standard public free-tier Windows runner.

Package: Microsoft.Diagnostics.Tracing.TraceEvent 4.0.0, MIT, resolved from NuGet. The first RDTE pins the direct version but transitive package digests require a committed NuGet lockfile before the next release gate. The producer emits exactly three synthetic state IDs. The consumer subscribes only to that provider GUID and self process ID. It does not print payloads, stack traces, system ETW events, user data or session names.

This is USER ETW only, not a privileged kernel trace, historic replay, Wine instrumentation, or proof of system-wide process events. It is a deliberately independent sensor workcell separate from the native NT phnt query and Wine11 source build.

The ETW session is uniquely named and disposed via scoped using. Bounded startup / collection / shutdown timeouts guard hangs. Negative controls and event-loss metadata must be extended before any cross-process or native WinBot use. Fail closed on missing provider events or privilege errors.

Public project keeps only original synthetic code and reviewable package metadata. Native Windows WinBot implementation and HIL remain in its separate DLE authority. No private repo/minutes, driver, protected branch or release modifications.
