# Input Pipeline Conformance Policy

This policy defines mandatory input correctness behavior for mouse and keyboard events across the full WineBot pipeline:

`Browser/noVNC -> websockify -> x11vnc/X11 -> Wine -> focused app`

It also defines human/agent control arbitration requirements and UI occlusion constraints.

## Scope

In scope:
- Mouse gestures and keyboard input delivery.
- Input trace consistency between client/X11/Windows layers.
- Human and agent control dynamics.
- Dashboard/UI interaction surfaces that can block or distort input.

Out of scope:
- Application-specific behavior inside a target Windows app beyond input arrival/observability.

## Normative Requirements

### R1. End-to-End Delivery

- Mouse and keyboard inputs MUST arrive at the currently focused Wine window.
- Input delivery MUST preserve button, key, and modifier semantics (`Ctrl`, `Alt`, `Shift`, `Meta`).
- Coordinate mapping MUST be deterministic for both 1:1 and scaled viewport modes.

### R2. Gesture Semantics

- System MUST distinguish at least:
  - `mouse_down`, `mouse_up`, `move`
  - `click` vs `drag`
  - `double_click` timing windows
  - `wheel` (vertical; horizontal when available)
- A `click` MUST be classified only when:
  - same button down/up,
  - movement under threshold,
  - duration under threshold.
- Missing terminal events (for example lost `mouse_up`) MUST trigger recovery to avoid stuck-button state.

### R3. Keyboard Semantics

- Keydown/keyup pairs MUST be observable in trace logs for focused interactions.
- Modifier combos (`Ctrl+Key`, `Alt+Key`, `Shift+Key`) MUST retain ordering and state.
- Keyboard input SHOULD be ignored when focus is inside dashboard text fields unless explicitly targeting VNC canvas.

### R4. Human Priority and Agent Arbitration

- Human input MUST preempt agent control in interactive sessions.
- Agent control MUST require explicit grant and MUST be revocable by:
  - user input activity,
  - `STOP_NOW`,
  - lease expiration.
- Agent MUST NOT acquire control without explicit user authorization.
- Effective control mode MUST be visible in UI when agent is in control.

### R5. No Unintended UI Occlusion

- Non-interactive overlays above the VNC canvas MUST use `pointer-events: none`.
- Interactive controls MAY overlay the canvas only within explicit control regions.
- Critical input regions (canvas interior excluding explicit controls) MUST remain hit-test reachable.
- Dashboard regressions that cause click swallowing MUST fail conformance tests.

### R6. Observability and Diagnostics

- For mouse down/up logs, messages MUST include button and modifier state.
- Input traces MUST support at least client and X11 layers; Windows/network traces SHOULD be available when enabled.
- Diagnostic output MUST include enough data to localize drops:
  - client coords,
  - mapped VNC/X11 coords,
  - event type/button/modifiers,
  - timestamp.

## Conformance Gates

A release candidate is conformant only if:

- Required unit/integration/e2e suites pass.
- No known P1 input regression is open for:
  - click delivery,
  - drag semantics,
  - keyboard modifier combos,
  - human priority arbitration,
  - UI occlusion.

## Failure Classification

- `P0`: Human cannot control session (widespread click/keyboard failure).
- `P1`: Arbitration breach, stuck-button state, or major gesture misclassification.
- `P2`: Reduced fidelity (for example scaled-coordinate drift with workaround).
- `P3`: Logging/diagnostic incompleteness with no immediate functional loss.
