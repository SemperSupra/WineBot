from playwright.sync_api import Page, expect
import time
from _auth import ui_url


def test_mouse_input_trace(page: Page):
    # Enable console logging
    page.on("console", lambda msg: print(f"CONSOLE: {msg.text}"))
    page.on("pageerror", lambda exc: print(f"ERROR: {exc}"))

    # Load dashboard
    page.goto(ui_url())

    # Enable Dev Mode
    page.click(".mode-toggle", force=True)

    # Handle VNC password if needed
    badge = page.locator("#badge-vnc")
    expect(badge).not_to_have_text("connecting...", timeout=15000)

    if "password required" in badge.text_content(): # type: ignore
        # Expand config if needed
        toggle = page.locator(".panel-section", has_text="Configuration").locator(
            ".section-toggle"
        )
        if toggle.get_attribute("aria-expanded") == "false":
            toggle.click()
        page.fill("#vnc-password", "winebot")
        page.click("#save-vnc")
        expect(badge).to_have_text("connected", timeout=5000)

    # Enable Client Tracing
    # Expand "VNC Settings" if needed
    vnc_settings = page.locator(".panel-section", has_text="VNC Settings")
    toggle = vnc_settings.locator(".section-toggle")
    if toggle.get_attribute("aria-expanded") == "false":
        toggle.click()

    trace_checkbox = page.locator("#vnc-trace-input")
    if not trace_checkbox.is_checked():
        trace_checkbox.click()
        # Wait for update
        time.sleep(1)

    # Expand "Input Debug" to see logs
    debug_section = page.locator(".panel-section", has_text="Input Debug")
    toggle = debug_section.locator(".section-toggle")
    if toggle.get_attribute("aria-expanded") == "false":
        toggle.click()

    # Get Canvas
    canvas = page.locator("#vnc-container canvas:not(#vnc-crosshair)")
    box = canvas.bounding_box()
    print(f"Canvas Box: {box}")

    # Perform Click at offset (100, 100) relative to canvas
    target_x = 100
    target_y = 100
    canvas.click(position={"x": target_x, "y": target_y})

    # Check Input Debug Log for "client_mouse_up"
    # The log adds entries like: [Time] client_mouse_up ...
    # We wait for the log to contain our event
    debug_log = page.locator("#input-debug-log")

    # We expect the log to eventually show the event.
    # The dashboard logs: "Last event: client_mouse_up" in stats
    # And detailed log entry.

    expect(page.locator("#input-debug-stats")).to_contain_text("Mouse")

    # Verify coordinates in the detailed log (if implemented in index.html logging)
    # index.html logic: postClientTraceEvent(...)
    # But it doesn't log the FULL payload to the on-screen log, only "Last event: ..."
    # Wait, look at index.html:
    # updateInputDebug(msg)
    # canvas.addEventListener("mousedown") -> updateInputDebug(...)

    # "Mousedown: client(x,y) -> VNC(vx,vy)"

    # Let's verify the log entry
    expected_log_part = f"client({target_x},{target_y})"
    # Note: clientX/Y in browser might be relative to viewport, but getCanvasCoords subtracts rect.left/top.
    # So it should be close to 100,100 if click position is relative to element.
    # Playwright click(position=...) is relative to element top-left.

    # We need to wait for the text to appear
    print(f"Expecting log to contain: {expected_log_part}")
    expect(debug_log).to_contain_text(expected_log_part)

    # Take a screenshot
    page.screenshot(path="/output/input_test.png")
