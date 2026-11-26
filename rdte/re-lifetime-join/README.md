# Synthetic Wine 11 current-state / heap-lifetime join (research-only)

**Owner:** mark-e-deyoung/winebot-research#3. This is a stacked candidate on source-exact typed evidence WineBot PR #190. The integration branch reuses the **same immutable Git blob SHAs** for the original Go trace parser and negative controls from pinned source-built Wine 11 research PR #197, rather than creating a forked parser.

Offline run (Go standard library, no dependencies):

    GO111MODULE=off go test -race -count=1 ./rdte/re-observation-contract ./rdte/wine11-heap-trace ./rdte/re-lifetime-join

Input #1: strict three-row module / heap allocation / containing memory region Win32 current-state fixture verified by NormalizeWine11CurrentStateWitness. Input #2: bounded filtered Wine 11 heap TRACE stream verified by VerifySyntheticLifetime. Join requires exactly the same allocation pointer and size and a successful allocate-then-free sequence. Negative controls refuse mixed witness process, fabricated app class, invalid source, wrong heap, duplicate/reordered events, wrong extent, malformed record, or resource-budget overflow.

Output: a fixed metadata-only v1 Receipt. **No pointer, heap handle, PID, raw trace, stack memory, or application object metadata.** Evidence class remains SYNTHETIC_CONSISTENCY_ONLY, trust/source UNVERIFIED, process attribution and trace completeness UNKNOWN, clock correlation UNAVAILABLE, and application semantics UNKNOWN.

Limits: The same memory pointer in two independently supplied text streams **does not attest common process/generation**, actual Wine 11 source, time order across hosts, event-loss bounds, or reliable first-writer attribution. Git SHA remains externally asserted until independently bound by source/run/fixture custody. The separate live Wine 11 +heap success at PR #197 is not inherited as a proof for this join. This does not implement an API endpoint, production Wine fork, actual WinBot reference comparison, Ghidra/Observatory pipeline, arbitrary target, or authorized debug actuation.

No private GHA minutes, artifact uploads, images, restricted target bytes, host modifications or main merge. Next integration gate is exact-source/process-generation/clock/loss binding under WineBot/Observatory owners and externally qualified live fixture capture. Keep this workcell draft.