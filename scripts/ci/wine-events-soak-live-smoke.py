#!/usr/bin/env python3
"""Bounded 70s Wine/Xvfb synthetic observer soak; no host telemetry.

Reads only cgroup-v2 resource counters INSIDE the capped disposable test
container. Neither process RSS nor user hardware identity is sampled. Only
fixed PASS/FAIL phases are printed; event frames stay in transient memory.
"""
import os
import signal
import subprocess
import threading
import time

from api.core.wine_events_process_rdte import OwnedWineEventProcess
from api.core.wine_events_rdte import SessionObserverRegistry
from scripts.ci.wine_events_soak_bounds import (
    ResourceUnqualified, assess_envelope, read_cgroup_v2,
)

SESSION = "synthetic-soak-session"
FIXTURE = "/opt/winebot/rdte/win_event_fixture.exe"
DURATION = 70.0
QUIET_END = 20.0


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


def stop_fixture(proc):
    if proc is None:
        return
    if proc.poll() is None:
        try:
            os.killpg(proc.pid, signal.SIGTERM)
        except OSError:
            proc.terminate()
        try:
            proc.wait(timeout=1)
        except subprocess.TimeoutExpired:
            try:
                os.killpg(proc.pid, signal.SIGKILL)
            except OSError:
                proc.kill()
            proc.wait(timeout=1)


def run_soak():
    registry = SessionObserverRegistry()
    identity = [SESSION]
    owner = OwnedWineEventProcess(
        SESSION, registry, lambda: identity[0], lambda: identity[0],
        prefix=os.environ["WINEPREFIX"], display=os.environ["DISPLAY"],
    )
    results = []
    thread = threading.Thread(
        target=lambda: results.append(owner.run(deadline_seconds=94.0)),
        name="synthetic-soak-owner",
    )
    fixtures = []
    samples = []
    cursor = 0
    count = 0
    kinds = set()
    t0 = None

    def observe_and_sample():
        nonlocal cursor, count
        elapsed = time.monotonic() - t0
        samples.append(read_cgroup_v2(elapsed=elapsed))
        snap = registry.observe(SESSION, after=cursor, limit=128)
        if snap.get("state") != "ready":
            return "soak_stream_unavailable"
        records = snap["events"]
        for item in records:
            if item["sequence"] != cursor + 1:
                return "soak_sequence_gap"
            cursor = item["sequence"]
            count += 1
            kinds.add(item["kind"])
        if snap["next_cursor"] != cursor:
            return "soak_cursor_mismatch"
        return "ok"

    def sample_until(relative_deadline):
        while time.monotonic() - t0 < relative_deadline:
            verdict = observe_and_sample()
            if verdict != "ok":
                return verdict
            if not thread.is_alive():
                return "soak_observer_early_exit"
            time.sleep(0.8)
        return "ok"

    try:
        thread.start()
        readiness_deadline = time.monotonic() + 13
        while time.monotonic() < readiness_deadline:
            if registry.observe(SESSION)["state"] == "ready":
                break
            if not thread.is_alive():
                return "soak_observer_missing_ready"
            time.sleep(0.05)
        else:
            return "soak_observer_missing_ready"

        t0 = time.monotonic()
        outcome = sample_until(QUIET_END)
        if outcome != "ok":
            return outcome
        if count != 0:
            return "soak_unexpected_quiet_events"

        for _ in range(4):
            proc = subprocess.Popen(
                ["wine", FIXTURE], stdin=subprocess.DEVNULL,
                stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                env=fixture_env(), close_fds=True, start_new_session=True,
            )
            fixtures.append(proc)
            finish = time.monotonic() + 9
            while proc.poll() is None and time.monotonic() < finish:
                outcome = observe_and_sample()
                if outcome != "ok":
                    return outcome
                if not thread.is_alive():
                    return "soak_observer_early_exit"
                time.sleep(0.5)
            if proc.poll() is None:
                return "soak_fixture_timeout"
            if proc.returncode != 0:
                return "soak_fixture_nonzero"
            outcome = sample_until(time.monotonic() - t0 + 1.2)
            if outcome != "ok":
                return outcome

        if count < 8 or not {"show", "location"}.issubset(kinds):
            return "soak_event_coverage"
        outcome = sample_until(DURATION)
        if outcome != "ok":
            return outcome

        # The clocks and counts belong to THIS bounded fixture and cgroup;
        # only the enum verdict, never raw container or host metrics, exits.
        envelope = assess_envelope(samples, quiet_stop_seconds=QUIET_END)
        if envelope != "ok":
            return envelope
        print("PASS: soak_70s_live_event_continuity", flush=True)
        print("PASS: soak_cgroup_v2_resource_envelope", flush=True)
        result = "ok"
    except ResourceUnqualified:
        return "soak_metrics_unavailable"
    except (OSError, ValueError, subprocess.SubprocessError):
        return "soak_process_exception"
    finally:
        owner.request_stop()
        thread.join(timeout=5)
        for proc in fixtures:
            stop_fixture(proc)
        cleanup_ok = not thread.is_alive() and owner.source.stopped and (
            registry.observe(SESSION)["state"] == "unavailable"
        )
        if not cleanup_ok:
            # Do not report a false success if cleanup never settled.
            print("FAIL: soak_cleanup_not_erased", flush=True)
        else:
            print("PASS: soak_owner_stop_and_erase", flush=True)
        registry.clear()
    return result if cleanup_ok else "soak_cleanup_not_erased"


def main():
    result = run_soak()
    if result != "ok":
        allowed = frozenset({
            "soak_stream_unavailable", "soak_sequence_gap",
            "soak_cursor_mismatch", "soak_observer_early_exit",
            "soak_observer_missing_ready", "soak_unexpected_quiet_events",
            "soak_fixture_timeout", "soak_fixture_nonzero",
            "soak_event_coverage", "soak_insufficient_duration",
            "soak_bad_quiet_window", "soak_invalid_measurement",
            "soak_oom_kill", "soak_memory_ceiling", "soak_pid_ceiling",
            "soak_memory_growth", "soak_cpu_accounting",
            "soak_insufficient_quiet", "soak_busy_quiet",
            "soak_metrics_unavailable", "soak_process_exception",
            "soak_cleanup_not_erased",
        })
        print("FAIL: " + (result if result in allowed
                          else "soak_unqualified"), flush=True)
        return 1
    print("PASS: soak_qualified", flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
