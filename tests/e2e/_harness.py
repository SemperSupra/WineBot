import time
import requests
from playwright.sync_api import Page, expect

from _auth import API_URL, auth_headers


def api_post(path: str, payload: dict | None = None, timeout: int = 15):
    resp = requests.post(
        f"{API_URL}{path}",
        json=payload,
        headers=auth_headers(),
        timeout=timeout,
    )
    resp.raise_for_status()
    return resp


def wait_badge_text(page: Page, selector: str, text: str, timeout_ms: int = 15000):
    expect(page.locator(selector)).to_contain_text(text, timeout=timeout_ms)


def wait_poll_interval(seconds: float = 5.5):
    # Dashboard poll period is 5s. Keep helper centralized for deterministic tests.
    time.sleep(seconds)
