import argparse
import datetime
import json
import os
import re
import selectors
import signal
import time
import subprocess
import time
from typing import Optional

DEFAULT_LAYER = "x11"
DEFAULT_SOURCE = "x11_core"
DEFAULT_TOOL = "xinput-core"

MOTION_RE = re.compile(r"^motion a\\[0\\]=([-0-9.]+) a\\[1\\]=([-0-9.]+)")
BUTTON_RE = re.compile(r"^button (press|release) (\\d+)")
KEY_RE = re.compile(r"^key (press|release) (\\d+)")


def trace_log_path(session_dir: str) -> str:
    return os.path.join(session_dir, "logs", "input_events_x11_core.jsonl")


def trace_stderr_path(session_dir: str) -> str:
    return os.path.join(session_dir, "logs", "input_trace_x11_core.stderr")


def trace_pid_path(session_dir: str) -> str:
    return os.path.join(session_dir, "input_trace_x11_core.pid")


def trace_state_path(session_dir: str) -> str:
    return os.path.join(session_dir, "input_trace_x11_core.state")


def write_pid(session_dir: str, pid: int) -> None:
    try:
        with open(trace_pid_path(session_dir), "w") as f:
            f.write(str(pid))
    except Exception:
        pass


def read_pid(session_dir: str) -> Optional[int]:
    try:
        with open(trace_pid_path(session_dir), "r") as f:
            return int(f.read().strip())
    except Exception:
        return None


def write_state(session_dir: str, state: str) -> None:
    try:
        with open(trace_state_path(session_dir), "w") as f:
            f.write(state)
    except Exception:
        pass


def session_id_from_dir(session_dir: str) -> Optional[str]:
    try:
        name = os.path.basename(session_dir.rstrip("/"))
        return name or None
    except Exception:
        return None


def now_payload(session_id: Optional[str]) -> dict:
    return {
        "timestamp_epoch_ms": int(time.time() * 1000),
        "timestamp_utc": datetime.datetime.now(datetime.timezone.utc).isoformat(),
        "session_id": session_id,
    }


def check_xinput_test() -> bool:
    try:
        result = subprocess.run(["xinput", "--help"], capture_output=True, text=True, check=False)
        return result.returncode == 0
    except Exception:
        return False


def parse_stream(stream, session_id: Optional[str], motion_sample_ms: int):
    seq = 0
    last_motion_ms = 0
    for line in stream:
        line = line.strip()
        if not line:
            continue
        event = None
        payload = {
            "source": DEFAULT_SOURCE,
            "layer": DEFAULT_LAYER,
            "origin": "unknown",
            "tool": DEFAULT_TOOL,
        }
        motion_match = MOTION_RE.match(line)
        if motion_match:
            event = "motion"
            try:
                x = int(round(float(motion_match.group(1))))
                y = int(round(float(motion_match.group(2))))
                payload["x"] = x
                payload["y"] = y
            except Exception:
                pass
        else:
            button_match = BUTTON_RE.match(line)
            if button_match:
                event = "button_press" if button_match.group(1) == "press" else "button_release"
                payload["button"] = int(button_match.group(2))
            else:
                key_match = KEY_RE.match(line)
                if key_match:
                    event = "key_press" if key_match.group(1) == "press" else "key_release"
                    payload["keycode"] = int(key_match.group(2))

        if not event:
            continue

        ts_payload = now_payload(session_id)
        payload.update(ts_payload)
        payload["event"] = event
        payload["seq"] = seq
        seq += 1

        if event == "motion" and motion_sample_ms > 0:
            if payload["timestamp_epoch_ms"] - last_motion_ms < motion_sample_ms:
                continue
            last_motion_ms = payload["timestamp_epoch_ms"]

        yield payload


def run_xinput(args):
    try:
        result = subprocess.run(["xinput"] + args, capture_output=True, text=True, check=False)
        return result.returncode, result.stdout or "", result.stderr or ""
    except Exception:
        return 1, "", ""


def resolve_device_id(name: str) -> Optional[int]:
    code, stdout, _stderr = run_xinput(["list", "--id-only", name])
    if code == 0:
        value = stdout.strip()
        if value.isdigit():
            return int(value)
    return None


