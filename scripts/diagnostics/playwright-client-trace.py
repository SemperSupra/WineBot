import sys
import os
from playwright.sync_api import sync_playwright

def main():
    api_url = os.environ.get("API_URL", "http://localhost:8000")

    try:
        with sync_playwright() as p:
            browser = p.chromium.launch(headless=True)
            context = browser.new_context(viewport={"width": 1024, "height": 768})
            page = context.new_page()

            ui_url = f"{api_url}/ui"
            print(f"Navigating to {ui_url}...")
            page.goto(ui_url)

            try:
                page.wait_for_selector("#noVNC_canvas", timeout=5000, state="visible")
                print("Canvas is visible. Dispatching click...")

                canvas = page.locator("#noVNC_canvas")
                page.wait_for_timeout(2000)

                canvas.click(position={"x": 120, "y": 140}, button="left")
                print("Click dispatched via Playwright.")

                page.wait_for_timeout(1000)

            except Exception as e:
                print(f"Playwright error: {e}", file=sys.stderr)
                sys.exit(1)
            finally:
                browser.close()

    except Exception as e:
        print(f"Error launching playwright: {e}", file=sys.stderr)
        sys.exit(1)

if __name__ == "__main__":
    main()
