# WineBot observation receipt command (synthetic RDTE)

A local, read-only command for the already qualified Wine 11 synthetic current-state / heap lifetime join. It imports the original parser libraries without modifications.

Build from this repository:

    GO111MODULE=off go build -o winebot-observation ./rdte/re-observation-cli

Run against an independently authorized, local synthetic fixture directory:

    ./winebot-observation -witness witness.jsonl -trace filtered.heap -source-commit <exact-asserted-producer-commit>

Exit 0 emits a single metadata-only JSON receipt on stdout. Exit 1 refuses invalid input or an unavailable file; exit 2 refuses invalid usage. Failures emit a fixed category only, with no raw addresses, paths, memory or traces. No network service or automatic runtime actions. Do not use adversarial filesystem locations or real user captures; the tool is not a sandbox.

Human: inspect the receipt or use jq. Automation: check exit status and the schema before consuming JSON. Agent: use the same schema and treat UNVERIFIED/UNKNOWN/UNAVAILABLE as explicit limitations, not successful authentication or missing work to hallucinate.

Actual historical producer qualification: WineBot PR #206 exact fe2ac64de5e00bb9879ff26555b547bcf87da6f7, public run 45174475488, actual source-built Wine 11 synthetic join PASS. Its unrelated broad conformance failure is retained. This integration transfers libraries into the #181 MVP lineage, requalifies the offline command and does not rerun the source compile. No inference of source attestation, real application semantics, continuous event coverage, cross-process causality, or production acceptance. Native WinBot comparison and Observatory ingestion remain separately qualified tasks.
