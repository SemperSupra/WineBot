# Compatibility qualification comparator MVP (source-only)

**Scope:** Deterministic native Windows/Wine **API or workflow** assertions. This is a synthetic, fail-closed comparator only. It does not invoke Wine, WineTest, WinBot, Windows, X11, or computer vision. It does not prove Windows compatibility until independent, admissible observations from both runtimes exist. Visual, accessibility, renderer, gaming, performance, and stability comparisons are **UNQUALIFIED** in v0.

## Existing work and ownership

The broader design is documented in [draft plan #142](https://github.com/SemperSupra/WineBot/pull/142). The Wine-specific comparison implementation belongs in WineBot. WinBot owns native Windows execution. The genuinely portable contracts belong in `winebot-contracts` only after semantic review. Agent Dispatch provides idempotent, bounded scheduling; this module does not create another scheduler or control plane.

## Input and outcome policy

Both JSON observations conform to `qualification/schemas/observation-v0.schema.json`. For deterministic comparison, the observations must agree on complete `scenario`, input checksums (the **same Windows executable and synthetic fixture**), and the declared display/renderer profile. They must carry complementary `execution.lane` values (`windows` and `wine`), exact source-head and tested-checkout Git SHAs, and sufficient declared `capabilities` for the scenario. `run_id` is a bounded opaque identifier rather than a hostname or path. The observation's `observed_sha256` must come from the *same deterministic, normalized semantic output bytes* on both lanes; hashing unnormalized log text, window pixel images, platform-specific object handles or hidden environment metadata is not valid evidence of functional equivalence.

Outcomes are:

- `PASS`: all assertions match and the native Windows oracle and every required capability are available.
- `FAIL`: valid Windows oracle and confirmed differing candidate outcome or deterministic output digest.
- `UNQUALIFIED`: missing assertion, Windows oracle failure, unsupported test class, missing capabilities, mismatched executable/fixture/scenario, mismatched profiles, or skipped assertions.
- `INFRA_ERROR`: runtime/observer failed before its assertion could be evaluated.

Malformed inputs are rejected without publishing a result. An *absent Windows observation* never becomes a synthetic reference. Mixed per-assertion statuses do not inflate a pass rate. This MVP compares one pair of snapshots, not distributions/repeated trials or probabilistic equivalence; collecting repeated trials remains a later gate.

## Local source-only verification

```sh
python -m pytest -q tests/test_compatibility_comparator.py
python -m qualification.compare --windows /admitted/windows.json --wine /admitted/wine.json --public-report /admitted/summary.json
```

CLI exit codes: 0 PASS; 1 FAIL; 2 UNQUALIFIED; 3 INFRA_ERROR or rejected invalid/missing input/output. `--public-report` is mandatory and output is exclusively fixed-schema summary counters, verdict and reason enumeration. No raw assertions, filenames, paths, host/environment attributes, logs, screenshots, credentials, application IDs, or input digests enter the public summary. **Not all summaries are automatically authorized for publication**; source and security gates remain separate. Do not pass actual sovereign or personal observations to public CI.

## Safety and admission

This implementation must be qualified against private security authority `SemperSupra/agent-dispatch-private#515`. Existing public CI/artifact mitigation drafts #124/#125/#127/#129 and disposable RDTE #130 are not implicitly merge-authorized by this module. The comparator and unit fixtures alone run locally; a public workflow must use qualified synthetic fixtures and a separately admitted publication boundary. Neither release nor merge is authorized.

## Next READY baton

1. Prove v0 schemas and implementation agree using positive/negative fixtures and a source-only test lane.
2. Qualify WineTest availability on pinned Windows and Wine executors, with identical signed/hashed test binary (discover module list first).
3. Create a freely redistributable deterministic Win32 PE sample and independent native WinBot/WineBot observation adapters; require same PE and fixture hashes.
4. Run paired qualification; record exact run/job IDs, tested checkout and PR source heads, observed capabilities, first failure, public/private evidence custody, and blockers. Do not report Wine-only results as native Windows compatibility.
