#!/usr/bin/env python3
"""Bounded native WinEvent overflow qualification using only synthetic windows."""
import json
import queue
import subprocess
import sys
import threading

EXPECTED = {"schema", "kind", "sequence"}
SCHEMA = "winebot.wine.event.v1"


def read_records(pipe, dest):
    try:
        for line in iter(pipe.readline, b""):
            dest.put(line)
    finally:
        dest.put(None)


def decode(line):
    if not isinstance(line, bytes) or not 0 < len(line) <= 256:
        raise ValueError("line_outside_bounds")
    try:
        d = json.loads(line.decode("utf-8"))
    except (ValueError, UnicodeError):
        raise ValueError("invalid_record_encoding") from None
    if (type(d) is not dict or set(d) != EXPECTED or d["schema"] != SCHEMA
            or type(d["sequence"]) is not int or type(d["kind"]) is not str):
        raise ValueError("invalid_record_schema")
    if len(d["kind"]) > 24:
        raise ValueError("unbounded_kind")
    return d


def main():
    if len(sys.argv) != 3:
        raise ValueError("expected_observer_and_storm_fixture")
    observer, fixture = sys.argv[1:]
    records = queue.Queue()
    proc = subprocess.Popen(
        [observer], stdin=subprocess.PIPE, stdout=subprocess.PIPE,
        stderr=subprocess.DEVNULL, bufsize=0,
    )
    reader = threading.Thread(target=read_records, args=(proc.stdout, records), daemon=True)
    reader.start()
    try:
        try:
            first = records.get(timeout=10)
        except queue.Empty:
            raise ValueError("observer_ready_timeout") from None
        if first is None or decode(first) != {
            "schema": SCHEMA, "kind": "ready", "sequence": 0,
        }:
            raise ValueError("observer_not_ready")
        run = subprocess.run([fixture], stdout=subprocess.DEVNULL,
                             stderr=subprocess.DEVNULL, timeout=22, check=False)
        if run.returncode != 0:
            raise ValueError("storm_fixture_failed")
        try:
            result = proc.wait(timeout=12)
        except subprocess.TimeoutExpired:
            raise ValueError("observer_failed_to_stop_on_overflow") from None
        reader.join(timeout=2)
        events = [decode(first)]
        while True:
            try:
                line = records.get(timeout=2)
            except queue.Empty:
                raise ValueError("stdout_not_closed") from None
            if line is None:
                break
            events.append(decode(line))
        if result != 6:
            raise ValueError("incorrect_overflow_exit_status")
        if len(events) != 130:
            raise ValueError("incorrect_bounded_record_count")
        if [e["sequence"] for e in events] != list(range(130)):
            raise ValueError("noncontiguous_overflow_sequence")
        if events[-1]["kind"] != "overflow":
            raise ValueError("terminal_overflow_missing")
        if any(e["kind"] == "overflow" for e in events[:-1]):
            raise ValueError("early_overflow")
        print("PASS: synthetic_win32_storm_overflow")
        print("PASS: ready_0_plus_128_bounded_events_plus_terminal_overflow_129")
        print("PASS: observer_exits_with_overflow_class_6")
    finally:
        if proc.poll() is None:
            proc.kill()
        try:
            proc.wait(timeout=5)
        except subprocess.TimeoutExpired:
            pass
        if proc.stdin is not None:
            proc.stdin.close()
        if proc.stdout is not None:
            proc.stdout.close()


if __name__ == "__main__":
    try:
        main()
    except (ValueError, OSError, subprocess.SubprocessError) as exc:
        print("FAIL: synthetic_overflow: " + str(exc), file=sys.stderr)
        sys.exit(1)
