#!/usr/bin/env python3
"""Actual Wine fixture-only stop/overflow falsification; no emitted frames."""
import json
import os
import selectors
import signal
import subprocess
import threading
import time

from api.core.wine_events_process_rdte import OwnedWineEventProcess
from api.core.wine_events_rdte import SessionObserverRegistry

OBSERVER = "/opt/winebot/rdte/win_event_observer.exe"
BURST = "/opt/winebot/rdte/win_event_burst_fixture.exe"
SESSION = "synthetic-burst-session"


def environment():
    return {
        "PATH": "/usr/local/bin:/usr/bin:/bin",
        "HOME": os.environ.get("HOME", "/home/winebot"),
        "DISPLAY": os.environ["DISPLAY"],
        "WINEPREFIX": os.environ["WINEPREFIX"],
        "WINEARCH": "win64",
        "WINEDEBUG": "-all",
        "WINEDLLOVERRIDES": "mscoree,mshtml=",
        "XDG_RUNTIME_DIR": os.environ["XDG_RUNTIME_DIR"],
    }


def stop_child(child):
    if child is None:
        return
    if child.poll() is None:
        try:
            os.killpg(child.pid, signal.SIGTERM)
        except OSError:
            child.terminate()
        try:
            child.wait(timeout=2)
        except subprocess.TimeoutExpired:
            try:
                os.killpg(child.pid, signal.SIGKILL)
            except OSError:
                child.kill()
            child.wait(timeout=2)
    for channel in (child.stdin, child.stdout):
        if channel is not None:
            channel.close()


def orderly_stop_probe():
    child = None
    selector = selectors.DefaultSelector()
    try:
        child = subprocess.Popen(
            ["wine", OBSERVER], stdin=subprocess.PIPE, stdout=subprocess.PIPE,
            stderr=subprocess.DEVNULL, env=environment(), close_fds=True,
            start_new_session=True, bufsize=0,
        )
        selector.register(child.stdout, selectors.EVENT_READ)
        ready = False
        buffer = bytearray()
        cutoff = time.monotonic() + 15
        while not ready and time.monotonic() < cutoff:
            if not selector.select(timeout=0.2):
                continue
            chunk = os.read(child.stdout.fileno(), 256)
            if not chunk:
                return False
            buffer.extend(chunk)
            if len(buffer) > 256:
                return False
            if b"\n" in buffer:
                line, _, _ = buffer.partition(b"\n")
                try:
                    event = json.loads(line)
                except (ValueError, UnicodeError):
                    return False
                ready = event == {
                    "schema": "winebot.wine.event.v1",
                    "kind": "ready",
                    "sequence": 0,
                }
                if not ready:
                    return False
        if not ready:
            return False
        child.stdin.write(b"Q")
        child.stdin.flush()
        return child.wait(timeout=5) == 0
    except (OSError, ValueError, subprocess.SubprocessError):
        return False
    finally:
        selector.close()
        stop_child(child)


def burst_probe():
    registry = SessionObserverRegistry()
    owner = OwnedWineEventProcess(
        SESSION, registry, lambda: SESSION, lambda: SESSION,
        prefix=os.environ["WINEPREFIX"], display=os.environ["DISPLAY"],
    )
    verdicts = []
    runner = threading.Thread(
        target=lambda: verdicts.append(owner.run(deadline_seconds=18)),
        name="synthetic-event-owner",
    )
    child = None
    try:
        runner.start()
        cutoff = time.monotonic() + 12
        while time.monotonic() < cutoff:
            if registry.observe(SESSION)["state"] == "ready":
                break
            if not runner.is_alive():
                return "observer_missing_ready"
            time.sleep(0.05)
        else:
            return "observer_missing_ready"
        child = subprocess.Popen(
            ["wine", BURST], stdin=subprocess.DEVNULL,
            stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
            env=environment(), close_fds=True, start_new_session=True,
        )
        try:
            fixture_result = child.wait(timeout=9)
        except subprocess.TimeoutExpired:
            return "fixture_timeout"
        if fixture_result != 0:
            return "fixture_nonzero"
        runner.join(timeout=8)
        if runner.is_alive():
            return "observer_no_terminal_overflow"
        if verdicts != ["source_overflow"]:
            # Return one fixed class, never a raw event or unexpected error.
            return "observer_no_terminal_overflow"
        if registry.observe(SESSION)["state"] != "unavailable":
            return "overflow_not_erased"
        return "ok"
    finally:
        owner.request_stop()
        runner.join(timeout=5)
        registry.clear()
        stop_child(child)


def main():
    if not orderly_stop_probe():
        print("FAIL: wine_direct_orderly_stop", flush=True)
        return 1
    print("PASS: wine_direct_orderly_stop", flush=True)
    verdict = burst_probe()
    if verdict != "ok":
        fixed = frozenset({
            "observer_missing_ready", "fixture_timeout", "fixture_nonzero",
            "observer_no_terminal_overflow", "overflow_not_erased",
        })
        print("FAIL: " + (verdict if verdict in fixed else "burst_unqualified"), flush=True)
        return 1
    print("PASS: wine_real_callback_overflow_scrub", flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
