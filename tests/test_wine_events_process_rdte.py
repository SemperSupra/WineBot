"""Bounded subprocess owner: only synthetic Python children in unit tests.

Production command stays fixed to the pre-qualified fixture-class Win32 .exe.
"""
import json
import os
import subprocess
import sys
import threading
import time
import unittest
from unittest.mock import patch

from api.core.wine_events_rdte import SessionObserverRegistry
from api.core.wine_events_process_rdte import OwnedWineEventProcess

SESSION = "synthetic-session"
COMMAND = ["wine", "/opt/winebot/rdte/win_event_observer.exe"]


def event(kind, sequence):
    return json.dumps({
        "schema": "winebot.wine.event.v1",
        "kind": kind,
        "sequence": sequence,
    }, separators=(",", ":"))


def child_script(mode):
    if mode == "normal":
        return ("import sys,time\n"
                "print(" + repr(event("ready", 0)) + ", flush=True)\n"
                "print(" + repr(event("show", 1)) + ", flush=True)\n"
                "print(" + repr(event("location", 2)) + ", flush=True)\n"
                "time.sleep(0.25)\n")
    if mode == "slow":
        return ("import time\n"
                "print(" + repr(event("ready", 0)) + ", flush=True)\n"
                "time.sleep(4)\n")
    if mode == "exit_bad":
        return ("import sys\n"
                "print(" + repr(event("ready", 0)) + ", flush=True)\n"
                "sys.exit(7)\n")
    if mode == "no_ready":
        return "import sys; sys.exit(0)\n"
    if mode == "gap":
        return ("print(" + repr(event("ready", 0)) + ", flush=True)\n"
                "print(" + repr(event("location", 2)) + ", flush=True)\n")
    if mode == "partial":
        return "import sys;sys.stdout.write(" + repr(event("ready", 0).rstrip("\n")) + ");sys.stdout.flush()\n"
    if mode == "oversized":
        return "print('x'*300, flush=True)\n"
    if mode == "secret":
        return "import os,sys;sys.exit(9 if os.getenv('API_TOKEN') else 0)\n"
    raise AssertionError("test mode not declared")


