#!/usr/bin/env python3
import argparse
import datetime
import json
import os
import re
import signal
import subprocess
import sys
import time
from typing import Any, Dict, Optional

TRACE_PID_FILE = "input_trace.pid"
TRACE_STATE_FILE = "input_trace.state"
TRACE_LOG_FILE = "logs/input_events.jsonl"
TRACE_STDERR_LOG = "logs/input_trace.log"
DEFAULT_LAYER = "x11"
DEFAULT_TOOL = "xinput"


EVENT_RE = re.compile(r"^EVENT type (\d+) \(([^)]+)\)")
DEVICE_RE = re.compile(r"^\s*device:\s*(\d+)\s+\((.+)\)")
DETAIL_RE = re.compile(r"^\s*detail:\s*(\d+)")
ROOT_RE = re.compile(r"^\s*root:\s*([0-9.+-]+)/([0-9.+-]+)")
FLAGS_RE = re.compile(r"^\s*flags:\s*(.*)")
MODIFIERS_RE = re.compile(r"^\s*modifiers:.*effective:\s*(\d+)")


def now_ts() -> Dict[str, Any]:
    epoch_ms = int(time.time() * 1000)
    return {
        "timestamp_epoch_ms": epoch_ms,
        "timestamp_utc": datetime.datetime.now(datetime.timezone.utc).isoformat(),
    }


def read_session_dir() -> Optional[str]:
    path = "/tmp/winebot_current_session"
    if not os.path.exists(path):
        return None
    try:
        with open(path, "r") as f:
            value = f.read().strip()
        return value or None
    except Exception:
        return None


def session_id_from_dir(session_dir: Optional[str]) -> Optional[str]:
    if not session_dir:
        return None
    return os.path.basename(session_dir)




def trace_state_path(session_dir: str) -> str:
    return os.path.join(session_dir, TRACE_STATE_FILE)


def trace_pid_path(session_dir: str) -> str:
    return os.path.join(session_dir, TRACE_PID_FILE)


def trace_log_path(session_dir: str) -> str:
    return os.path.join(session_dir, "logs", TRACE_LOG_FILE)


def trace_stderr_path(session_dir: str) -> str:
    return os.path.join(session_dir, "logs", TRACE_STDERR_LOG)


def write_state(session_dir: str, state: str) -> None:
    try:
        with open(trace_state_path(session_dir), "w") as f:
            f.write(state)
    except Exception:
        pass


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


def pid_running(pid: int) -> bool:
    try:
        os.kill(pid, 0)
        return True
    except ProcessLookupError:
        return False
    except PermissionError:
        return True


def input_event_from_xi2(
    current: Dict[str, Any],
    session_id: Optional[str],
    include_raw: bool,
    seq: int,
) -> Optional[Dict[str, Any]]:
    xi2_name = current.get("xi2_name")
    if not xi2_name:
        return None
    raw_event = False
    xi2_base = xi2_name
    if xi2_name.startswith("Raw"):
        raw_event = True
        xi2_base = xi2_name[3:]
    event_type = None
    if xi2_base == "Motion":
        event_type = "motion"
    elif xi2_base == "ButtonPress":
        event_type = "button_press"
    elif xi2_base == "ButtonRelease":
        event_type = "button_release"
    elif xi2_base == "KeyPress":
        event_type = "key_press"
    elif xi2_base == "KeyRelease":
        event_type = "key_release"
    else:
        return None

    payload: Dict[str, Any] = {
        "session_id": session_id,
        "event_id": f"{session_id}-{seq}",
        "seq": seq,
        "source": "x11",
        "layer": DEFAULT_LAYER,
        "type": event_type,  # Canonical name
        "event": event_type, # Backwards compat
        "origin": "unknown",
        "tool": DEFAULT_TOOL,
        "device": {
            "id": current.get("device_id"),
            "name": current.get("device_name"),
        },
        "detail": current.get("detail"),
        "xi2_type": xi2_name,
    }
    if raw_event:
        payload["xi2_raw"] = True
    
    ts = now_ts()
    payload.update(ts)
    payload["t_wall_ms"] = ts["timestamp_epoch_ms"]
    # t_mono_ms is hard to get from python without CLOCK_MONOTONIC sync, using wall for now
    payload["t_mono_ms"] = ts["timestamp_epoch_ms"] 

    if current.get("root_x") is not None and current.get("root_y") is not None:
        payload["x"] = current.get("root_x")
        payload["y"] = current.get("root_y")
    if event_type.startswith("button") and current.get("detail") is not None:
        payload["button"] = current.get("detail")
    if event_type.startswith("key") and current.get("detail") is not None:
        payload["keycode"] = current.get("detail")
    if current.get("flags"):
        payload["flags"] = current.get("flags")
    
    # Parse modifiers mask (Base X11: Shift=1, Lock=2, Ctrl=4, Mod1=8 ...)
    mods = []
    mask = current.get("modifiers_effective", 0)
    if mask & 1: mods.append("shift")
    if mask & 4: mods.append("ctrl")
    if mask & 8: mods.append("alt") # Mod1
    if mask & 64: mods.append("meta") # Mod4 often
    payload["modifiers"] = mods

    if include_raw and current.get("raw"):
        payload["raw"] = current.get("raw")
    return payload


