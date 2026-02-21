# Internal Versioning Strategy

This document defines the versioning strategy for WineBot's internal APIs, protocols, and data artifacts to ensure operational correctness during incremental changes.

## 1. Versioned Artifacts

| Artifact | Version Key | Verification | Fail-Fast Policy |
| :--- | :--- | :--- | :--- |
| **HTTP API** | `X-WineBot-API-Version` | Handshake / Negotiate | **High**. Rejects incompatible agents. |
| **Session Manifest** | `schema_version` | Load-time check | **Medium**. Warns if parsing old data. |
| **Event Logs** | `schema_version` | Stream-time check | **Low**. Backfills missing fields. |
| **Discovery** | `version` | TXT Record check | **High**. Hub ignores old nodes. |
| **Configuration** | `WINEBOT_CONFIG_VERSION`| Startup check | **Critical**. Refuses to boot on stale config. |

---

## 2. Implementation Recommendations

### A. API Handshake (Implement)
**Goal**: Prevent automated agents from using an API they don't understand.
- **Action**: Add a `/handshake` endpoint that returns supported versions.
- **Enforcement**: If an agent specifies an `X-WineBot-Min-Version` header higher than the server supports, return `426 Upgrade Required`.

### B. Strict Manifest Validation (Implement)
**Goal**: Prevent data corruption when resuming sessions from a different WineBot version.
- **Action**: Update `resume_session` to verify that the `session.json` version matches the current build's expectation.
- **Fail-Fast**: If major versions differ, refuse to resume without an explicit `--force-resume` flag.

### C. Discovery version Guard (Implement)
**Goal**: Prevent the multi-node hub from crashing when aggregating data from mixed-version clusters.
- **Action**: Discovery TXT records now include both `version` (WineBot Build) and `schema_version` (Metadata Format).

---

## 3. Implementation Strategy

1. **Phase 1: API Negotiation**: Implement `/handshake` and header-based version guarding.
2. **Phase 2: Resumption Guard**: Harder `resume_session` logic to check `schema_version`.
3. **Phase 3: Formalize Config Version**: Add `WINEBOT_CONFIG_SCHEMA_VERSION` to `winebot.env`.

**How would you like to proceed?**
- **Option 1: Implement Phase 1 & 2 now.**
- **Option 2: Open a feature issue for the full strategy.**
- **Option 3: Ignore.**
