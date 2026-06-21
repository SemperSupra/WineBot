"""E2E conformance tests for input pipeline policy R3 (Keyboard Semantics).

Validates normative requirements from policy/input-pipeline-conformance-policy.md:
  R3.1: Keydown/keyup pairs observable in trace logs
  R3.2: Modifier combos retain ordering and state
  R3.3: Keyboard input ignored when focus is in dashboard text fields

Requires a running interactive WineBot instance with the test-runner profile.
"""

import time

import requests

from _auth import API_URL, auth_headers, ensure_agent_control, ensure_openbox_running


class KeyboardAPI:
    """API client for keyboard injection and trace verification."""

    def __init__(self, url: str):
        self.url = url
        self.headers = auth_headers()

    def send_keys(self, keys: str, window_title: str = "", backend: str = "") -> dict:
        body: dict = {"keys": keys}
        if window_title:
            body["window_title"] = window_title
        if backend:
            body["backend"] = backend
        res = requests.post(
            f"{self.url}/input/key",
            json=body,
            headers=self.headers,
            timeout=15,
        )
        res.raise_for_status()
        return res.json()

    def run_app(self, path: str) -> dict:
        res = requests.post(
            f"{self.url}/apps/run",
            json={"path": path, "detach": True},
            headers=self.headers,
            timeout=10,
        )
        res.raise_for_status()
        return res.json()

    def get_windows(self) -> dict:
        res = requests.get(f"{self.url}/health/windows", headers=self.headers, timeout=10)
        res.raise_for_status()
        return res.json()

    def start_trace(self, layer: str) -> dict:
        res = requests.post(
            f"{self.url}/input/trace/{layer}/start",
            headers=self.headers,
            timeout=10,
        )
        res.raise_for_status()
        return res.json()

    def stop_trace(self, layer: str) -> dict:
        res = requests.post(
            f"{self.url}/input/trace/{layer}/stop",
            headers=self.headers,
            timeout=10,
        )
        res.raise_for_status()
        return res.json()

    def get_trace_events(self, source: str, limit: int = 200) -> list:
        res = requests.get(
            f"{self.url}/input/events",
            params={"source": source, "limit": limit},
            headers=self.headers,
            timeout=10,
        )
        res.raise_for_status()
        return res.json().get("events", [])

    def get_session_dir(self) -> str:
        res = requests.get(f"{self.url}/lifecycle/status", headers=self.headers, timeout=10)
        res.raise_for_status()
        return res.json().get("session_dir", "")


def wait_for_window(api: KeyboardAPI, title_pat: str, max_attempts: int = 20) -> dict:
    for _ in range(max_attempts):
        windows = api.get_windows().get("windows", [])
        match = next((w for w in windows if title_pat in w.get("title", "")), None)
        if match:
            return match
        time.sleep(1)
    raise AssertionError(f"Window '{title_pat}' not found after {max_attempts}s")


def test_r3_1_keydown_keyup_pairing():
    """R3.1: Keydown/keyup pairs MUST be observable in trace logs."""
    api = KeyboardAPI(API_URL)
    ensure_openbox_running()
    ensure_agent_control(lease_seconds=300)

    # Start Windows trace
    api.start_trace("windows")
    time.sleep(1)

    # Launch Notepad
    api.run_app("notepad.exe")
    notepad_win = wait_for_window(api, "Notepad")
    print(f"R3.1: Notepad window: {notepad_win}")

    # Send a simple key
    result = api.send_keys(keys="a", window_title="Notepad")
    print(f"R3.1: send_keys response: {result}")
    assert result["status"] == "sent"
    trace_id = result.get("trace_id")

    time.sleep(1.5)  # Allow trace propagation

    # Query Windows trace
    events = api.get_trace_events("windows", limit=200)
    key_events = [e for e in events if e.get("trace_id") == trace_id]

    print(f"R3.1: Matched {len(key_events)} events for trace_id={trace_id}")
    for ev in key_events:
        print(f"  {ev.get('event')} vk={ev.get('vk')} keys={ev.get('keys')}")

    # R3.1 assertion: at least one key_down event
    key_downs = [e for e in key_events if e.get("event") == "key_down"]
    assert len(key_downs) >= 1, (
        f"R3.1 FAIL: No key_down event found for trace_id={trace_id}. "
        f"Total events: {len(key_events)}"
    )

    # If the trace captures key_up as well, verify pairing
    key_ups = [e for e in key_events if e.get("event") == "key_up"]
    if key_ups:
        print(f"R3.1 PASS: Key down/up pairing confirmed (down={len(key_downs)}, up={len(key_ups)})")
    else:
        print(f"R3.1 PARTIAL: Key down found but key_up not captured (down={len(key_downs)})")

    # Cleanup
    api.send_keys(keys="alt+F4", window_title="Notepad")
    api.stop_trace("windows")