class OwnedProcessTests(unittest.TestCase):
    def setUp(self):
        self.registry = SessionObserverRegistry()
        self.active = [SESSION]
        self.broker = [SESSION]

    def tearDown(self):
        self.registry.clear()

    def make_owner(self, mode, **kwargs):
        script = child_script(mode)
        def spawn(command, **options):
            self.assertEqual(command, COMMAND)
            self.assertIs(options["stderr"], subprocess.DEVNULL)
            self.assertIs(options["stdin"], subprocess.DEVNULL)
            self.assertEqual(options["env"]["WINEDEBUG"], "-all")
            self.assertEqual(options["env"]["WINEPREFIX"], "/tmp/synthetic-prefix")
            self.assertNotIn("API_TOKEN", options["env"])
            return subprocess.Popen([sys.executable, "-u", "-c", script], **options)
        return OwnedWineEventProcess(
            SESSION, self.registry,
            lambda: self.active[0],
            lambda: self.broker[0],
            prefix="/tmp/synthetic-prefix",
            spawn=spawn,
            **kwargs,
        )

    def test_clean_eof_and_erasure(self):
        owner = self.make_owner("normal")
        self.assertEqual(owner.run(deadline_seconds=2.5), "clean_eof")
        self.assertTrue(owner.source.stopped)
        self.assertEqual(self.registry.observe(SESSION)["state"], "unavailable")
        self.assertEqual(owner.run(), "already_started")

    def test_visible_during_run_but_not_after_eof(self):
        owner = self.make_owner("normal")
        results = []
        thread = threading.Thread(
            target=lambda: results.append(owner.run(deadline_seconds=3)))
        thread.start()
        observed = False
        for _ in range(120):
            snapshot = self.registry.observe(SESSION)
            if snapshot["state"] == "ready" and len(snapshot["events"]) >= 2:
                observed = True
                self.assertEqual({x["kind"] for x in snapshot["events"]},
                                 {"show", "location"})
                break
            time.sleep(0.01)
        thread.join(timeout=6)
        self.assertFalse(thread.is_alive())
        self.assertTrue(observed, "synthetic events were not observable while child was alive")
        self.assertEqual(results, ["clean_eof"])
        self.assertEqual(self.registry.observe(SESSION)["state"], "unavailable")

    def test_clean_restart_new_lease_and_instance(self):
        first = self.make_owner("normal")
        self.assertEqual(first.run(deadline_seconds=2), "clean_eof")
        second = self.make_owner("normal")
        self.assertEqual(second.run(deadline_seconds=2), "clean_eof")
        self.assertEqual(self.registry.observe(SESSION)["state"], "unavailable")

    def test_timeout_kills_child_and_clears(self):
        owner = self.make_owner("slow")
        self.assertEqual(owner.run(deadline_seconds=0.3), "timeout")
        self.assertEqual(self.registry.observe(SESSION)["state"], "unavailable")
        self.assertTrue(owner.source.stopped)

    def test_nonzero_exit_not_normalized_to_success(self):
        owner = self.make_owner("exit_bad")
        self.assertEqual(owner.run(deadline_seconds=3), "nonzero_exit")
        self.assertEqual(self.registry.observe(SESSION)["state"], "unavailable")

    def test_missing_ready(self):
        owner = self.make_owner("no_ready")
        self.assertEqual(owner.run(deadline_seconds=3), "missing_ready")

    def test_malformed_and_gap(self):
        owner = self.make_owner("gap")
        self.assertEqual(owner.run(deadline_seconds=3), "source_rejected")
        self.assertEqual(self.registry.observe(SESSION)["state"], "unavailable")

    def test_partial_line_rejected(self):
        owner = self.make_owner("partial")
        self.assertEqual(owner.run(deadline_seconds=3), "truncated_event")

    def test_oversized_line_rejected_without_logs(self):
        owner = self.make_owner("oversized")
        self.assertEqual(owner.run(deadline_seconds=3), "line_oversized")

    def test_handover_during_run_kills_child_and_erases(self):
        owner = self.make_owner("slow")
        result = []
        th = threading.Thread(target=lambda: result.append(owner.run(deadline_seconds=3)))
        th.start()
        for _ in range(100):
            if self.registry.observe(SESSION)["state"] == "ready":
                break
            time.sleep(0.01)
        self.active[0] = "session-next"
        th.join(timeout=4)
        self.assertFalse(th.is_alive())
        self.assertEqual(result, ["session_handover"])
        self.assertEqual(self.registry.observe(SESSION)["state"], "unavailable")

    def test_unadmitted_session_prevents_launch(self):
        self.broker[0] = "wrong"
        def forbidden(*args, **kwargs):
            self.fail("spawn must not run for a stale session")
        o = OwnedWineEventProcess(
            SESSION, self.registry, lambda: self.active[0],
            lambda: self.broker[0], prefix="/tmp/synthetic-prefix",
            spawn=forbidden,
        )
        self.assertEqual(o.run(deadline_seconds=1), "session_handover")

    def test_invalid_deadline_and_prefix_rejected(self):
        owner = self.make_owner("normal")
        self.assertEqual(owner.run(deadline_seconds=23), "invalid_deadline")
        with self.assertRaises(ValueError):
            OwnedWineEventProcess(
                SESSION, self.registry, lambda: SESSION, lambda: SESSION,
                prefix="relative",
            )

    def test_api_token_not_in_child_environment(self):
        owner = self.make_owner("secret")
        with patch.dict(os.environ, {"API_TOKEN": "secret-synthetic-test"}):
            self.assertEqual(owner.run(deadline_seconds=3), "missing_ready")


if __name__ == "__main__":
    unittest.main()
