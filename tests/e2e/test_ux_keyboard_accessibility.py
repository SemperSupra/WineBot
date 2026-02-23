from playwright.sync_api import Page, expect

from _auth import ui_url


def test_keyboard_navigation_basics(page: Page):
    page.set_viewport_size({"width": 375, "height": 667})
    page.goto(ui_url())

    # Ensure focus can reach key controls using keyboard-only navigation.
    mobile_toggle = page.locator("#mobile-menu-toggle")
    mobile_toggle.focus()
    expect(mobile_toggle).to_be_focused()
    mobile_toggle.press("Enter")

    screenshot_btn = page.locator("#btn-screenshot")
    screenshot_btn.focus()
    expect(screenshot_btn).to_be_focused()
