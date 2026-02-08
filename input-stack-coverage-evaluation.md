# Input Stack Coverage Evaluation Pack (Keyboard + Mouse)
**Purpose:** Give this file to an engineering agent so they can evaluate whether an input capture/trace stack fully covers the range of **keyboard and mouse** inputs and edge cases, and can log them losslessly in a canonical event stream (e.g., JSONL).

This is written to be OS/backend-agnostic and applies to:
- Linux X11 (including Xvfb), Wayland (where feasible)
- Windows (Win32 message loop + Raw Input)
- Wine / containerized GUI automation harnesses
- Remote desktops (VNC/noVNC/RDP) where inputs may be synthesized

---

## 0) What the agent should deliver
The agent must produce a **Coverage Report** with:
1. **Inventory:** Which layers/backends are used (e.g., XInput2, XRecord, evdev, Win32 hooks, Raw Input).
2. **Capability table:** Which input categories are captured, derived, and logged; and what is missing.
3. **Schema compliance:** Evidence that the log schema can represent all inputs without information loss.
4. **Test results:** A reproducible test matrix with outputs and pass/fail status.
5. **Gap plan:** Concrete fixes (code pointers, config changes, or limitations explicitly documented).

---

## 1) Canonical event model requirements
### 1.1 Core principle
**Lossless first, interpretation second.**
Even if the system does not yet derive high-level gestures, it must be able to **record enough raw detail** to derive them later.

### 1.2 Minimum required fields (every event)
All logged events (JSONL recommended) must include:

- `session_id` (string)
- `seq` (int, strictly increasing)
- `event_id` (string or int, unique within session)
- `t_wall_ms` (int) and `t_mono_ms` (int)
- `type` (enum string; see below)
- `modifiers` (set/array: `shift`, `ctrl`, `alt`, `meta`, plus `altgr` if applicable)
- `device` (object or null; best-effort)
  - `id`, `name`, `type` (mouse/touchpad/keyboard/virtual)
- `context` (object or null; best-effort)
  - `focused_window_id`, `window_under_cursor_id`
  - `window_title`, `window_class`, `pid` if available
- `raw` (object): backend-specific raw codes and metadata for debugging

### 1.3 Recommended fields (strongly preferred)
- `buttons_down` (array of normalized button names at event time)
- Pointer position representation:
  - `x`, `y` (root/screen coords)
  - `x_win`, `y_win` (window-relative if available)
  - `coord_space` (e.g., `root`, `window`)
- Keyboard key identity:
  - `keycode` (hardware/scancode or OS-specific code)
  - `keysym` / virtual key (`vk`) where relevant
  - `text` (unicode string produced, if any)
  - `is_repeat` (bool)
  - `layout` / `ime` metadata in session `meta.json` (best-effort)

---

## 2) Input taxonomy to verify coverage
The agent must map the current implementation to this taxonomy and confirm:
- **Captured:** raw input recorded
- **Representable:** schema can store it
- **Derivable:** higher-level behavior can be derived (optional but preferred)
- **Tested:** reproducible test exists and passes

Use these categories.

---

## 3) Mouse / pointer coverage checklist
### 3.1 Pointer motion
- [ ] Absolute motion (`x,y`)
- [ ] Relative motion (`dx,dy`) if backend supports
- [ ] Motion coalescing/sampling behavior documented
- [ ] Motion while button pressed (critical for drag detection) recorded at full fidelity or with safe coalescing rules

### 3.2 Buttons (press/release)
Must capture **press** and **release** for:
- [ ] Left
- [ ] Right
- [ ] Middle
- [ ] Back (Mouse4)
- [ ] Forward (Mouse5)
- [ ] Extra buttons (Mouse6+), if available (at least representable in `raw`)

For each event:
- [ ] pointer position at time
- [ ] modifiers at time
- [ ] window context at time (best-effort)
- [ ] device identity (best-effort)

### 3.3 Scroll
- [ ] Vertical scroll
- [ ] Horizontal scroll
- [ ] Discrete wheel ticks
- [ ] Smooth/continuous scroll (touchpad) representable (float delta + units)
- [ ] Optional: inertial scroll representable (flag)

