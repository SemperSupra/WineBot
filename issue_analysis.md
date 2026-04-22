# WineBot Issue Analysis

Based on a review of the open issues, here is the analysis regarding which issues are still relevant, which can be automatically closed, and which should be combined or broken up.

## Still Relevant

The following issues are actively relevant and should remain open:
- #45: Invariant hardening (deferred): durable broker state + CAS transitions
- #43: Conformance: add OpenAPI property-based fuzz tests
- #42: Conformance: add DNS-SD/mDNS integration tests on real network
- #41: Recording Phase 2: Markerized Timeline and markers API
- #40: Recording Phase 5: Timeline-Correlated Playback and Diagnostic UX
- #35: Recorder: checkpointed finalization and recovery for interrupted long-running post-processing
- #34: Automation: detached job TTL, ownership binding, and cancellation controls
- #26: Correctness hardening: enable mypy untyped-body checks for discovery paths
- #25: Correctness hardening: explicit write-failure surfacing + atomic log cap under contention
- #23: [Correctness] Bound memory usage in /recording/perf/summary
- #15: Telemetry Phase 4: CI Baselines and Performance Regression Gates
- #14: Telemetry Phase 3: Runtime Telemetry Config + Summary/Regression APIs
- #13: Expand Human-Visible Agent-Control Indicators Beyond Dashboard
- #12: [Correctness] Formalize Configuration Schema Versioning
- #11: [Accessibility] Implement Automated A11y Audits for Dashboard
- #10: [Test] Implement Network Partition & Latency Simulation
- #9: [Feature] Implement Resource Quotas per App
- #8: [Feature] Implement Native Wine Event Pipe

## Can Be Closed

The following issue is no longer relevant and should be closed:
- #5: [Optimization] Investigate and Implement a Stripped Custom Wine Build (The body explicitly states this is deferred in favor of the more comprehensive Stage 2 Instrumented Wine Core Build, Issue #7. Therefore, Issue #5 can be closed to avoid tracking duplicate/superseded work).

## Should Be Combined

The following groups of issues cover heavily overlapping domains and should be combined into epic/tracking issues or single comprehensive PRs to reduce fragmentation:

- **Telemetry Coverage Consolidation**
  Combine #17 (Screenshot + Window Inspection Performance), #18 (API Auth and Token Path), #19 (Session Artifact I/O and Retention Costs), #20 (Interactive Stack), and #22 (Use context-local session attribution for process telemetry). These all represent piecemeal additions to the telemetry system. They should be rolled into a single "Comprehensive Telemetry Coverage Enhancements" tracking issue.

- **Resource Control Config Consolidation**
  Combine #31 (Resource control: residual backend timing constants configurable) and #32 (Resource control: make UI polling/backoff limits configurable). Both address making hardcoded timing/resource constraints configurable. They belong in a single "Make all timing and polling constants configurable" issue.

- **State Correctness/Anomaly Detection Consolidation**
  Combine #28 (State correctness: add composed lifecycle transition-table invariant tests) and #29 (State correctness: unexpected-transition telemetry and anomaly alerts). Both address enforcing and alerting on unexpected state transitions in the lifecycle. These form a single cohesive effort.

## Should Be Broken Up

The following issues are too broad and should be broken down into smaller, actionable tickets:

- #16: Telemetry Phase 5: Trend Dashboards and Optimization Workflow
  This encompasses several large, distinct tasks: building daily/weekly rollups, producing top regression reports, defining an export format, and documenting a new playbook. This should be split into smaller issues (e.g., "Implement telemetry data export format", "Create regression reporting job", "Document optimization playbook").

- #7: [Feature] Implement Stage 2: Instrumented Wine Core Build
  This requires deep C-level modifications to Wine (structured JSON logging, direct sync hooks, embedded tracing, and module stripping). This is an epic-level effort that should be broken down into separate tickets for each specific Wine subsystem modification.

- #46: Config/ops: migrate runtime state paths to XDG conventions with compatibility
  This touches multiple subsystems, requires careful backwards compatibility shims, update to docs, and testing across different operating systems. This should be broken into "Implement XDG path resolution", "Migrate existing state with backwards compatibility shims", and "Update CLI/Agent scripts to new paths".
