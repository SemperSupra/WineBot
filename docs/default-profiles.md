# Default Profiles

WineBot provides named default profiles so operators and agents can start with safe, understandable settings instead of manually setting individual variables.

## Start Commands

List profiles:

`./scripts/wb profile list`

Start a profile:

`./scripts/wb profile up <name> [--build] [--detach]`

Persist profile settings in runtime config:

`scripts/winebotctl config profile set <name>`

Validate current config:

`scripts/winebotctl config validate`

## Profile Definitions

| Profile | Runtime | Instance lifecycle | Session lifecycle | Instance control | Session control | Use case |
| :--- | :--- | :--- | :--- | :--- | :--- | :--- |
| `human-desktop` | `interactive` | `persistent` | `persistent` | `human-only` | `human-only` | Human-operated desktop with no agent takeover. |
| `assisted-desktop` | `interactive` | `persistent` | `persistent` | `hybrid` | `hybrid` | Human first, agent assists via explicit grants. |
| `unattended-runner` | `headless` | `persistent` | `persistent` | `agent-only` | `agent-only` | Continuous unattended automation. |
| `ci-oneshot` | `headless` | `oneshot` | `oneshot` | `agent-only` | `agent-only` | One-shot CI jobs that exit automatically. |
| `support-session` | `interactive` | `persistent` | `oneshot` | `hybrid` | `hybrid` | Temporary interactive support workflows. |

## Admission Guard Rules

WineBot rejects invalid or contradictory combinations at startup and API admission points.

Blocked by default:

- `MODE=headless` with effective control mode `human-only`
- `MODE=headless` with effective control mode `hybrid` (unless `WINEBOT_ALLOW_HEADLESS_HYBRID=1`)
- `BUILD_INTENT=rel-runner` with `MODE=interactive`

Allowed with explicit override:

- `MODE=headless` + effective `hybrid` when `WINEBOT_ALLOW_HEADLESS_HYBRID=1`

The effective control mode is resolved as:

- `human-only` if either instance/session is `human-only`
- else `agent-only` if either instance/session is `agent-only`
- else `hybrid`