Recommended canonical representation:
`scroll: { axis: "vertical"|"horizontal", delta: number, units: "tick"|"pixel"|"unknown" }`

### 3.4 Multi-button and chorded mouse actions
- [ ] Left+Right down simultaneously (some apps use it)
- [ ] Middle button drag (pan in CAD/maps)
- [ ] Back/Forward with modifiers (browser nav + selection combos)
- [ ] Buttons_down snapshot present or reconstructable

### 3.5 Target/context enrichment
- [ ] focused window id
- [ ] window under cursor id
- [ ] title/class (best-effort)
- [ ] handle focus changes during drags/clicks

### 3.6 Derived pointer gestures (optional but preferred)
Derived from down/up/motion + thresholds:
- [ ] Click (down+up within time and slop distance)
- [ ] Double-click / Triple-click
- [ ] DragStart / DragMove / DragEnd
- [ ] Drag-and-drop (drop target differs; best-effort)
- [ ] HoverStart / HoverEnd (dwell threshold)

Edge case requirements:
- [ ] tiny jitter should not become drag
- [ ] drag threshold crossing should be detectable even if motion is sampled
- [ ] missing ButtonUp (focus loss / disconnect) should create a `GestureCancel` or `TracerState` event

---

## 4) Keyboard coverage checklist
### 4.1 Key down / key up
Must capture:
- [ ] KeyDown
- [ ] KeyUp
- [ ] Repeat behavior (hardware/OS repeat) as either repeated KeyDown with `is_repeat=true` or a separate Repeat event
- [ ] Timestamping and ordering guarantees under load

### 4.2 Modifier keys
Modifiers must be tracked and logged for every event:
- [ ] Shift (left/right if possible)
- [ ] Ctrl (left/right if possible)
- [ ] Alt (left/right if possible)
- [ ] Meta/Super (left/right if possible)
- [ ] AltGr (ISO_Level3_Shift / RightAlt on many layouts)
- [ ] CapsLock, NumLock, ScrollLock state (representable; session metadata acceptable)

### 4.3 Text input vs physical keys
Keyboard has two distinct layers that must both be representable:
1. **Physical key identity** (what key was pressed)
2. **Text output** (what character(s) were produced)

Coverage requirements:
- [ ] Key identity recorded (keycode/scancode + keysym/vk)
- [ ] Text produced recorded when applicable (`text` field, unicode)
- [ ] Dead keys (e.g., accent composition) representable
- [ ] Compose key sequences representable (Linux)
- [ ] IME input representable (CJK / candidate selection) — at minimum explicitly documented if out-of-scope

If IME is out-of-scope, the system must still:
- [ ] not crash or mis-log (store raw events + note limitation)
- [ ] store layout/IME status in `meta.json` if feasible

### 4.4 Non-character keys
Must capture and represent:
- [ ] Function keys F1–F24
- [ ] Navigation keys: arrows, Home/End, PgUp/PgDn, Insert/Delete
- [ ] Escape, Tab, Enter/Return, Backspace, Space
- [ ] PrintScreen, Pause/Break
- [ ] Media keys (Play/Pause, Next/Prev, Volume Up/Down/Mute) if available
- [ ] System keys (e.g., Menu key, Windows/Super, Application key)
- [ ] Numpad keys (distinct from top-row digits when possible)
- [ ] Keypad Enter vs Enter

### 4.5 Chords and shortcuts
Must correctly log timing and modifier state for:
- [ ] Ctrl+C / Ctrl+V etc.
- [ ] Alt+Tab (focus change mid-trace)
- [ ] Ctrl+Shift+Esc / Ctrl+Alt+Del equivalents (some may be intercepted by OS)
- [ ] Repeated shortcuts (key repeat while modifiers held)
- [ ] Stuck modifier resilience (missed KeyUp)

### 4.6 Multiple keyboards and virtual devices
- [ ] device identity per key event if backend supports
- [ ] distinguish physical vs synthetic (injected) events when feasible
- [ ] represent unknown device as `device:null` but keep raw source hints

---

