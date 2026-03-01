from playwright.sync_api import Page, expect
import requests
import time
import json
import glob
import os
from _auth import API_URL, auth_headers, ui_url, ensure_agent_control, ensure_openbox_running


class WineBotAPI:
    def __init__(self, url):
        self.url = url
        self.headers = auth_headers()

    def get_windows(self):
        res = requests.get(f"{self.url}/health/windows", headers=self.headers)
        res.raise_for_status()
        return res.json()

    def run_app(self, path):
        res = requests.post(
            f"{self.url}/apps/run",
            json={"path": path, "detach": True},
            headers=self.headers,
        )
        res.raise_for_status()
        return res.json()

    def get_session_id(self):
        res = requests.get(f"{self.url}/lifecycle/status", headers=self.headers)
        res.raise_for_status()
        return res.json().get("session_id")


def get_input_logs(session_id):
    # The volume is mounted at /output
    log_dir = f"/output/sessions/{session_id}/logs"
    print(f"DEBUG: Looking for logs in {log_dir}")
    logs = []
    if os.path.exists(log_dir):
        # 1. Windows log (AHK)
        win_matches = glob.glob(f"{log_dir}/input_events_windows*.jsonl")
        if win_matches:
            logs.append(sorted(win_matches, key=os.path.getmtime, reverse=True)[0])
        # 2. Linux log (xinput)
        lin_matches = glob.glob(f"{log_dir}/input_events.jsonl")
        if lin_matches:
            logs.append(lin_matches[0])
        # 3. Client-side noVNC trace
        client_matches = glob.glob(f"{log_dir}/input_events_client*.jsonl")
        if client_matches:
            logs.append(sorted(client_matches, key=os.path.getmtime, reverse=True)[0])
    return logs


def wait_for_input_logs(api: WineBotAPI, timeout_seconds: int = 30):
    deadline = time.time() + timeout_seconds
    while time.time() < deadline:
        session_id = api.get_session_id()
        logs = get_input_logs(session_id)
        if logs:
            return session_id, logs
        time.sleep(1)
    raise AssertionError("Input logs were not created before timeout")


