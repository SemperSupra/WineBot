#!/usr/bin/env python3
# EXECUTION: IN_CONTAINER — uses ctypes/Win32 API for input diagnosis; requires Wine runtime
# STATUS: ACTIVE — Win32 input pipeline diagnosis; keyboard/mouse event tracing
import argparse
import ctypes
import json
import time

KEY_MAP = {
    "VK_LBUTTON": 0x01,
    "LBUTTON": 0x01,
    "VK_RBUTTON": 0x02,
    "RBUTTON": 0x02,
    "VK_CANCEL": 0x03,
    "VK_MBUTTON": 0x04,
    "MBUTTON": 0x04,
    "VK_XBUTTON1": 0x05,
    "XBUTTON1": 0x05,
    "VK_XBUTTON2": 0x06,
    "XBUTTON2": 0x06,
    "VK_BACK": 0x08,
    "VK_TAB": 0x09,
    "VK_RETURN": 0x0D,
    "VK_SHIFT": 0x10,
    "SHIFT": 0x10,
    "VK_CONTROL": 0x11,
    "CONTROL": 0x11,
    "CTRL": 0x11,
    "VK_MENU": 0x12,
    "ALT": 0x12,
    "VK_CAPITAL": 0x14,
    "VK_ESCAPE": 0x1B,
    "VK_SPACE": 0x20,
    "VK_LEFT": 0x25,
    "VK_UP": 0x26,
    "VK_RIGHT": 0x27,
    "VK_DOWN": 0x28,
    "VK_A": 0x41,
    "A": 0x41,
    "VK_B": 0x42,
    "B": 0x42,
    "VK_C": 0x43,
    "C": 0x43,
    "VK_D": 0x44,
    "D": 0x44,
    "VK_E": 0x45,
    "E": 0x45,
    "VK_F": 0x46,
    "F": 0x46,
}


def parse_keys(keys_csv: str):
    keys = []
    if not keys_csv:
        return keys
    for token in keys_csv.split(","):
        token = token.strip()
        if not token:
            continue
        upper = token.upper()
        if upper.startswith("0X"):
            try:
                keys.append((token, int(upper, 16)))
                continue
            except ValueError:
                pass
        if upper.isdigit():
            try:
                keys.append((token, int(upper)))
                continue
            except ValueError:
                pass
        if upper in KEY_MAP:
            keys.append((token, KEY_MAP[upper]))
            continue
        # fallback: try VK_ prefixed
        vk_name = "VK_" + upper
        if vk_name in KEY_MAP:
            keys.append((token, KEY_MAP[vk_name]))
            continue
    return keys


def main():
    parser = argparse.ArgumentParser(
        description="Poll GetAsyncKeyState and log key states to JSONL"
    )
    parser.add_argument("--out", required=True)
    parser.add_argument("--duration", type=float, default=10.0)
    parser.add_argument("--interval-ms", type=int, default=50)
    parser.add_argument("--keys", default="VK_LBUTTON,VK_A,VK_B,VK_MENU")
    args = parser.parse_args()

    keys = parse_keys(args.keys)
    if not keys:
        return 0

    user32 = ctypes.windll.user32
    get_async = user32.GetAsyncKeyState
    get_async.argtypes = [ctypes.c_int]
    get_async.restype = ctypes.c_short

    end_time = time.time() + max(0.1, float(args.duration))
    interval = max(1, int(args.interval_ms)) / 1000.0

    with open(args.out, "w", encoding="utf-8") as f:
        while time.time() < end_time:
            ts_ms = int(time.time() * 1000)
            for label, vk in keys:
                state = get_async(int(vk))
                down = 1 if (state & 0x8000) else 0
                f.write(
                    json.dumps(
                        {
                            "timestamp_epoch_ms": ts_ms,
                            "key": label,
                            "vk": int(vk),
                            "down": down,
                        }
                    )
                    + "\n"
                )
            f.flush()
            time.sleep(interval)

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