def find_master_devices() -> tuple:
    pointer_name = "Virtual core pointer"
    keyboard_name = "Virtual core keyboard"
    fallback_pointer_name = "Xvfb mouse"
    fallback_keyboard_name = "Xvfb keyboard"

    pointer_id = resolve_device_id(pointer_name)
    keyboard_id = resolve_device_id(keyboard_name)
    fallback_pointer_id = resolve_device_id(fallback_pointer_name)
    fallback_keyboard_id = resolve_device_id(fallback_keyboard_name)

    code, stdout, _stderr = run_xinput(["list", "--short"])
    if code == 0:
        lines = stdout.splitlines()
        for line in lines:
            if pointer_id is None and "master pointer" in line:
                match = re.search(r"id=(\d+)", line)
                if match:
                    pointer_id = int(match.group(1))
                    pointer_name = line.split("id=")[0].strip()
            if keyboard_id is None and "master keyboard" in line:
                match = re.search(r"id=(\d+)", line)
                if match:
                    keyboard_id = int(match.group(1))
                    keyboard_name = line.split("id=")[0].strip()
            if fallback_pointer_id is None and fallback_pointer_name in line:
                match = re.search(r"id=(\d+)", line)
                if match:
                    fallback_pointer_id = int(match.group(1))
            if fallback_keyboard_id is None and fallback_keyboard_name in line:
                match = re.search(r"id=(\d+)", line)
                if match:
                    fallback_keyboard_id = int(match.group(1))

    pointer_info = {
        "id": pointer_id,
        "name": pointer_name,
        "fallback_id": fallback_pointer_id,
        "fallback_name": fallback_pointer_name,
    }
    keyboard_info = {
        "id": keyboard_id,
        "name": keyboard_name,
        "fallback_id": fallback_keyboard_id,
        "fallback_name": fallback_keyboard_name,
    }
    return pointer_info, keyboard_info


