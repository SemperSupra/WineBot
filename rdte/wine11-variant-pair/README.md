# Wine 11 dual-variant admission contract (synthetic RDTE)

Owner: mark-e-deyoung/winebot-research#3. Candidate only; no production admission, release, hardware test or protected merge.

This Go standard-library, offline contract uses explicit versioned build/session schemas (winebot/wine11-build/v1 and winebot/wine11-session/v1) and checks the **declarations** for two variants, using four independent flat JSON records (stock build, instrumented build, stock session, instrumented session):

- Exact same Wine 11.0 upstream tag, source SHA-256, toolchain and dependency-lock digests.
- Stock has no instrumentation patch queue or privileged sensor mode. Instrumented has an explicit, versioned nonempty patch digest and optional-native sensor designation.
- Separate OCI image digests. Same source-state snapshot and synthetic fixture digest for comparative testing.
- Separate proposed session IDs, generation, prefix clone IDs and writable state mount IDs. Only synthetic or cloned prefix origins admitted, never live user prefixes.
- Fail-closed missing/extra/duplicate/oversize/trailing/nested JSON and 20 negative-controls.

Run: GO111MODULE=off go test -race -count=1 ./rdte/wine11-variant-pair

The four-record CLI is: go run ./rdte/wine11-variant-pair stock.json instrumented.json stock-session.json instrumented-session.json

**Critical limitations:** Digest *strings* are not independently validated hashes or cryptographic attestations. String-distinct clone/mount IDs do not prove mount isolation, fencing, leases, namespace custody or absence of aliases. A nonempty patch digest does not establish real patched source; declarations do not establish disabled-mode behavior or event loss. A runtime supervisor must bind and verify actual OCI image digest, manifest signatures, source build receipts, prefix-state snapshot, process/mount namespace, active writer epoch and lease, human STOP preemption and fixture permission before any active session. Native Windows stays in WinBot; no duplicate VM or control plane. Future release qualification must compare real patch-off/on and stock behavior with independent WinBot oracle under exact-source and privacy gates.

All test values are synthetic; no private source or host/network access, no artifacts or images uploaded. Existing WineBot MVP/WinInspect gates remain independent.
