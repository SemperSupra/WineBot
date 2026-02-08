# WineBot Interactive Session Control & Agent Control API Compatibility

## Purpose

Extend WineBot’s interaction strategy to enforce a strict policy during **interactive sessions**:

- **Agents/automation MUST NOT take control from a user.**
- **Users MAY:**
  1. **Wait** (let the agent continue),
  2. **Interrupt safely** (pause/handshake at a safe point),
  3. **Immediately stop** the agent and take control.

Additionally, evaluate existing automation programs installed in WineBot and determine how they can be made **compatible with the Agent Control API** (i.e., routed through the broker rather than injecting input directly).

This document is intended to be handed to an implementation agent.

---

## Definitions

### Interactive Session
A session is **interactive** if a human is attached (VNC/noVNC/local viewer) OR if explicitly flagged interactive by the session manager.

- `interactive=true`: enforce the strict non-preemption policy.
- `interactive=false`: automation can run without user arbitration (headless batch use).

### Control Modes
- `USER`: user has control.
- `AGENT`: agent has control (only if user granted/leased it).

### User Intent States
During interactive sessions, user intent determines how agent execution proceeds:

- `WAIT`: user allows agent to continue.
- `SAFE_INTERRUPT`: user requests a cooperative pause at a safe point.
- `STOP_NOW`: user immediately stops agent and takes control.

---

## Policy Requirements (Interactive Sessions)

### P0. Non-Preemption
In `interactive=true` sessions:
- The agent **cannot** switch the session from `USER` to `AGENT` by itself.
- The agent may only operate in `AGENT` mode if the **user has explicitly granted** control.

### P1. User Always Wins
- Any user input (mouse/keyboard) **revokes agent control immediately** and switches to `USER`.
- This must be true even if an agent lease is active.

### P2. User-Control Options
Users must have three explicit choices:

1. **WAIT**
   - User does nothing; agent continues if it currently holds a valid lease.

2. **SAFE_INTERRUPT**
   - User requests a cooperative pause.
   - Agent must stop at the next safe point.
   - Control returns to `USER` after pause.

3. **STOP_NOW**
   - Immediate hard stop of automation.
   - Agent lease revoked instantly.
   - Input queue cleared.
   - Control returns to `USER` immediately.

### P3. Only Necessary During Interactive
In `interactive=false` sessions:
- The broker may allow agent acquisition by default (or via policy), since no human is attached.

---

## Control API Extensions

### Control State Model

```json
{
  "session_id": "uuid",
  "interactive": true,
  "control_mode": "USER | AGENT",
  "lease_expiry": "timestamp | null",
  "user_intent": "WAIT | SAFE_INTERRUPT | STOP_NOW",
  "agent_status": "IDLE | RUNNING | PAUSED | STOPPING | STOPPED"
}
```

### User-Facing Control Endpoints

#### Set User Intent
```
POST /sessions/{id}/user_intent
```

Payload examples:
```json
{ "intent": "WAIT" }
```
```json
{ "intent": "SAFE_INTERRUPT" }
```
```json
{ "intent": "STOP_NOW" }
```

Rules:
- `STOP_NOW` triggers an immediate stop and returns mode to `USER`.
- `SAFE_INTERRUPT` triggers a cooperative pause at a safe point.
- `WAIT` clears any pending interrupt requests.

#### Grant Agent Control (User Action)
```
POST /sessions/{id}/control/grant
```

Payload:
```json
{ "lease_seconds": 30 }
```

Rules:
- Only valid when `interactive=true`.
- Sets `control_mode=AGENT`.
- Agent cannot call this endpoint autonomously.

#### Agent Lease Renewal
```
POST /sessions/{id}/control/renew
```

Rules:
- Only valid if agent already holds control and no user override is pending.

---

## Input Broker Enforcement Logic

### Core Rules
1. If `interactive=true` and `control_mode=USER`, drop agent input.
2. User input always revokes agent control.
3. `STOP_NOW` immediately halts agent activity.
4. `SAFE_INTERRUPT` pauses at the next safe point.

### Pseudo-Code
```python
def on_user_event(ev):
    revoke_agent_lease()
    clear_agent_queue()
    signal_agent_stop(reason="user_input_override")
    set_mode(USER)
    inject(ev)

def on_agent_event(ev):
    if interactive and mode != AGENT:
        drop(ev)
        return
    if lease_expired() or user_intent == "STOP_NOW":
        drop(ev)
        return
    inject(ev)
```

---

## Safe Interrupt Semantics

A safe point is a boundary between discrete automation steps.

Examples:
- After a click completes
- After a window focus change
- After a UI idle wait
- Between macro steps

### Safe Point API
```
POST /sessions/{id}/agent/safe_point
```

Payload:
```json
{ "step": "click_ok_button", "sequence": 42 }
```

Broker response:
```json
{ "action": "CONTINUE | PAUSE | STOP" }
```

Agent must obey broker decisions.

---

## STOP_NOW Semantics

When invoked:
- Revoke lease immediately
- Block all agent input
- Clear queues
- Terminate or cancel automation
- Return control to user instantly

---

## Interactive Session Detection

A session is interactive if:
- VNC/noVNC client is connected
- Local viewer attached
- Explicit `--interactive` flag set

Viewer connection should be treated as authoritative by default.

---

## Automation Program Compatibility Audit

All installed automation tools must be reviewed.

Create `docs/AUTOMATION_COMPAT.md` with:

| Tool | Input Path | Risk | Compatibility | Adapter Plan | STOP_NOW | SAFE_INTERRUPT |
|------|------------|------|---------------|--------------|----------|----------------|

Rules:
- No direct X injection in interactive sessions
- All automation must route through the broker

Adapter approaches:
- CLI wrappers
- PATH shadowing
- Step-based runner with cancellation tokens

---

## Logging & Observability

Log all:
- Control changes
- User intent updates
- Overrides
- Stops and pauses
- Safe point decisions

Format: JSON lines with session_id and timestamps.

---

## Testing Requirements

### Unit Tests
- Agent cannot preempt user
- STOP_NOW revokes control immediately
- SAFE_INTERRUPT pauses at safe points

### Integration Tests
- Interactive session + VNC + agent without grant → denied
- User input interrupts agent instantly
- SAFE_INTERRUPT pauses cleanly
- STOP_NOW halts automation

### Invariants
- Agent never takes control from user
- User can always reclaim control instantly
- No agent input without valid grant

---

## Summary

In interactive WineBot sessions:

- Users are always in control.
- Agents operate only with explicit user consent.
- Users can wait, safely interrupt, or immediately stop automation.
- All automation must be brokered, auditable, and revocable.