## 5) Cross-cutting concerns (must evaluate)
### 5.1 Ordering and timing
- Events must have a strict `seq` ordering.
- `t_mono_ms` must be monotonic (never goes backward).
- Under heavy move/scroll volume, ensure button/key up/down are never dropped.

### 5.2 Sampling and loss
If pointer move events are sampled:
- Document sampling rate and algorithm.
- Ensure: while any button is down, sampling does not prevent drag detection (or preserve enough detail to detect threshold crossing).
- Provide a configuration knob to disable sampling for debugging.

### 5.3 Focus and window lifecycle
- Log focus changes explicitly if possible (`FocusChanged` events).
- Handle window destroyed/created mid-gesture without crashing.
- In remote desktop contexts, note where targeting info is unavailable.

### 5.4 Coordinate spaces and multi-monitor
- Document coordinate space (root vs window).
- Record display geometry in `meta.json`:
  - monitor count, resolutions, arrangement offsets
- Be robust to negative coordinates.

### 5.5 Accessibility / pointer settings (best-effort)
- Double-click time setting affects derivation.
- Pointer acceleration affects dx/dy interpretation.
At minimum: document if derivation uses fixed thresholds vs OS settings.

---

## 6) Canonical event types (recommended)
The agent should ensure the implementation can emit at least these:

### 6.1 Raw-ish
- `PointerMove`
- `ButtonDown`
- `ButtonUp`
- `Scroll`
- `KeyDown`
- `KeyUp`
- `TextInput` (optional but very useful)

### 6.2 Derived (optional but preferred)
- `Click`
- `DoubleClick`
- `TripleClick`
- `DragStart`
- `DragMove`
- `DragEnd`
- `HoverStart`
- `HoverEnd`
- `FocusChanged`
- `GestureCancel`
- `TracerState` (startup/shutdown/backend reconnect)

---

## 7) Test matrix (must be reproducible)
The agent must implement or verify tests that generate known input sequences and assert expected logs.

### 7.1 Mouse test cases
1. Left click
2. Right click
3. Middle click
4. Double click
5. Triple click
6. Ctrl+Left click
7. Shift+Left click
8. Alt+Left click
9. Meta+Left click
10. Back/Forward buttons (if available)
11. Drag 200px
12. Press+2px move+release (must be Click, not Drag)
13. Drag with Shift held
14. Drag with Ctrl held
15. Drag then focus change then release (must end or cancel deterministically)
16. Vertical scroll ticks (3 notches)
17. Horizontal scroll (if feasible)
18. Smooth scroll burst (touchpad-like) OR at least schema supports float delta
19. Hover (stop moving 700ms) if hover is derived
20. Move across windows; verify `window_under_cursor` changes

### 7.2 Keyboard test cases
1. Simple key: `a` (KeyDown/KeyUp + TextInput "a")
2. Shift+key: `A`
3. Ctrl+key: Ctrl+C
4. Alt+key: Alt+F (or Alt+Enter)
5. Meta+key: Super+R (if OS allows)
6. Key repeat: hold `a` for 1s
7. Navigation keys: Left/Right/Up/Down
8. Function keys: F1, F12
9. Numpad digit vs top-row digit (distinct if possible)
10. Dead key sequence (e.g., `´` then `e` => `é`) if supported by environment
11. Compose sequence (Linux) if supported
12. AltGr sequence (German layout common): AltGr+Q => `@`
13. CapsLock toggle state reflected
14. Stuck modifier simulation (drop a KeyUp) -> system logs consistent state and/or emits TracerState warning

### 7.3 Integration environment requirements
Provide at least one integration harness:
- X11/Xvfb: start Xvfb + lightweight X app, run tracer, inject events via XTest/xdotool, then validate JSONL.
- Windows: run tracer + SendInput injection (if within scope), validate.

The agent should include:
- A single script that runs all integration tests and stores artifacts under `artifacts/<timestamp>/`.

---

## 8) Evaluation procedure (step-by-step)
The agent should follow this procedure and report results:

1. **Identify capture points**
   - Which backend(s) are used? (e.g., XInput2, XRecord, evdev, Win32 hooks, Raw Input)
   - Are they capturing pre- or post-composition for keyboard text?

