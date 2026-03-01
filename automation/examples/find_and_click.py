#!/usr/bin/env python3
import argparse
import os
import subprocess
import sys
import tempfile
import time

import cv2


def capture_screenshot(display_value, output_path, window_id=None):
    target_window = "root" if window_id is None else str(window_id)
    result = subprocess.run(
        ["import", "-display", display_value, "-window", target_window, output_path],
        capture_output=True,
        text=True,
    )
    if result.returncode != 0:
        raise RuntimeError(result.stderr.strip() or "Failed to capture screenshot")


def load_image(image_path, error_label):
    image = cv2.imread(image_path)
    if image is None:
        raise RuntimeError(f"Unable to load {error_label} from {image_path}")
    return image


def click_coordinates(x_coord, y_coord, click_count, button, display_value):
    env = dict(os.environ)
    env["DISPLAY"] = display_value
    cmd = ["xdotool", "mousemove", "--sync", str(x_coord), str(y_coord)]
    for _ in range(max(1, int(click_count))):
        cmd.extend(["click", str(button)])
    subprocess.run(cmd, check=True, env=env)


def get_window_origin(window_id, display_value):
    env = dict(os.environ)
    env["DISPLAY"] = display_value
    result = subprocess.run(
        ["xdotool", "getwindowgeometry", "--shell", str(window_id)],
        capture_output=True,
        text=True,
        check=True,
        env=env,
    )
    x_val = 0
    y_val = 0
    for line in result.stdout.splitlines():
        if line.startswith("X="):
            x_val = int(line.split("=", 1)[1].strip())
        elif line.startswith("Y="):
            y_val = int(line.split("=", 1)[1].strip())
    return x_val, y_val


def find_and_click(
    template_path,
    display_value,
    threshold_value,
    retries,
    delay_seconds,
    screenshot_out,
    click_count,
    button,
    window_id,
):
    template = load_image(template_path, "template")
    temporary_path = None
    if screenshot_out is None:
        temp_file = tempfile.NamedTemporaryFile(suffix=".png", delete=False)
        temporary_path = temp_file.name
        temp_file.close()
        screenshot_out = temporary_path

    try:
        for attempt_index in range(retries):
            capture_screenshot(display_value, screenshot_out, window_id=window_id)
            screenshot = load_image(screenshot_out, "screenshot")
            result = cv2.matchTemplate(screenshot, template, cv2.TM_CCOEFF_NORMED)
            _, max_value, _, max_location = cv2.minMaxLoc(result)
            if max_value >= threshold_value:
                template_height, template_width = template.shape[:2]
                center_x = max_location[0] + template_width // 2
                center_y = max_location[1] + template_height // 2
                if window_id is not None:
                    origin_x, origin_y = get_window_origin(window_id, display_value)
                    center_x += origin_x
                    center_y += origin_y
                print(
                    f"match={max_value:.3f} click=({center_x},{center_y}) window_id={window_id or 'root'}"
                )
                click_coordinates(center_x, center_y, click_count, button, display_value)
                return True
            if attempt_index < retries - 1:
                time.sleep(delay_seconds)
        return False
    finally:
        if temporary_path is not None:
            os.unlink(temporary_path)


def parse_args():
    parser = argparse.ArgumentParser()
    parser.add_argument("--template", required=True)
    parser.add_argument("--threshold", type=float, default=0.8)
    parser.add_argument("--retries", type=int, default=5)
    parser.add_argument("--delay", type=float, default=1.0)
    parser.add_argument("--display", default=os.environ.get("DISPLAY", ":99"))
    parser.add_argument("--screenshot-out")
    parser.add_argument("--click-count", type=int, default=1)
    parser.add_argument("--button", type=int, default=1)
    parser.add_argument("--window-id")
    return parser.parse_args()


def main():
    args = parse_args()
    try:
        found = find_and_click(
            template_path=args.template,
            display_value=args.display,
            threshold_value=args.threshold,
            retries=args.retries,
            delay_seconds=args.delay,
            screenshot_out=args.screenshot_out,
            click_count=args.click_count,
            button=args.button,
            window_id=args.window_id,
        )
    except Exception as exc:
        print(str(exc), file=sys.stderr)
        return 1
    return 0 if found else 2


if __name__ == "__main__":
    sys.exit(main())