def parse_xi2_stream(
    stream,
    session_id: Optional[str],
    include_raw: bool,
    motion_sample_ms: int,
):
    current: Optional[Dict[str, Any]] = None
    seq = 0
    last_motion_ms = 0

    for line in stream:
        line = line.rstrip("\n")
        if not line:
            continue
        event_match = EVENT_RE.match(line)
        if event_match:
            if current is not None:
                seq += 1
                event = input_event_from_xi2(current, session_id, include_raw, seq)
                if event:
                    if event["event"] == "motion" and motion_sample_ms > 0:
                        if event["timestamp_epoch_ms"] - last_motion_ms < motion_sample_ms:
                            event = None
                        else:
                            last_motion_ms = event["timestamp_epoch_ms"]
                    if event:
                        yield event
            current = {
                "xi2_type": int(event_match.group(1)),
                "xi2_name": event_match.group(2),
            }
            if include_raw:
                current["raw"] = [line]
            continue

        if current is None:
            continue
        if include_raw:
            current.setdefault("raw", []).append(line)

        device_match = DEVICE_RE.match(line)
        if device_match:
            current["device_id"] = int(device_match.group(1))
            current["device_name"] = device_match.group(2)
            continue
        detail_match = DETAIL_RE.match(line)
        if detail_match:
            current["detail"] = int(detail_match.group(1))
            continue
        root_match = ROOT_RE.match(line)
        if root_match:
            try:
                current["root_x"] = int(round(float(root_match.group(1))))
                current["root_y"] = int(round(float(root_match.group(2))))
            except ValueError:
                pass
            continue
        flags_match = FLAGS_RE.match(line)
        if flags_match:
            current["flags"] = flags_match.group(1).strip()
            continue
        mods_match = MODIFIERS_RE.match(line)
        if mods_match:
            current["modifiers_effective"] = int(mods_match.group(1))
            continue

    if current is not None:
        seq += 1
        event = input_event_from_xi2(current, session_id, include_raw, seq)
        if event:
            if event["event"] == "motion" and motion_sample_ms > 0:
                if event["timestamp_epoch_ms"] - last_motion_ms >= motion_sample_ms:
                    yield event
            else:
                yield event


def check_xinput_test_xi2() -> bool:
    try:
        result = subprocess.run(["xinput", "--help"], capture_output=True, text=True, check=False)
        help_text = (result.stdout or "") + (result.stderr or "")
        return "test-xi2" in help_text
    except Exception:
        return False


def run_trace(session_dir: str, include_raw: bool, motion_sample_ms: int) -> int:
    os.makedirs(os.path.join(session_dir, "logs"), exist_ok=True)
    log_path = trace_log_path(session_dir)
    stderr_path = trace_stderr_path(session_dir)
    session_id = session_id_from_dir(session_dir)

    if not check_xinput_test_xi2():
        with open(stderr_path, "a") as err:
            err.write("xinput test-xi2 not available. Input trace aborted.\n")
        return 1

    with open(stderr_path, "a") as err:
        proc = subprocess.Popen(
            ["xinput", "test-xi2", "--root"],
            stdout=subprocess.PIPE,
            stderr=err,
            text=True,
            bufsize=1,
        )

        if proc.stdout is None:
            err.write("Failed to open xinput stdout.\n")
            return 1

        write_pid(session_dir, proc.pid)
        write_state(session_dir, "running")

        stop_requested = False

        def handle_signal(_sig, _frame):
            nonlocal stop_requested
            stop_requested = True
            try:
                proc.terminate()
            except Exception:
                pass

        signal.signal(signal.SIGTERM, handle_signal)
        signal.signal(signal.SIGINT, handle_signal)

        try:
            with open(log_path, "a") as logf:
                for event in parse_xi2_stream(proc.stdout, session_id, include_raw, motion_sample_ms):
                    if stop_requested:
                        break
                    logf.write(json.dumps(event) + "\n")
                    logf.flush()
        finally:
            try:
                proc.terminate()
            except Exception:
                pass
            try:
                proc.wait(timeout=2)
            except Exception:
                pass
            write_state(session_dir, "stopped")

    return 0


def stop_trace(session_dir: str) -> int:
    pid = read_pid(session_dir)
    if not pid:
        return 0
    if not pid_running(pid):
        return 0
    try:
        os.kill(pid, signal.SIGTERM)
        return 0
    except Exception:
        return 1


def main():
    parser = argparse.ArgumentParser(description="Trace X11 input events to a JSONL log.")
    subparsers = parser.add_subparsers(dest="command")

    start_p = subparsers.add_parser("start", help="Start input tracing")
    start_p.add_argument("--session-dir", default="")
    start_p.add_argument("--include-raw", action="store_true")
    start_p.add_argument("--motion-sample-ms", type=int, default=0)

    stop_p = subparsers.add_parser("stop", help="Stop input tracing")
    stop_p.add_argument("--session-dir", default="")

    status_p = subparsers.add_parser("status", help="Show input trace status")
    status_p.add_argument("--session-dir", default="")

    args = parser.parse_args()
    session_dir = args.session_dir or read_session_dir()
    if not session_dir:
        print("No session directory provided and /tmp/winebot_current_session missing.", file=sys.stderr)
        return 1

    if args.command == "start":
        return run_trace(session_dir, args.include_raw, args.motion_sample_ms)
    if args.command == "stop":
        return stop_trace(session_dir)
    if args.command == "status":
        pid = read_pid(session_dir)
        running = pid_running(pid) if pid else False
        state = None
        try:
            with open(trace_state_path(session_dir), "r") as f:
                state = f.read().strip() or None
        except Exception:
            pass
        payload = {
            "session_dir": session_dir,
            "pid": pid,
            "running": running,
            "state": state,
            "log_path": trace_log_path(session_dir),
        }
        print(json.dumps(payload))
        return 0

    parser.print_help()
    return 1


if __name__ == "__main__":
    sys.exit(main())
