# Default Profiles

WineBot provides named startup profiles so operators and agents can select a use case directly instead of manually composing control, lifecycle, and performance flags.

## Start Commands

List profiles:

`./scripts/wb profile list`

Start a use-case profile (default performance for that use case):

`./scripts/wb profile up <use-case> [--build] [--detach]`

Start a use-case profile with explicit performance profile:

`./scripts/wb profile up <use-case> --performance <name> [--build] [--detach]`

Persist profile settings in runtime config:

`scripts/winebotctl config profile set <use-case> [--performance <name>]`

Validate current config:

`scripts/winebotctl config validate`

## Use-Case Profiles

| Use-case profile | Runtime | Instance lifecycle | Session lifecycle | Instance control | Session control | Default performance | Purpose |
| :--- | :--- | :--- | :--- | :--- | :--- | :--- | :--- |
| `human-interactive` | `interactive` | `persistent` | `persistent` | `human-only` | `human-only` | `low-latency` | Primary human desktop interaction. |
| `human-exploratory` | `interactive` | `persistent` | `persistent` | `human-only` | `human-only` | `balanced` | Human exploratory testing with moderate telemetry. |
| `human-debug-input` | `interactive` | `persistent` | `persistent` | `human-only` | `human-only` | `diagnostic` | Human-led input debugging and tracing. |
| `agent-batch` | `headless` | `persistent` | `persistent` | `agent-only` | `agent-only` | `balanced` | Continuous unattended automation. |
| `agent-timing-critical` | `headless` | `persistent` | `persistent` | `agent-only` | `agent-only` | `low-latency` | Throughput/latency-sensitive automation. |
| `agent-forensic` | `headless` | `persistent` | `persistent` | `agent-only` | `agent-only` | `diagnostic` | Deep capture for audits and failures. |
| `supervised-agent` | `interactive` | `persistent` | `persistent` | `hybrid` | `hybrid` | `balanced` | Human supervises and can interrupt agent actions. |
| `incident-supervision` | `interactive` | `persistent` | `persistent` | `hybrid` | `hybrid` | `diagnostic` | Incident response with full telemetry. |
| `demo-training` | `interactive` | `persistent` | `persistent` | `hybrid` | `hybrid` | `max-quality` | Demonstrations/training with visual quality bias. |
| `ci-gate` | `headless` | `oneshot` | `oneshot` | `agent-only` | `agent-only` | `balanced` | One-shot CI readiness verification. |

Legacy aliases remain accepted:

- `human-desktop` -> `human-interactive`
- `assisted-desktop` -> `supervised-agent`
- `unattended-runner` -> `agent-batch`
- `ci-oneshot` -> `ci-gate`
- `support-session` -> `incident-supervision`

## Performance Profiles

| Performance profile | Recording | X11 trace | Windows trace | Network trace | Debug hooks | Purpose |
| :--- | :--- | :--- | :--- | :--- | :--- | :--- |
| `low-latency` | off | off | off | off | off | Minimize overhead for interactive responsiveness/throughput. |
| `balanced` | off | on | on | off | off | Default tradeoff between observability and responsiveness. |
| `max-quality` | on | on | on | on | off | Higher-fidelity capture for demos/visual review. |
| `diagnostic` | on | on | on | on | on | Maximum observability for debugging and incident triage. |

## Admission Guard Rules

WineBot rejects invalid or contradictory combinations at startup and API admission points.

Blocked by default:

- `MODE=headless` with effective control mode `human-only`
- `MODE=headless` with effective control mode `hybrid` (unless `WINEBOT_ALLOW_HEADLESS_HYBRID=1`)
- `BUILD_INTENT=rel-runner` with `MODE=interactive`
- invalid `WINEBOT_USE_CASE_PROFILE` names
- invalid `WINEBOT_PERFORMANCE_PROFILE` names
- use-case/performance combinations not allowed by policy (for example `ci-gate + diagnostic`)
- use-case profile selection that conflicts with explicit runtime/lifecycle/control values

Allowed with explicit override:

- `MODE=headless` + effective `hybrid` when `WINEBOT_ALLOW_HEADLESS_HYBRID=1`

The effective control mode is resolved as:

- `human-only` if either instance/session is `human-only`
- else `agent-only` if either instance/session is `agent-only`
- else `hybrid`