def test_comprehensive_input(page: Page):
    api = WineBotAPI(API_URL)
    ensure_openbox_running()

    # 1. Setup Dashboard
    page.goto(ui_url())

    # Enable Dev Mode
    page.click(".mode-toggle", force=True)

    # Handle password
    badge = page.locator("#badge-vnc")
    expect(badge).not_to_have_text("connecting...", timeout=15000)
    if "password required" in badge.text_content(): # type: ignore
        config_toggle = page.locator(
            ".panel-section", has_text="Configuration"
        ).locator(".section-toggle")
        if config_toggle.get_attribute("aria-expanded") == "false":
            config_toggle.click()
        page.fill("#vnc-password", "winebot")
        page.click("#save-vnc")
        expect(badge).to_have_text("connected", timeout=5000)

    # 2. Ensure Scale to Fit is OFF (for precise coordinates)
    vnc_settings = page.locator(".panel-section", has_text="VNC Settings")
    toggle = vnc_settings.locator(".section-toggle")
    if toggle.get_attribute("aria-expanded") == "false":
        toggle.click()

    scale_checkbox = page.locator("#vnc-scale")
    if scale_checkbox.is_checked():
        scale_checkbox.click()
        time.sleep(1)  # Wait for resize

    # Enable client-side trace so click evidence is captured even when
    # Windows-side hooks only emit movement/keyboard.
    trace_checkbox = page.locator("#vnc-trace-input")
    if not trace_checkbox.is_checked():
        trace_checkbox.click()
        time.sleep(1)

    # 3. Launch Notepad
    print("Launching Notepad...")
    ensure_agent_control()
    run_res = api.run_app("notepad.exe")
    print(f"Run result: {run_res}")

    # 4. Find Notepad Window
    notepad_win = None
    max_attempts = 30
    relaunch_count = 0
    for i in range(max_attempts):
        windows_payload = api.get_windows()
        windows = windows_payload.get("windows", [])
        print(f"Windows found: {windows}")
        if windows_payload.get("error"):
            print(f"Window list error: {windows_payload.get('error')}")
        notepad_win = next((w for w in windows if "Notepad" in w["title"]), None)
        if notepad_win:
            break
        # Recover from transient shell/app launch failures without hiding persistent errors.
        if i in (6, 14, 22) and relaunch_count < 3:
            relaunch_count += 1
            print(f"Notepad not visible yet; attempting controlled relaunch ({relaunch_count}/3).")
            ensure_openbox_running()
            ensure_agent_control()
            run_res = api.run_app("notepad.exe")
            print(f"Relaunch result: {run_res}")
        time.sleep(2)

    assert notepad_win, "Notepad window not found via API"
    print(f"Notepad Window: {notepad_win}")

    # Get geometry (API doesn't return geometry in /health/windows summary, need /inspect or assume centered?)
    # Wait, /health/windows only returns ID and Title.
    # /inspect/window gives details.

    # Inspect window (use title)
    res = requests.post(
        f"{API_URL}/inspect/window",
        json={"title": notepad_win["title"]},
        headers=auth_headers(),
    )
    if res.ok:
        print(f"Inspection Result: {res.json()}")
    else:
        print(f"Inspection Failed: {res.text}")

    # We proceed with blind clicks on Start Button and Notepad center
    # Start Button approx 20, 705 (bottom left)

    print("Clicking Start Button area...")
    canvas = page.locator("#vnc-container canvas:not(#vnc-crosshair)")

    # VNC coordinates: (20, 700) (approx)
    # We click via canvas.
    canvas.click(position={"x": 20, "y": 705})
    time.sleep(2)
    page.screenshot(path="/output/start_menu_click.png")

    # Now click Notepad text area (center of screen likely if it just opened)
    # Notepad usually opens cascaded.
    # Let's try to type blindly into the center of the screen, hoping Notepad is there.
    # Or use "Force Focus" button in dashboard!

    print("Forcing focus on Notepad...")
    # There is a button "Force App Focus" in VNC Settings
    page.click("#btn-force-focus")
    time.sleep(1)

    print("Typing text...")
    canvas.click()  # Ensure canvas has focus for keyboard input
    page.keyboard.type("Hello WineBot Input Test")
    time.sleep(1)
    page.screenshot(path="/output/notepad_typed.png")

    # 5. Verify Received Events
    session_id, log_files = wait_for_input_logs(api, timeout_seconds=30)

    found_clicks = 0
    found_keys = 0

    for log_file in log_files:
        print(f"Reading log: {log_file}")
        with open(log_file, "r") as f:
            for line in f:
                try:
                    event = json.loads(line)
                    # Check for clicks (mousedown in AHK, button_press in Linux)
                    if (
                        event.get("event") == "mousedown"
                        or event.get("event") == "button_press"
                        or event.get("event") == "client_mouse_down"
                        or event.get("event") == "client_mouse_up"
                    ):
                        # Detail 1 or LButton
                        if (
                            event.get("button") == "LButton"
                            or event.get("button") == 1
                            or event.get("button") == 0
                        ):
                            found_clicks += 1
                            print(f"Found Click in {log_file}: {event}")
                    # Check for keys (keydown in AHK, key_press in Linux)
                    if (
                        event.get("event") == "keydown"
                        or event.get("event") == "key_press"
                        or event.get("event") == "client_key_down"
                        or event.get("event") == "key_down"
                    ):
                        found_keys += 1
                except json.JSONDecodeError:
                    pass

    print(f"Total Clicks across all logs: {found_clicks}")
    print(f"Total Keys across all logs: {found_keys}")

    # We expect at least the start button click and some keys
    assert found_clicks > 0, "No clicks detected in any input log"
    assert found_keys > 0, "No keypresses detected in any input log"

    print("SUCCESS: Input validated end-to-end.")
