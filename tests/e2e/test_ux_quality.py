import time
from playwright.sync_api import Page, expect
from _auth import get_token, ui_url, ensure_agent_control
from _harness import api_post, wait_badge_text, wait_poll_interval


def auth_page(page: Page):
    token = get_token()
    # Go directly to dashboard with token
    url = ui_url()
    
    # Trace the constructed URL (redacting token)
    safe_url = url
    if token:
        safe_url = url.replace(token, "REDACTED")
    print(f"--> [DEBUG] get_token() returned length: {len(token) if token else 0}")
    print(f"--> [DEBUG] auth_page: Navigating to {safe_url}")
    
    page.goto(url)
    # Wait for the explicit 'ready' marker added to index.html.
    # It is intentionally hidden (display:none), so we wait for attachment.
    print("--> [DEBUG] auth_page: Waiting for #app-ready-marker...")
    page.wait_for_selector("#app-ready-marker", state="attached", timeout=30000)
    print("--> [DEBUG] auth_page: Marker found.")
    # Give it one more second for DOM stabilization
    time.sleep(1)

def test_toast_notifications(page: Page):
    """Tier 1: Verify that UI actions trigger visible toast notifications."""
    auth_page(page)

    # Enable Dev Mode
    page.click(".mode-toggle", force=True)

    # Trigger a screenshot
    page.click("#btn-screenshot")

    # Verify capturing toast appears
    expect(page.locator(".toast", has_text="Capturing screenshot")).to_be_visible()

    # Wait for completion toast (using a broader match to handle filenames)
    expect(page.locator(".toast", has_text="Screenshot saved")).to_be_visible(
        timeout=15000
    )


def test_health_summary_sync(page: Page):
    """Tier 1: Verify that the UI synchronizes with backend process failures."""
    auth_page(page)

    # Verify initial state is healthy
    summary_title = page.locator("#health-summary-title")
    expect(summary_title).to_have_text("System Operational", timeout=15000)

    # Simulate a critical failure by stopping Openbox
    ensure_agent_control()
    api_post("/apps/run", {"path": "pkill", "args": "-f openbox", "detach": False})

    # Wait for the next polling cycle (5s) + some buffer
    wait_poll_interval()
    expect(summary_title).to_have_text("System Issues Detected", timeout=20000)
    expect(page.locator("#health-summary-detail")).to_contain_text("openbox")

    # Restore state for subsequent tests
    ensure_agent_control()
    api_post("/apps/run", {"path": "openbox", "detach": True})
    wait_badge_text(page, "#badge-openbox", "running", timeout_ms=20000)
    expect(summary_title).to_have_text("System Operational", timeout=15000)


def test_responsive_mobile_drawer(page: Page):
    """Tier 1: Verify that the control panel transitions to a drawer on mobile."""
    page.set_viewport_size({"width": 375, "height": 667})
    auth_page(page)

    panel = page.locator("#control-panel")
    menu_btn = page.locator("#mobile-menu-toggle")

    # Ensure button is visible and panel is hidden
    expect(menu_btn).to_be_visible()
    # Panel is off-screen (transform: translateX(100%))
    expect(panel).not_to_be_in_viewport()

    # Toggle Open
    menu_btn.click()
    expect(panel).to_be_in_viewport()

    # Toggle Closed via backdrop (click far left side of viewport)
    page.mouse.click(10, 330)
    expect(panel).not_to_be_in_viewport()


def test_visual_baseline(page: Page):
    """Tier 2: Capture visual snapshots for regression testing."""
    page.set_viewport_size({"width": 1280, "height": 800})
    auth_page(page)

    # Enable Dev Mode for a full visual audit
    page.click(".mode-toggle", force=True)

    # Mask dynamic elements to avoid false positives in future comparisons
    mask = [
        page.locator("#vnc-container"),
        page.locator("#badge-version"),
        page.locator(".log-time"),
        page.locator(".summary-detail"),  # Contains session ID
    ]

    page.screenshot(path="/output/visual_baseline_desktop.png", mask=mask)

    # Mobile
    page.set_viewport_size({"width": 375, "height": 667})
    page.screenshot(path="/output/visual_baseline_mobile.png", mask=mask)
