#!/usr/bin/env python3
"""Real Wine/Xvfb fixed-fixture two-session cursor handover (RDTE only).

No runtime API, external ingress, arbitrary Windows apps, raw event output,
screenshots, logs, credentials, or automatic same-session observer restart.
"""
import copy
import os
import signal
import subprocess
import threading
import time

from api.core.wine_events_process_rdte import OwnedWineEventProcess
from api.core.wine_events_rdte import SessionObserverRegistry
from rdte.wine11.generation_cursor_rdte import GenerationCursorView

FIXTURE = "/opt/winebot/rdte/win_event_fixture.exe"
SESSION_A = "synthetic-generation-A"
SESSION_B = "synthetic-generation-B"


def emit(code):
    print("PASS: " + code, flush=True)


def fixture_env():
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


def start_owner(session, registry, identity, owners):
    owner = OwnedWineEventProcess(
        session, registry, lambda: identity[0], lambda: identity[0],
        prefix=os.environ["WINEPREFIX"], display=os.environ["DISPLAY"],
    )
    terminal = []
    thread = threading.Thread(
        target=lambda: terminal.append(owner.run(deadline_seconds=42.0)),
        name="synthetic-generation-owner",
    )
    owners.append((owner, thread, terminal))
    thread.start()
    deadline = time.monotonic() + 15
    while time.monotonic() < deadline:
        if registry.observe(session)["state"] == "ready":
            return owner, thread, terminal
        if not thread.is_alive():
            return None
        time.sleep(0.08)
    return None


def capture_fixture(session, view, fixtures):
    fixture = subprocess.Popen(
        ["wine", FIXTURE],
        stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL, env=fixture_env(),
        start_new_session=True,
    )
    fixtures.append(fixture)
    deadline = time.monotonic() + 12
    while time.monotonic() < deadline:
        snap = view.read(session, view.initial_cursor())
        if snap["state"] != "ready":
            return None
        kinds = {e["kind"] for e in snap["events"]}
        if {"show", "location"}.issubset(kinds):
            if fixture.wait(timeout=10) == 0:
                return snap
            return None
        if fixture.poll() is not None:
            return None
        time.sleep(0.075)
    return None


def stop_owner(owner, thread, terminal, registry, session):
    owner.request_stop()
    thread.join(timeout=5)
    return (
        not thread.is_alive()
        and terminal == ["cancelled"]
        and owner.source.stopped
        and owner._process is None
        and registry.observe(session)["state"] == "unavailable"
    )


def exercise(registry, identity, owners, fixtures, views):
    started = start_owner(SESSION_A, registry, identity, owners)
    if started is None:
        return "first_observer_not_ready"
    owner_a, thread_a, terminal_a = started
    view_a = GenerationCursorView(SESSION_A, owner_a.source._bridge)
    views.append(view_a)
    first = capture_fixture(SESSION_A, view_a, fixtures)
    if first is None or first["events"][0]["sequence"] != 1:
        return "first_wine_events_missing"
    emit("first_wine_generation_one")
    old_cursor = view_a.read(
        SESSION_A, view_a.initial_cursor(), limit=1,
    )["next_cursor"]
    if old_cursor is None or old_cursor["sequence"] != 1:
        return "first_cursor_not_bound"
    if not stop_owner(owner_a, thread_a, terminal_a, registry, SESSION_A):
        return "first_owner_cleanup"
    emit("first_owner_cancel_and_erase")

    # This is an independently admitted NEW session, not a same-session restart.
    identity[0] = SESSION_B
    started = start_owner(SESSION_B, registry, identity, owners)
    if started is None:
        return "new_session_not_ready"
    owner_b, thread_b, terminal_b = started
    view_b = GenerationCursorView(SESSION_B, owner_b.source._bridge)
    views.append(view_b)

    # Old session source/view stop cannot clear a separately owned replacement.
    view_a.close()
    owner_a.source.stop()
    if registry.observe(SESSION_B)["state"] != "ready":
        return "stale_owner_cleared_replacement"
    second = capture_fixture(SESSION_B, view_b, fixtures)
    if second is None or second["events"][0]["sequence"] != 1:
        return "second_wine_events_missing"
    emit("second_wine_sequence_reset")

    if view_b.read(SESSION_B, old_cursor)["state"] != "session_mismatch":
        return "old_session_cursor_accepted"
    # If a buggy caller rewrites only the session string, the generation
    # discriminator STILL blocks the previous source's sequence=1.
    wrong_generation = copy.deepcopy(old_cursor)
    wrong_generation["session"] = SESSION_B
    if view_b.read(SESSION_B, wrong_generation)["state"] != "stale_generation":
        return "old_generation_cursor_accepted"
    emit("cross_session_and_generation_rejected")

    # Distinct readers advance separately; no hidden actor-specific path.
    for audience in ("human", "automation", "agent"):
        snapshot = view_b.read(SESSION_B, view_b.initial_cursor(), limit=1)
        if snapshot["state"] != "ready" or len(snapshot["events"]) != 1:
            return "reader_snapshot_inconsistent"
        if snapshot["next_cursor"]["sequence"] != 1:
            return "reader_cursor_invalid"
    emit("three_audience_independent_read")
    if not stop_owner(owner_b, thread_b, terminal_b, registry, SESSION_B):
        return "new_owner_cleanup"
    if view_b.read(SESSION_B, view_b.initial_cursor())["state"] != "unqualified":
        # Source was closed by its genuine owner before a stale view read.
        return "new_stream_not_invalidated"
    emit("new_session_stop_and_erase")
    return "ok"


def cleanup(registry, owners, fixtures, views):
    clean = True
    for owner, thread, _ in owners:
        owner.request_stop()
        if thread.ident is not None:
            thread.join(timeout=5)
        clean = clean and not thread.is_alive()
    for view in views:
        view.close()
    for proc in fixtures:
        if proc.poll() is None:
            try:
                os.killpg(proc.pid, signal.SIGTERM)
                proc.wait(timeout=2)
            except (OSError, subprocess.TimeoutExpired):
                try:
                    os.killpg(proc.pid, signal.SIGKILL)
                    proc.wait(timeout=2)
                except (OSError, subprocess.TimeoutExpired):
                    clean = False
    registry.clear()
    return clean


def main():
    registry = SessionObserverRegistry()
    identity = [SESSION_A]
    owners, fixtures, views = [], [], []
    try:
        outcome = exercise(registry, identity, owners, fixtures, views)
    except Exception:
        # Preserve only allowlisted failure type; never emit exception contents.
        outcome = "handover_unqualified"
    if not cleanup(registry, owners, fixtures, views):
        outcome = "cleanup_failed"
    if outcome != "ok":
        print("FAIL: " + outcome, flush=True)
        return 1
    emit("generation_handover_qualified")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
