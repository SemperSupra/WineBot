# Input Pipeline Tracing

WineBot records structured JSONL trace events across five layers, enabling
end-to-end observability of input delivery from client to Windows application.

## Trace Layers

| Layer | Source | Log File | What It Captures |
|:---|:---|:---|:---|
| **X11** | XI2 (XInput2) events | `logs/input_events.jsonl` | Raw X11 input events: button press/release, key press/release, motion |
| **X11 Core** | `xinput test` device output | `logs/input_events_x11_core.jsonl` | Low-level X11 device events (master + XTEST) |
| **Windows** | AHK hooks or `diagnose-wine-hook.py` | `logs/input_events_windows.jsonl` | Windows-side events: mouse_down/up/move, key_down/up, focus/queue state |
| **Client** | noVNC canvas JavaScript | `logs/input_events_client.jsonl` | Browser-side events: mouseup/down, key events with client/VNC coordinates |
| **Network** | VNC proxy listener | `logs/input_events_network.jsonl` | Raw VNC RFB protocol events: pointer, key, with button masks |

## Enabling Trace Layers

Traces are controlled via environment variables and API endpoints:

| Layer | Env Var | API Start | API Stop |
|:---|:---|:---|:---|
| X11 | `WINEBOT_INPUT_TRACE=1` | `POST /input/trace/start` | `POST /input/trace/stop` |
| X11 Core | -- | `POST /input/trace/x11core/start` | `POST /input/trace/x11core/stop` |
| Windows | `WINEBOT_INPUT_TRACE_WINDOWS=1` | `POST /input/trace/windows/start` | `POST /input/trace/windows/stop` |
| Client | -- | `POST /input/trace/client/start` | `POST /input/trace/client/stop` |
| Network | `WINEBOT_INPUT_TRACE_NETWORK=1` | `POST /input/trace/network/start` | `POST /input/trace/network/stop` |

Query trace events: `GET /input/events?limit=200&source=windows&origin=agent`

## Trace Event Schema

Every event contains these common fields:

| Field | Type | Description |
|:---|:---|:---|
| `event` | string | Event type (e.g., `button_press`, `key_down`, `agent_key`) |
| `timestamp_epoch_ms` | int | Unix epoch milliseconds |
| `timestamp_utc` | string | ISO 8601 UTC timestamp |
| `source` | string | Trace layer: `x11`, `windows`, `client`, `network`, `api` |
| `layer` | string | Same as source (canonical field for cross-layer queries) |
| `origin` | string | `agent` or `user` |
| `tool` | string | Tool that generated the event: `xinput`, `ahk`, `novnc`, `api:/input/key` |
| `session_id` | string | Active session ID |
| `trace_id` | string | UUID hex — **matches events across layers for the same input action** |

### Mouse Events

| Event | Layer | Extra Fields |
|:---|:---|:---|
| `button_press` | X11, X11 Core | `button` (1-3), `x`, `y` |
| `button_release` | X11, X11 Core | `button` (1-3), `x`, `y` |
| `motion` | X11, X11 Core | `x`, `y` |
| `mouse_down` | Windows | `button` ("left"/"right"/"middle"), `x`, `y`, `trace_id` |
| `mouse_up` | Windows | `button` ("left"/"right"/"middle"), `x`, `y`, `trace_id` |
| `mouse_move` | Windows | `x`, `y`, `trace_id` |
| `mouse_wheel` | Windows | `delta`, `trace_id` |
| `client_mouse_down` | Client | `client_x`, `client_y`, `vnc_x`, `vnc_y`, `button` |
| `client_mouse_up` | Client | `client_x`, `client_y`, `vnc_x`, `vnc_y`, `button` |
| `vnc_pointer` | Network | `x`, `y`, `button_mask` (bitmask: 1=left, 2=middle, 4=right, 8=scroll-up, 16=scroll-down) |
| `mousedown` | Windows (AHK) | `button` ("left"/"right"/"middle"), `x`, `y` |

### Keyboard Events

| Event | Layer | Extra Fields |
|:---|:---|:---|
| `key_press` | X11, X11 Core | `keycode`, `keysym`, `modifiers` |
| `key_release` | X11, X11 Core | `keycode`, `keysym`, `modifiers` |
| `key_down` | Windows | `vk` (virtual key code), `keys` (string if available), `trace_id` |
| `key_up` | Windows | `vk`, `keys`, `trace_id` |
| `client_key_down` | Client | `key`, `code`, `ctrl`, `alt`, `shift`, `meta` |
| `client_key_up` | Client | `key`, `code`, `ctrl`, `alt`, `shift`, `meta` |
| `vnc_key` | Network | `keysym`, `down` (bool) |

### API Events (from `/input/key`)

| Event | Phase | Extra Fields |
|:---|:---|:---|
| `agent_key` | `request` | `keys`, `via` (backend name: "ahk"/"xdotool"), `trace_id`, `target_window_id`, `target_window_title` |
| `agent_key` | `complete` | `keys`, `status` ("sent"), `trace_id`, `backend` |

API keyboard events also write a cross-layer `key_sent` event to the Windows log:
```json
{"event": "key_sent", "origin": "agent", "source": "windows",
 "keys": "Hello", "trace_id": "...", "backend": "ahk",
 "timestamp_epoch_ms": 1719000000000}
```

## Cross-Layer Event Correlation

Events from the same input action share a `trace_id`. To trace a keystroke end-to-end:

```bash
# 1. Query API input events
curl -H "X-API-Key: $TOKEN" "$API/input/events?source=&origin=agent&limit=50"

# 2. Find the agent_key event with trace_id
# 3. Query Windows layer for matching trace_id
curl -H "X-API-Key: $TOKEN" "$API/input/events?source=windows&limit=200"

# Or use the latency analysis tool:
python3 scripts/diagnostics/analyze-trace-latency.py --mode keyboard
```

The `analyze-trace-latency.py` tool automates this correlation:
- **Mouse mode** (`--mode mouse`): Matches Network → X11 → Windows for VNC-injected mouse clicks
- **Keyboard mode** (`--mode keyboard`): Matches API input events → Windows trace for API-injected keystrokes

## Diagnostic Tools

| Tool | Purpose |
|:---|:---|
| `scripts/diagnostics/diagnose-input-suite.sh` | End-to-end mouse/keyboard validation across Notepad, Regedit, Winefile using CV and visual diff |
| `scripts/diagnostics/diagnose-input-trace.sh` | 5-layer trace bisect: starts all trace layers, injects mouse/keyboard, validates each layer |
| `scripts/diagnostics/analyze-trace-latency.py` | Cross-layer latency analysis (mouse and keyboard modes) |
| `scripts/diagnostics/diagnose-master.sh` | Full system diagnostic including fault injection |

## Integration with Recording

When recording is enabled with `WINEBOT_RECORDING_INCLUDE_INPUT_TRACES=1`,
trace events are embedded as subtitle tracks in the recording. The
`WINEBOT_RECORDING_REDACT_FIELDS` setting controls which trace fields
are redacted (defaults to `key,keycode,text,raw,password,token,secret,clipboard`).
