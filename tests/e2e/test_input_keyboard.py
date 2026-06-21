"""E2E test for the /input/key keyboard injection endpoint.

Verifies that keyboard input via the API reaches Windows applications,
bypassing the X11 explorer.exe/desktop interception layer using AHK Send.
"""

from playwright.sync_api import Page, expect
import requests
import time
from _auth import API_URL, auth_headers, ui_url, ensure_agent_control, ensure_openbox_running


class WineBotAPI:
    """Minimal API helper for the keyboard test."""

    def __init__(self, url: str):
        self.url = url
        self.headers = auth_headers()

    def get_windows(self) -> dict:
        res = requests.get(f"{self.url}/health/windows", headers=self.headers, timeout=10)
        res.raise_for_status()
        return res.json()

    def run_app(self, path: str, detach: bool = True) -> dict:
        res = requests.post(
            f"{self.url}/apps/run",
            json={"path": path, "detach": detach},
            headers=self.headers,
            timeout=10,
        )
        res.raise_for_status()
        return res.json()

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

    def get_screenshot_path(self) -> str:
        """GET /screenshot returns a PNG; we save it to /output."""
        res = requests.get(
            f"{self.url}/screenshot",
            headers=self.headers,
            timeout=10,
        )
        res.raise_for_status()
        screenshot_path = res.headers.get("X-Screenshot-Path", "")
        return screenshot_path


def wait_for_notepad_window(api: WineBotAPI, max_attempts: int = 20) -> dict:
    """Wait for a Notepad window to appear via the API."""
    for i in range(max_attempts):
        windows_payload = api.get_windows()
        windows = windows_payload.get("windows", [])
        notepad_win = next((w for w in windows if "Notepad" in w["title"]), None)
        if notepad_win:
            return notepad_win
        time.sleep(2)
    raise AssertionError("Notepad window not found via API after %d attempts" % max_attempts)


def test_keyboard_text_injection(page: Page):
    """Test that plain text can be sent to Notepad via /input/key."""
    api = WineBotAPI(API_URL)

    # Ensure the interactive stack and agent control are ready
    ensure_openbox_running()
    ensure_agent_control(lease_seconds=300)

    # 1. Launch Notepad
    print("Launching Notepad via API...")
    run_res = api.run_app("notepad.exe")
    print(f"Notepad launch result: {run_res}")

    # 2. Wait for Notepad window
    notepad_win = wait_for_notepad_window(api)
    print(f"Notepad window found: {notepad_win}")

    # 3. Send plain text via /input/key (AHK backend by default)
    test_text = "Hello WineBot Keyboard Test"
    print(f"Sending keys via /input/key: {test_text}")
    key_res = api.send_keys(keys=test_text, window_title="Notepad")
    print(f"Key response: {key_res}")
    assert key_res["status"] == "sent"
    assert key_res["backend"] == "ahk"

    time.sleep(1)

    # 4. Take a screenshot for visual verification
    screenshot_path = api.get_screenshot_path()
    print(f"Screenshot captured: {screenshot_path}")

    # 5. Also capture via Playwright for the test report
    page.goto(ui_url())
    page.click(".mode-toggle", force=True)  # Enable dev mode

    # Wait for VNC connection
    badge = page.locator("#badge-vnc")
    expect(badge).not_to_have_text("connecting...", timeout=15000)

    time.sleep(2)
    page.screenshot(path="/output/input_key_text_test.png")
    print("Playwright screenshot saved to /output/input_key_text_test.png")


def test_keyboard_modifier_chord(page: Page):
    """Test that modifier chords (e.g., ctrl+s) can be sent to Notepad."""
    api = WineBotAPI(API_URL)

    ensure_openbox_running()
    ensure_agent_control(lease_seconds=300)

    # 1. Launch Notepad
    print("Launching Notepad for modifier test...")
    api.run_app("notepad.exe")

    # 2. Wait for Notepad window
    notepad_win = wait_for_notepad_window(api)
    print(f"Notepad window found: {notepad_win}")

    # 3. Type some text first
    api.send_keys(keys="Test save dialog", window_title="Notepad")
    time.sleep(0.5)

    # 4. Press Ctrl+S to open Save dialog
    print("Sending ctrl+s chord...")
    key_res = api.send_keys(keys="ctrl+s", window_title="Notepad")
    print(f"Key response: {key_res}")
    assert key_res["status"] == "sent"
    assert key_res["backend"] == "ahk"

    time.sleep(2)

    # 5. Check if Save As dialog appeared
    windows_payload = api.get_windows()
    windows = windows_payload.get("windows", [])
    print(f"Windows after ctrl+s: {windows}")
    save_dialog = next(
        (w for w in windows if "Save As" in w.get("title", "")),
        None,
    )
    # Note: Wine Notepad may use "Save As" or localized title
    assert save_dialog, (
        "Save As dialog not found after ctrl+s. Windows: %s" % windows
    )

    # 6. Dismiss the dialog with Escape
    print("Dismissing Save dialog with Escape...")
    api.send_keys(keys="Escape", window_title="Save As")
    time.sleep(0.5)

    # 7. Close Notepad with Alt+F4
    print("Closing Notepad with alt+F4...")
    api.send_keys(keys="alt+F4", window_title="Notepad")
    time.sleep(1)

    # 8. Verify Notepad closed
    final_windows = api.get_windows().get("windows", [])
    notepad_still_open = any("Notepad" in w.get("title", "") for w in final_windows)
    print(f"Notepad still open: {notepad_still_open}")

    # Take final screenshot
    page.goto(ui_url())
    page.click(".mode-toggle", force=True)
    time.sleep(2)
    page.screenshot(path="/output/input_key_modifier_test.png")


def test_keyboard_named_keys(page: Page):
    """Test that named keys (Return, Tab, BackSpace) work via /input/key."""
    api = WineBotAPI(API_URL)

    ensure_openbox_running()
    ensure_agent_control(lease_seconds=300)

    # 1. Launch Notepad
    api.run_app("notepad.exe")
    notepad_win = wait_for_notepad_window(api)
    print(f"Notepad window found: {notepad_win}")

    # 2. Type text, then use BackSpace and Return
    api.send_keys(keys="Line1", window_title="Notepad")
    time.sleep(0.3)

    # Send Return (new line)
    print("Sending Return for newline...")
    key_res = api.send_keys(keys="Return", window_title="Notepad")
    assert key_res["status"] == "sent"
    time.sleep(0.3)

    api.send_keys(keys="Line2", window_title="Notepad")
    time.sleep(0.3)

    # Send BackSpace to delete characters
    print("Sending BackSpace...")
    api.send_keys(keys="BackSpace", window_title="Notepad")
    time.sleep(0.3)

    api.send_keys(keys="Tab", window_title="Notepad")
    time.sleep(0.3)

    api.send_keys(keys="indented", window_title="Notepad")
    time.sleep(0.5)

    # Screenshot for visual verification
    page.goto(ui_url())
    page.click(".mode-toggle", force=True)
    time.sleep(2)
    page.screenshot(path="/output/input_key_named_keys_test.png")

    # Close Notepad
    api.send_keys(keys="alt+F4", window_title="Notepad")
    time.sleep(0.5)
    # If "Do you want to save" dialog appears, dismiss it
    final_windows = api.get_windows().get("windows", [])
    if any("Notepad" in w.get("title", "") for w in final_windows):
        api.send_keys(keys="alt+F4", window_title="Notepad")
    time.sleep(1)
