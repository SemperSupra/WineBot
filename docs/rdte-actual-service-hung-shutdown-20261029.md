# WineBot actual service shutdown timeout gate — 2026-10-29

Independent research branch from the qualified actual-service handover branch `5b3000219ab762d6d7cfc46ab233cf690157d1a7`. No API/core source change, no process spawn. The direct actual `ObserverService.shutdown` method is exercised with a deterministic hung-worker dependency and an actual fixed `EventBridge` in the shared registry.

Required behavior: explicit `False` after the bounded 4-second join contract when a worker remains alive (the worker stub returns without sleeping); no global erasure of a successor's event bridge; subsequent late completion reports `True` without erasure; a stopped service cannot restart even when worker recovers. Existing actual handover/source/registry tests run in the SAME scoped public GHA batch.

Important limitations: process-group kill, operating system or Wine orphan handling, actual cancellation latency and atomically admitted resource lease are **not** qualified by a synthetic worker. `False` is not a cleanup success; external owner must treat as failure/hold. Source custody/security #515, G0–G5, three-audience identity and production release gates remain unchanged. No merge/release.
