# Agent Autonomy & Accountability Policy

This document defines the operational boundaries and safety requirements for autonomous agents (LLMs, bots, CI scripts) interacting with the WineBot codebase and infrastructure.

## 1. The "Human-in-the-Loop" (HITL) Mandate

Agents must distinguish between **Standard Actions** and **High-Risk Actions**. High-risk actions require explicit human confirmation via the user interface or a command-line prompt.

### 1.1 Standard Actions (Autonomous)
- **Code Modification**: Refining logic, fixing bugs, and adding features within the repository.
- **Testing**: Running unit, integration, and E2E tests in ephemeral containers.
- **Documentation**: Updating Markdown files and generating reports.
- **Monitoring**: Observing logs and reporting health status.

### 1.2 High-Risk Actions (HITL Required)
- **Destructive File Operations**: Deleting or overwriting permanent session artifacts or the persistent Wine prefix.
- **Credential Management**: Accessing or modifying environment files containing secrets (e.g., `.env`, `API_TOKEN`).
- **Infrastructure Teardown**: Shutting down the API or stopping the container (unless part of a requested task).
- **Public Communication**: Opening public issues or PRs on behalf of the project (if enabled in the future).

## 2. Capability Transparency

Agents must accurately represent their capabilities and limitations. 
- If an agent identifies a task that exceeds its safety bounds (e.g., modifying host-level files), it **MUST** stop and ask for human intervention.
- Agents should provide a "Technical Rationale" for all major changes to maintain auditability.

## 3. Policy Adherence

All agent actions are governed by the established WineBot policies:
1. **Containerized Tooling Policy**: No host-level modifications.
2. **Interactive Control Policy**: Never preempt a human user.
3. **Dependency Pinning Policy**: No unverified or floating versions.

## 4. Failure Handling

When an agent encounters a system failure (e.g., a crash during testing):
- It **MUST** attempt a graceful recovery (e.g., using `scripts/wb ctl lifecycle reset_workspace`).
- It **MUST NOT** attempt to "hack around" safety guards (e.g., disabling the API token to bypass authentication).
- It **MUST** document the failure and the recovery steps taken.
