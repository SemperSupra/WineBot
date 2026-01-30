#!/usr/bin/env python3
import argparse
import os
import subprocess
import sys
import time


def run_command(args, check=True, capture_output=False):
    return subprocess.run(
        args,
        check=check,
        capture_output=capture_output,
        text=True,
    )


def find_window(title, timeout, interval):
    deadline = time.time() + timeout
    while time.time() < deadline:
        result = run_command(
            ["xdotool", "search", "--name", title],
            check=False,
            capture_output=True,
        )
        if result.returncode == 0 and result.stdout.strip():
            window_ids = result.stdout.split()
            return window_ids[-1]
        time.sleep(interval)
    return None


def list_windows(title):
    result = run_command(
        ["xdotool", "search", "--name", title],
        check=False,
        capture_output=True,
    )
    if result.returncode != 0 or not result.stdout.strip():
        return []
    return result.stdout.split()


def find_new_window(title, existing_ids, timeout, interval):
    deadline = time.time() + timeout
    while time.time() < deadline:
        for window_id in list_windows(title):
            if window_id not in existing_ids:
                return window_id
        time.sleep(interval)
    return None


def activate_window(window_id, attempts=5, interval=0.2):
    for _ in range(attempts):
        run_command(["xdotool", "windowactivate", "--sync", window_id], check=False)
        active = run_command(
            ["xdotool", "getactivewindow"],
            check=False,
            capture_output=True,
        )
        if active.stdout.strip() == window_id:
            return True
        time.sleep(interval)
    return False


def send_keys(window_id, *keys):
    run_command(["xdotool", "key", "--window", window_id, *keys])


def type_text(window_id, text, delay):
    run_command(["xdotool", "type", "--window", window_id, "--delay", str(delay), text])


def to_windows_path(path_value):
    result = run_command(["winepath", "-w", path_value], capture_output=True)
    return result.stdout.strip()


def decode_contents(raw_bytes):
    if raw_bytes.startswith(b"\xff\xfe") or raw_bytes.startswith(b"\xfe\xff"):
        return raw_bytes.decode("utf-16")
    if raw_bytes.startswith(b"\xef\xbb\xbf"):
        return raw_bytes.decode("utf-8-sig")
    try:
        return raw_bytes.decode("utf-8")
    except UnicodeDecodeError:
        return raw_bytes.decode("cp1252")


def normalize_text(text_value):
    return text_value.replace("\r\n", "\n")


def parse_args():
    parser = argparse.ArgumentParser()
    parser.add_argument("--text", required=True)
    parser.add_argument("--output", default="/tmp/notepad_test.txt")
    parser.add_argument("--window-title", default="Notepad")
    parser.add_argument("--timeout", type=int, default=30)
    parser.add_argument("--save-timeout", type=int, default=20)
    parser.add_argument("--delay", type=int, default=50)
    parser.add_argument("--launch", action="store_true")
    parser.add_argument("--retry-interval", type=float, default=0.5)
    return parser.parse_args()


def main():
    args = parse_args()

    output_dir = os.path.dirname(args.output)
    if output_dir:
        os.makedirs(output_dir, exist_ok=True)
    # Ensure the file exists so Notepad can open it without triggering Save As.
    with open(args.output, "wb") as handle:
        handle.write(b"")

    existing_ids = list_windows(args.window_title)
    existing_save_ids = list_windows("Save As")
    windows_path = to_windows_path(args.output)
    if args.launch:
        subprocess.Popen(["wine", "notepad.exe", windows_path])
        window_id = find_new_window(
            args.window_title,
            set(existing_ids),
            args.timeout,
            args.retry_interval,
        )
    else:
        window_id = find_window(args.window_title, args.timeout, args.retry_interval)
    if window_id is None:
        print(f"Could not find a window matching '{args.window_title}'", file=sys.stderr)
        return 1

    activate_window(window_id)
    send_keys(window_id, "ctrl+a", "BackSpace")
    type_text(window_id, args.text, args.delay)
    send_keys(window_id, "ctrl+s")

    save_window = find_new_window(
        "Save As",
        set(existing_save_ids),
        5,
        args.retry_interval,
    )
    if save_window is None:
        send_keys(window_id, "alt+f", "a")
        save_window = find_new_window(
            "Save As",
            set(existing_save_ids),
            5,
            args.retry_interval,
        )
    if save_window is None:
        save_window = find_window("Save As", 5, args.retry_interval)

    if save_window is not None:
        activate_window(save_window)
        send_keys(save_window, "alt+n")
        send_keys(save_window, "ctrl+a")
        type_text(save_window, windows_path, args.delay)
        send_keys(save_window, "Return")

        confirm_window = find_window("Confirm Save As", 5, args.retry_interval)
        if confirm_window is None:
            confirm_window = find_window("Confirm Save", 5, args.retry_interval)
        if confirm_window is not None:
            activate_window(confirm_window)
            send_keys(confirm_window, "alt+y")

    expected = normalize_text(args.text)
    deadline = time.time() + args.save_timeout
    decoded = ""
    while time.time() < deadline:
        if os.path.exists(args.output):
            with open(args.output, "rb") as handle:
                contents = handle.read()
            decoded = normalize_text(decode_contents(contents))
            if decoded == expected:
                print(f"File written and verified at {args.output}")
                return 0
        time.sleep(args.retry_interval)

    if not os.path.exists(args.output):
        print("File was not created by Notepad", file=sys.stderr)
        return 1
    print("File contents did not match expected text", file=sys.stderr)
    return 2


if __name__ == "__main__":
    sys.exit(main())
