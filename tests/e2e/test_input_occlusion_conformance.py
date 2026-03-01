from playwright.sync_api import Page, expect
import time
from typing import TypedDict, cast
from _auth import ui_url


class CanvasBox(TypedDict):
    x: float
    y: float
    width: float
    height: float


class RelativeSample(TypedDict):
    name: str
    rx: float
    ry: float


class AbsolutePoint(TypedDict):
    name: str
    x: float
    y: float


def _expand_section(page: Page, title: str) -> None:
    section = page.locator(".panel-section", has_text=title)
    toggle = section.locator(".section-toggle")
    if toggle.get_attribute("aria-expanded") == "false":
        toggle.click()


def _ensure_vnc_connected(page: Page) -> None:
    badge = page.locator("#badge-vnc")
    expect(badge).not_to_have_text("connecting...", timeout=15000)
    for _ in range(3):
        text = (badge.text_content() or "").strip().lower()
        if text == "connected":
            return
        if "password required" in text:
            _expand_section(page, "Configuration")
            page.fill("#vnc-password", "winebot")
            page.click("#save-vnc")
            expect(badge).to_have_text("connected", timeout=8000)
            return
        # Handle transient timeout/error badge states by forcing reconnect.
        _expand_section(page, "VNC Settings")
        page.click("#btn-reconnect-vnc")
        time.sleep(1)
        expect(badge).not_to_have_text("connecting...", timeout=15000)
    raise AssertionError(f"VNC did not reach connected state. Last badge: {badge.text_content()}")


def _ensure_client_trace(page: Page) -> None:
    _expand_section(page, "VNC Settings")
    trace_checkbox = page.locator("#vnc-trace-input")
    if not trace_checkbox.is_checked():
        trace_checkbox.click()
        time.sleep(0.5)


def _canvas_box(page: Page) -> CanvasBox:
    canvas = page.locator("#vnc-container canvas:not(#vnc-crosshair)")
    expect(canvas).to_be_visible(timeout=10000)
    box = canvas.bounding_box()
    assert box and box["width"] > 200 and box["height"] > 200, (
        f"Unexpected canvas bounds: {box}"
    )
    return cast(CanvasBox, box)


def test_vnc_non_occlusion_hit_test(page: Page):
    page.goto(ui_url())
    page.click(".mode-toggle", force=True)
    _ensure_vnc_connected(page)
    box = _canvas_box(page)

    pointer_events = page.evaluate(
        """() => ({
            overlay: getComputedStyle(document.querySelector(".vnc-overlay")).pointerEvents,
            overlayRight: getComputedStyle(document.querySelector(".vnc-overlay-right")).pointerEvents
        })"""
    )
    assert pointer_events["overlay"] == "none"
    assert pointer_events["overlayRight"] == "none"

    samples = [
        {"name": "center", "rx": 0.50, "ry": 0.50},
        {"name": "left_mid", "rx": 0.20, "ry": 0.50},
        {"name": "right_mid", "rx": 0.80, "ry": 0.50},
        {"name": "upper_mid", "rx": 0.50, "ry": 0.20},
        {"name": "lower_mid", "rx": 0.50, "ry": 0.80},
        {"name": "upper_left_safe", "rx": 0.25, "ry": 0.25},
        {"name": "upper_right_safe", "rx": 0.75, "ry": 0.25},
    ]

    hit_results = page.evaluate(
        """(samples) => {
            const canvas = document.querySelector("#vnc-container canvas:not(#vnc-crosshair)");
            const rect = canvas.getBoundingClientRect();
            return samples.map((s) => {
                const x = Math.round(rect.left + rect.width * s.rx);
                const y = Math.round(rect.top + rect.height * s.ry);
                const top = document.elementFromPoint(x, y);
                return {
                    name: s.name,
                    x,
                    y,
                    topTag: top ? top.tagName : null,
                    topId: top ? top.id : null,
                    topClass: top ? top.className : null,
                    isCanvasHit: !!top && (top === canvas || canvas.contains(top))
                };
            });
        }""",
        samples,
    )

    failures = [entry for entry in hit_results if not entry["isCanvasHit"]]
    assert not failures, f"Canvas points occluded or not hit-test reachable: {failures}"

    # Keep this assertion tied to actual rendered canvas dimensions.
    assert box["width"] >= 600
    assert box["height"] >= 400


def test_canvas_clicks_pass_through_non_control_regions(page: Page):
    page.goto(ui_url())
    page.click(".mode-toggle", force=True)
    _ensure_vnc_connected(page)
    _ensure_client_trace(page)
    _expand_section(page, "Input Debug")
    box = _canvas_box(page)

    samples: list[RelativeSample] = [
        {"name": "center", "rx": 0.50, "ry": 0.50},
        {"name": "left_mid", "rx": 0.20, "ry": 0.55},
        {"name": "right_mid", "rx": 0.80, "ry": 0.55},
    ]

    abs_points: list[AbsolutePoint] = []
    for s in samples:
        x = float(round(box["x"] + box["width"] * s["rx"]))
        y = float(round(box["y"] + box["height"] * s["ry"]))
        abs_points.append({"name": s["name"], "x": x, "y": y})

    for p in abs_points:
        is_canvas_hit = page.evaluate(
            """(pt) => {
                const canvas = document.querySelector("#vnc-container canvas:not(#vnc-crosshair)");
                const top = document.elementFromPoint(pt.x, pt.y);
                return !!top && (top === canvas || canvas.contains(top));
            }""",
            p,
        )
        assert is_canvas_hit, f"Click sample point not targeting canvas: {p}"
        page.mouse.click(p["x"], p["y"])

    expect(page.locator("#input-debug-stats")).to_contain_text(
        "Mouse",
        timeout=5000,
    )
    expect(page.locator("#input-debug-log")).to_contain_text(
        "client(",
        timeout=5000,
    )
