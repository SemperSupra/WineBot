#!/usr/bin/env python3
import argparse
import subprocess
import sys
import time

import cv2
import numpy as np


def capture_screen(region=None):
    # region format: WxH+X+Y
    cmd = ["import", "-window", "root"]
    if region:
        cmd.extend(["-crop", region])
    cmd.append("png:-")

    try:
        proc = subprocess.run(cmd, capture_output=True, check=True)
        nparr = np.frombuffer(proc.stdout, np.uint8)
        img = cv2.imdecode(nparr, cv2.IMREAD_COLOR)
        return img
    except Exception as e:
        print(f"Error capturing screen: {e}", file=sys.stderr)
        return None


def wait_for_stability(region, duration, timeout, threshold):
    print(
        f"Waiting for pixel stability in {region or 'full screen'} for {duration}s (timeout {timeout}s)..."
    )
    start_time = time.time()
    stable_start = time.time()
    last_img = capture_screen(region)

    while time.time() - start_time < timeout:
        time.sleep(0.2)
        current_img = capture_screen(region)

        if last_img is None or current_img is None:
            last_img = current_img
            stable_start = time.time()
            continue

        if last_img.shape != current_img.shape:
            # Should not happen if region is fixed
            last_img = current_img
            stable_start = time.time()
            continue

        # Compare
        diff = cv2.absdiff(last_img, current_img)
        non_zero = np.count_nonzero(diff)

        if non_zero <= (last_img.size * threshold):
            # Stable
            if time.time() - stable_start >= duration:
                print("Stability reached.")
                return True
        else:
            # Changed
            stable_start = time.time()
            last_img = current_img

    print("Timeout waiting for stability.")
    return False


def main():
    parser = argparse.ArgumentParser(description="Wait for screen pixel stability.")
    parser.add_argument("--region", help="Region WxH+X+Y")
    parser.add_argument(
        "--duration",
        type=float,
        default=1.0,
        help="Required stability duration in seconds",
    )
    parser.add_argument("--timeout", type=float, default=10.0, help="Max wait time")
    parser.add_argument(
        "--threshold", type=float, default=0.001, help="Change threshold (0.0-1.0)"
    )

    args = parser.parse_args()

    if wait_for_stability(args.region, args.duration, args.timeout, args.threshold):
        sys.exit(0)
    else:
        sys.exit(1)


if __name__ == "__main__":
    main()
