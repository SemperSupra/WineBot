import re

from playwright.sync_api import Page, expect


def test_dashboard_loads(page: Page):
    # Capture console logs
    page.on("console", lambda msg: print(f"BROWSER CONSOLE: {msg.type}: {msg.text}"))
    page.on("pageerror", lambda exc: print(f"BROWSER ERROR: {exc}"))

    # Navigate to the dashboard
    # The hostname 'winebot-interactive' must match the service name in docker-compose
    page.goto("http://winebot-interactive:8000/ui/")

    # 1. Verify Title
    expect(page).to_have_title(re.compile("WineBot Dashboard"))

    # 2. Enable Dev Mode (required to see Configuration/Lifecycle/API)
    page.click(".mode-toggle", force=True)

    # 3. Verify VNC Badge Initial State
    # It might start as 'connecting...' or 'client missing' if something is wrong
    badge_vnc = page.locator("#badge-vnc")
    expect(badge_vnc).to_be_visible()

    # 3. Wait for Connection or Password Prompt
    print("DEBUG: Waiting for VNC badge to change...")
    page.screenshot(path="/output/debug_before_wait.png")

    # We expect it to eventually NOT be 'connecting...'
    # It should become 'connected' or 'password required' or 'timeout'
    # We allow a generous timeout for the initial connection
    expect(badge_vnc).not_to_have_text("connecting...", timeout=15000)

    # Check what state we ended up in
    status = badge_vnc.text_content() or ""
    print(f"VNC Status: {status}")

    if "password required" in status:
        # Expand Configuration panel if collapsed
        config_section = page.locator(".panel-section", has_text="Configuration")
        config_toggle = config_section.locator(".section-toggle")
        is_expanded = config_toggle.get_attribute("aria-expanded")
        print(f"DEBUG: Configuration panel expanded: {is_expanded}")

        if is_expanded == "false":
            config_toggle.click()

        # Handle password
        password_input = page.locator("#vnc-password")
        password_input.wait_for(state="visible", timeout=2000)
        password_input.fill("winebot")
        page.click("#save-vnc")
        # Should now connect
        expect(badge_vnc).to_have_text("connected", timeout=5000)

    elif "connected" in status:
        # Already good (maybe cached or no password)
        pass
    else:
        # Failed state
        assert False, f"VNC failed to connect. Status: {status}"

    # 4. Verify Canvas
    canvas = page.locator("#vnc-container canvas:not(#vnc-crosshair)")
    expect(canvas).to_be_visible()

    # 5. Take a screenshot for evidence
    page.screenshot(path="/output/dashboard_success.png")