2. **Map implementation to taxonomy**
   - Create a table: category -> captured? representable? derived? tested?

3. **Schema audit**
   - Confirm schema can store:
     - multiple buttons
     - smooth scroll
     - physical key identity + text output
     - device identity when available
     - focus/window context when available
   - If not, propose schema changes.

4. **Threshold audit**
   - Document click slop radius, drag threshold, double-click time.
   - Confirm test coverage around thresholds.

5. **Run test matrix**
   - Produce logs and a summary (pass/fail).
   - Include samples of JSONL lines for each category.

6. **Stress test**
   - High-frequency pointer move + simultaneous clicks and scroll.
   - Confirm no dropped ButtonUp/KeyUp.

7. **Gap and remediation**
   - For each gap: propose a code-level plan and a test to prevent regressions.

---

## 9) Reporting template (agent should fill in)
### 9.1 Inventory
- OS:
- Display server:
- Input backend(s):
- Trace format:
- Derivation logic present? (yes/no)

### 9.2 Coverage table (example headings)
| Category | Captured | Representable | Derived | Tested | Notes/Gaps |
|---|---:|---:|---:|---:|---|
| PointerMove | | | | | |
| ButtonDown/Up (Left/Right/Middle) | | | | | |
| Back/Forward | | | | | |
| Scroll vertical/horizontal | | | | | |
| Smooth scroll | | | | | |
| KeyDown/KeyUp | | | | | |
| TextInput (unicode) | | | | | |
| Dead keys / Compose / AltGr | | | | | |

### 9.3 Artifact list
- trace.jsonl:
- trace.log:
- meta.json:
- test script output:

### 9.4 Gaps
- Gap #1:
  - Evidence:
  - Impact:
  - Fix:
  - New test:

---

## 10) Notes for Xvfb/Wine-style stacks (common pitfalls)
If your environment is X11/Xvfb and/or Wine:
- Xvfb may not expose the same device richness as a physical X server.
- Some “extra buttons” may not exist in synthetic injection tools.
- IME-level text composition is often not observable via low-level hooks.
- Motion coalescing can break drag threshold detection if applied while button is down.

The agent should explicitly state which limitations are due to environment vs implementation.

---

## 11) Definition of “Full range” for acceptance
A stack is considered “full range” for keyboard+mouse if:
- It **captures and logs losslessly**: down/up/move/scroll + modifier state + key identity, with ordering and timestamps.
- It can represent both **physical key identity** and **text output** (or explicitly documents and tests limitations).
- It handles multi-button, smooth scroll (at least representable), and common modifier combinations.
- It passes the test matrix and includes at least one integration harness.
- Any out-of-scope areas (IME, multitouch gestures, pen pressure) are explicitly documented and do not cause crashes or silent mis-logging.

---

## Appendix A: Example JSONL snippets (illustrative)
### A1) ButtonDown
```json
{"session_id":"s1","seq":12,"event_id":"e12","t_wall_ms":1739000000000,"t_mono_ms":12345,"type":"ButtonDown","x":640,"y":380,"button":"left","modifiers":["ctrl"],"buttons_down":["left"],"context":{"focused_window_id":"0x3a00007","window_under_cursor_id":"0x3a00007","window_title":"App","window_class":"AppClass"},"device":{"id":"d1","name":"Logitech","type":"mouse"},"raw":{"backend":"xinput2","detail":1}}
```

### A2) TextInput
```json
{"session_id":"s1","seq":44,"event_id":"e44","t_wall_ms":1739000000100,"t_mono_ms":12410,"type":"TextInput","text":"@","modifiers":["altgr"],"context":{"focused_window_id":"0x3a00007"},"raw":{"backend":"xkb","keysym":"at"}}
```

(These are examples only; your actual schema may differ.)

---

## Appendix B: If the agent needs to extend scope later
Optional future areas (not required for “full range” mouse+keyboard):
- multitouch gestures (pinch/zoom)
- pen pressure/tilt
- gamepad/joystick
- HID consumer controls beyond media keys
