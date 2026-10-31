#!/usr/bin/env python3
"""Native Windows qualification of existing, fixture-limited WinEvent observer.

Uses two preexisting public synthetic C programs; no real app controls,
injection, screen capture, network access or binary publication.
"""
import json
import queue
import subprocess
import sys
import threading
import time

SCHEMA = "winebot.wine.event.v1"
KINDS = {
    "ready", "create", "show", "hide", "destroy", "focus",
    "location", "foreground", "overflow", "unsupported",
}
REQUIRED = {"show", "location", "destroy"}


def collect_pipe(pipe, records):
    try:
        for line in iter(pipe.readline, b""):
            records.put(line)
    finally:
        records.put(None)


def normalize(line):
    """Reject unbounded/non-schema data without echoing the raw content."""
    if not isinstance(line, bytes) or not 0 < len(line) <= 256:
        raise ValueError("invalid_line_bounds")
    try:
        item = json.loads(line.decode("utf-8"))
    except (ValueError, UnicodeError):
        raise ValueError("invalid_json_or_utf8") from None
    if (
        type(item) is not dict or set(item) != {"schema", "kind", "sequence"}
        or item["schema"] != SCHEMA or item["kind"] not in KINDS
        or type(item["sequence"]) is not int or not 0 <= item["sequence"] <= 129
    ):
        raise ValueError("unexpected_observer_schema")
    return item


def drain(records, target, duration):
    deadline = time.monotonic() + duration
    while time.monotonic() < deadline:
        try:
            line = records.get(timeout=min(0.2, max(0.001, deadline-time.monotonic())))
        except queue.Empty:
            continue
        if line is None:
            break
        target.append(normalize(line))


def main():
    if len(sys.argv) == 4 and sys.argv[1] == "--wine":
        observer, fixture = sys.argv[2:]
        observer_cmd, fixture_cmd = ["wine", observer], ["wine", fixture]
        runtime = "wine"
    elif len(sys.argv) == 3:
        observer, fixture = sys.argv[1:]
        observer_cmd, fixture_cmd = [observer], [fixture]
        runtime = "windows"
    else:
        raise ValueError("expected_fixture_executables_and_optional_wine_flag")
    records = queue.Queue(maxsize=150)
    events = []
    # Local process only; Windows session and desktop come from hosted runner.
    proc = subprocess.Popen(
        observer_cmd, stdin=subprocess.PIPE, stdout=subprocess.PIPE,
        stderr=subprocess.DEVNULL, bufsize=0,
    )
    reader = threading.Thread(target=collect_pipe, args=(proc.stdout, records), daemon=True)
    reader.start()
    try:
        deadline = time.monotonic() + 12.0
        while time.monotonic() < deadline:
            try:
                line = records.get(timeout=0.25)
            except queue.Empty:
                if proc.poll() is not None:
                    break
                continue
            if line is None:
                break
            event = normalize(line)
            events.append(event)
            if event["kind"] == "ready" and event["sequence"] == 0:
                break
            raise ValueError("observer_failed_ready")
        else:
            raise ValueError("observer_ready_timeout")
        if not events or events[0]["kind"] != "ready":
            raise ValueError("observer_not_ready")
        # The only active Windows application is the controlled fixture.
        completed = subprocess.run(
            fixture_cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
            timeout=16.0, check=False,
        )
        if completed.returncode != 0:
            raise ValueError("fixture_execution_failure")
        # Allow Wine's asynchronous event delivery additional bounded time.
        drain(records, events, 5.0 if runtime == "wine" else 1.0)
        if proc.poll() is not None:
            raise ValueError("observer_exited_before_control_stop")
        proc.stdin.write(b"Q")
        proc.stdin.flush()
        proc.stdin.close()
        proc.wait(timeout=8.0)
        reader.join(timeout=2.0)
        while True:
            try:
                line = records.get_nowait()
            except queue.Empty:
                break
            if line is not None:
                events.append(normalize(line))
        if proc.returncode != 0:
            raise ValueError("observer_control_exit_nonzero")
        if not 1 <= len(events) <= 130:
            raise ValueError("event_stream_bounds")
        sequences = [e["sequence"] for e in events]
        if sequences != list(range(len(events))):
            raise ValueError("noncontiguous_event_sequence")
        kinds = {e["kind"] for e in events[1:]}
        if "overflow" in kinds or "unsupported" in kinds:
            raise ValueError("observer_overflow_or_unsupported")
        if runtime == "wine":
            print("WITNESS: synthetic_wine_event_kinds=" + ",".join(sorted(kinds)))
            print("WITNESS: synthetic_wine_event_count=" + str(len(events) - 1))
        missing = REQUIRED - kinds
        if missing:
            raise ValueError("native_window_events_missing_" + "_".join(sorted(missing)))
        print("PASS: " + runtime + "_synthetic_fixture_win_events")
        print("PASS: contiguous_schema_bound_events=" + str(len(events) - 1))
        print("PASS: required_event_kinds=show,location,destroy")
        print("PASS: cooperative_private_Q_shutdown")
    finally:
        if proc.poll() is None:
            proc.kill()
        try:
            proc.wait(timeout=4)
        except subprocess.TimeoutExpired:
            pass
        if proc.stdin is not None and not proc.stdin.closed:
            proc.stdin.close()
        if proc.stdout is not None:
            proc.stdout.close()


if __name__ == "__main__":
    try:
        main()
    except (ValueError, OSError, subprocess.SubprocessError) as exc:
        print("FAIL: native_windows_fixture: " + str(exc), file=sys.stderr)
        sys.exit(1)