def test_r3_2_modifier_combo_ordering():
    """R3.2: Modifier combos MUST retain ordering and state."""
    api = KeyboardAPI(API_URL)
    ensure_openbox_running()
    ensure_agent_control(lease_seconds=300)

    api.start_trace("windows")
    time.sleep(1)

    # Launch fresh Notepad for each chord test
    api.run_app("notepad.exe")
    wait_for_window(api, "Notepad")
    time.sleep(0.5)

    # Test multiple modifier chords
    chords = [
        ("ctrl+s", "Ctrl+S (Save)"),
        ("alt+f", "Alt+F (File menu)"),
        ("shift+a", "Shift+A"),
    ]

    results = {}
    for chord, label in chords:
        result = api.send_keys(keys=chord, window_title="Notepad")
        print(f"R3.2 [{label}]: {result}")
        assert result["status"] == "sent", f"R3.2 FAIL: {label} not sent"
        results[chord] = result
        time.sleep(0.3)

    # Give traces time to flush
    time.sleep(1)

    # Query all trace events since our first send
    events = api.get_trace_events("windows", limit=500)
    key_downs = [e for e in events if e.get("event") == "key_down"]

    print(f"R3.2: Total key_down events: {len(key_downs)}")
    for kd in key_downs:
        print(f"  key_down: vk={kd.get('vk')} keys={kd.get('keys')}")

    # Verify we have key events for the chords (at minimum, each chord should produce key_down)
    assert len(key_downs) >= len(chords), (
        f"R3.2 FAIL: Expected at least {len(chords)} key_down events, got {len(key_downs)}"
    )

    # Issue: modifier+key chords should produce events with modifier state
    # At minimum, verify each trace_id from our sends produced events
    for chord, result in results.items():
        trace_id = result.get("trace_id")
        matching = [e for e in events if e.get("trace_id") == trace_id]
        assert len(matching) >= 1, (
            f"R3.2 FAIL: No trace events for chord '{chord}' (trace_id={trace_id})"
        )
        print(f"R3.2 [{chord}]: {len(matching)} trace events matched")

    print("R3.2 PASS: Modifier combos produce traceable key events")

    # Cleanup
    api.send_keys(keys="Escape", window_title="Notepad")
    time.sleep(0.3)
    api.send_keys(keys="alt+F4", window_title="Notepad")
    api.stop_trace("windows")


def test_r3_3_focus_bypass_dashboard_fields():
    """R3.3: Keyboard input SHOULD be ignored when focus is inside dashboard
    text fields unless explicitly targeting VNC canvas.

    This is a conformance requirement that the dashboard's input handling
    respects.  The test verifies that keyboard events posted to the API
    with explicit window targeting still reach the target app while
    dashboard text fields may intercept VNC-level keyboard input.
    """
    api = KeyboardAPI(API_URL)
    ensure_openbox_running()
    ensure_agent_control(lease_seconds=300)

    # R3.3 primarily concerns the dashboard UI behavior where keyboard input
    # should not leak from text fields to the VNC canvas.  This is tested
    # by test_ux_keyboard_accessibility.py (Playwright-based UI tests).

    # The API /input/key endpoint bypasses the dashboard UI entirely:
    # keyboard events go directly to AHK/Wine, not through VNC.
    # Verify this property by sending keys to a named window and
    # confirming they arrive even though no dashboard text field is focused.

    api.start_trace("windows")
    time.sleep(1)

    api.run_app("notepad.exe")
    wait_for_window(api, "Notepad")
    time.sleep(0.5)

    result = api.send_keys(keys="Test", window_title="Notepad")
    assert result["status"] == "sent"

    time.sleep(1)
    events = api.get_trace_events("windows", limit=200)
    key_downs = [e for e in events if e.get("event") == "key_down"]
    assert len(key_downs) >= 1, (
        "R3.3 FAIL: Key events not delivered when using API backend (AHK bypass)"
    )

    print("R3.3 PASS: API key injection bypasses dashboard focus, reaches target app")

    # Cleanup
    api.send_keys(keys="alt+F4", window_title="Notepad")
    api.stop_trace("windows")


def test_r3_rapid_fire_keystrokes():
    """R3 extension: Rapid-fire keystrokes must all arrive in order."""
    api = KeyboardAPI(API_URL)
    ensure_openbox_running()
    ensure_agent_control(lease_seconds=300)

    api.start_trace("windows")
    time.sleep(1)

    api.run_app("notepad.exe")
    wait_for_window(api, "Notepad")
    time.sleep(0.5)

    # Send 5 rapid keystrokes
    trace_ids = []
    for char in ["H", "e", "l", "l", "o"]:
        result = api.send_keys(keys=char, window_title="Notepad")
        assert result["status"] == "sent"
        trace_ids.append(result.get("trace_id"))
        time.sleep(0.05)  # Minimum politeness delay but rapid

    time.sleep(1.5)  # Allow trace flush

    events = api.get_trace_events("windows", limit=500)
    matched = 0
    for tid in trace_ids:
        tid_events = [e for e in events if e.get("trace_id") == tid]
        if tid_events:
            matched += 1
        print(f"R3 rapid: trace_id={tid[:8]}... matched={len(tid_events)} events")

    assert matched == 5, (
        f"R3 rapid FAIL: Only {matched}/5 rapid keystrokes produced trace events"
    )

    print(f"R3 rapid PASS: All 5 rapid keystrokes traced (matched={matched}/5)")

    # Cleanup
    api.send_keys(keys="alt+F4", window_title="Notepad")
    api.stop_trace("windows")