def run_trace(session_dir: str, motion_sample_ms: int) -> int:
    os.makedirs(os.path.join(session_dir, "logs"), exist_ok=True)
    log_path = trace_log_path(session_dir)
    stderr_path = trace_stderr_path(session_dir)
    session_id = session_id_from_dir(session_dir)

    if not check_xinput_test():
        with open(stderr_path, "a") as err:
            err.write("xinput test not available. x11 core trace aborted.\n")
        return 1

    pointer_info, keyboard_info = find_master_devices()
    if not pointer_info.get("id") and not keyboard_info.get("id"):
        with open(stderr_path, "a") as err:
            err.write("Failed to locate master pointer/keyboard via xinput list.\n")
        return 1

    with open(stderr_path, "a") as err:
        err.write(
            "Resolved devices: "
            f"pointer id={pointer_info.get('id')} name={pointer_info.get('name')} "
            f"fallback_id={pointer_info.get('fallback_id')} fallback_name={pointer_info.get('fallback_name')}; "
            f"keyboard id={keyboard_info.get('id')} name={keyboard_info.get('name')} "
            f"fallback_id={keyboard_info.get('fallback_id')} fallback_name={keyboard_info.get('fallback_name')}\n"
        )
        err.flush()
        procs = []
        selector = selectors.DefaultSelector()

        def start_device(label: str, info: dict):
            candidates = []
            device_id = info.get("id")
            device_name = info.get("name")
            fallback_id = info.get("fallback_id")
            fallback_name = info.get("fallback_name")

            prefer_fallback = False
            if device_name and "Virtual core" in device_name and fallback_id is not None:
                prefer_fallback = True

            if prefer_fallback and fallback_id is not None:
                candidates.append(str(fallback_id))
            if device_id is not None:
                candidates.append(str(device_id))
            if device_name:
                candidates.append(device_name)
            if not prefer_fallback and fallback_id is not None:
                candidates.append(str(fallback_id))
            if fallback_name:
                candidates.append(fallback_name)

            if not candidates:
                return

            def launch(spec: str):
                proc = subprocess.Popen(
                    ["xinput", "test", spec],
                    stdout=subprocess.PIPE,
                    stderr=err,
                    text=True,
                    bufsize=1,
                )
                if proc.stdout is None:
                    return None
                procs.append(proc)
                selector.register(
                    proc.stdout,
                    selectors.EVENT_READ,
                    {
                        "label": label,
                        "id": device_id,
                        "name": device_name,
                        "proc": proc,
                        "spec": spec,
                    }
                )
                return proc

            for idx, spec in enumerate(candidates):
                err.write(f"xinput test candidate '{spec}' for {label}.\n")
                err.flush()
                proc = launch(spec)
                if not proc:
                    continue
                time.sleep(0.2)
                if proc.poll() is None:
                    if idx > 0:
                        err.write(f"xinput test '{spec}' succeeded after fallback.\n")
                        err.flush()
                    return
                err.write(f"xinput test '{spec}' exited early; trying next candidate.\n")
                err.flush()
                try:
                    selector.unregister(proc.stdout)
                except Exception:
                    pass
                try:
                    procs.remove(proc)
                except ValueError:
                    pass

        start_device("pointer", pointer_info)
        start_device("keyboard", keyboard_info)

        if not procs:
            err.write("Failed to start xinput test for any device.\n")
            return 1

        write_pid(session_dir, os.getpid())
        write_state(session_dir, "running")

        stop_requested = False

        def handle_signal(_sig, _frame):
            nonlocal stop_requested
            stop_requested = True
            for proc in procs:
                try:
                    proc.terminate()
                except Exception:
                    pass

        signal.signal(signal.SIGTERM, handle_signal)
        signal.signal(signal.SIGINT, handle_signal)

        seq = 0
        last_motion_ms = 0

        try:
            with open(log_path, "a") as logf:
                while not stop_requested and selector.get_map():
                    for key, _ in selector.select(timeout=0.2):
                        stream = key.fileobj
                        meta = key.data
                        line = stream.readline()
                        if not line:
                            try:
                                selector.unregister(stream)
                            except Exception:
                                pass
                            continue
                        line = line.strip()
                        if not line:
                            continue
                        event = None
                        payload = {
                            "source": DEFAULT_SOURCE,
                            "layer": DEFAULT_LAYER,
                            "origin": "unknown",
                            "tool": DEFAULT_TOOL,
                            "device": {"id": meta.get("id"), "name": meta.get("name"), "spec": meta.get("spec")},
                        }
                        motion_match = MOTION_RE.match(line)
                        if motion_match:
                            event = "motion"
                            try:
                                x = int(round(float(motion_match.group(1))))
                                y = int(round(float(motion_match.group(2))))
                                payload["x"] = x
                                payload["y"] = y
                            except Exception:
                                pass
                        else:
                            button_match = BUTTON_RE.match(line)
                            if button_match:
                                event = "button_press" if button_match.group(1) == "press" else "button_release"
                                payload["button"] = int(button_match.group(2))
                            else:
                                key_match = KEY_RE.match(line)
                                if key_match:
                                    event = "key_press" if key_match.group(1) == "press" else "key_release"
                                    payload["keycode"] = int(key_match.group(2))

                        if not event:
                            continue

                        payload.update(now_payload(session_id))
                        payload["event"] = event
                        payload["seq"] = seq
                        seq += 1

                        if event == "motion" and motion_sample_ms > 0:
                            if payload["timestamp_epoch_ms"] - last_motion_ms < motion_sample_ms:
                                continue
                            last_motion_ms = payload["timestamp_epoch_ms"]

                        logf.write(json.dumps(payload) + "\n")
                        logf.flush()
        finally:
            for proc in procs:
                try:
                    proc.terminate()
                except Exception:
                    pass
            for proc in procs:
                try:
                    proc.wait(timeout=2)
                except Exception:
                    pass
            write_state(session_dir, "stopped")

    return 0


def stop_trace(session_dir: str) -> int:
    pid = read_pid(session_dir)
    if pid is None:
        return 1
    try:
        os.kill(pid, signal.SIGTERM)
    except Exception:
        pass
    write_state(session_dir, "stopped")
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description="X11 core input trace")
    subparsers = parser.add_subparsers(dest="command", required=True)

    start_p = subparsers.add_parser("start")
    start_p.add_argument("--session-dir", required=True)
    start_p.add_argument("--motion-sample-ms", type=int, default=0)

    stop_p = subparsers.add_parser("stop")
    stop_p.add_argument("--session-dir", required=True)

    args = parser.parse_args()

    if args.command == "start":
        return run_trace(args.session_dir, args.motion_sample_ms)
    if args.command == "stop":
        return stop_trace(args.session_dir)
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
