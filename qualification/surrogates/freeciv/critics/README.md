# Reversing observatory — public-safe critic candidate interviews

This folder is a source-neutral qualification fixture, **not** a deployed agent or a route to private game/runtime sources. The public GitHub Actions matrix must use CPU-only ephemeral runners, with no account tokens, credentials, private checkout, licensed game assets, raw customer/game captures, external listening ports or model-generated code execution.

## Previously adopted candidate interview protocol

Unit of qualification: `task × harness × model × configuration × tool permissions × compute substrate`. A candidate passes a **specific bounded task**, never a general benchmark or self-granted authority. Preflight requires exact source/model revision, license, resource envelope and independent ground truth. Execute against matched positive/negative and contradictory controls; perform repeat/crossover tests, report accuracy, false-positive/hallucination, latency, memory, reproducibility, first failure and limitations. Compare deterministic oracles alongside each model. Preserve failing candidates in DLE rather than turning unknown into green.

| task | candidate | expected use | exact acceptance limit |
| --- | --- | --- | --- |
| Evidence reasoning | `Qwen/Qwen2.5-Coder-0.5B-Instruct` revision `ea3f247` | rank next authorized observation, not permit actions | strict JSON + all cited evidence from fixture; fabricated references/actions fail |
| Frame/video VLM | `HuggingFaceTB/SmolVLM2-256M-Video-Instruct` revision `e62441b82f8a003a40e89eee6005489a0e9c0598` | compare controlled object motion across two source-known frames | left/right opposite controls; reported word must be unambiguous |
| Speech/audio critic | `openai/whisper-tiny` revision `169d4a4` | speech transcription on source-known synthetic sample | spoken "save the game" versus silence; silence hallucination fails |

**Not yet represented by a model here:** generic non-speech game SFX classification, frame-by-frame pixel segmentation, object ID attribution, full video event detection, multilingual speech/noise robustness, source-code repair autonomy or an actual integrated reasoning agent. Future candidates include AudioSet AST for environmental sound classification; Whisper is a speech model, not a sound-effect detector. Each requires separate matched datasets, threat-model and resource qualification. A failed CPU inference or unavailable published artifact remains `UNQUALIFIED` with typed failure, never a fabricated model score.

## Why this is not a Cloudflare MCP bridge

The candidate workflow runs short, bounded one-shot evaluations and uploads sanitized summary JSON. It does **not** expose an HTTP server. An ephemeral Cloudflare Quick Tunnel can expose a workcell endpoint, but a random hostname is not authentication; a public tunnel can be called by anyone who knows its URL and lasts only while the underlying process remains active. Before a ChatGPT/agent connection is eligible, require a registered client supporting streamable HTTP MCP, scoped authentication, per-tool authorization, TLS, signed immutable workset identity, read-only default, denied hidden-tool calls, expiry and revocation, origin/cross-tenant isolation, replay/idempotency, cancellation and cleanup. A successful tunnel GET or public Actions workflow is not proof of an admitted ChatGPT tool connector. The existing Pandora denial and SMAC original-binary hold remain unchanged.

All model outputs are **ADVISORY_NOT_RUNTIME_EVIDENCE**, cannot authorize write/manipulation, and must be challenged by independent deterministic evidence before any publication or acceptance. Do not copy private `ghidra-tools` code into public jobs.
