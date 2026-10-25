"""Synthetic hostile lifecycle qualification; no real user apps or network."""
import json
import os
import subprocess
import sys
import threading
import time
import unittest
from unittest.mock import patch

from api.core.wine_events_process_rdte import OwnedWineEventProcess
from api.core.wine_events_rdte import SessionObserverRegistry
from api.core.wine_events_service_rdte import ObserverService
from api.core.wine_events_source_rdte import TrustedLocalEventSource


SESSION = "rdte-long-synthetic"
COMMAND = ["wine", "/opt/winebot/rdte/win_event_observer.exe"]


def frame(kind, number, padding=0):
    data = {"schema": "winebot.wine.event.v1", "kind": kind, "sequence": number}
    return json.dumps(data, separators=(",", ":")) + (" " * padding) + "\n"


class SyntheticLifecycleTests(unittest.TestCase):
    def setUp(self):
        self.registry = SessionObserverRegistry()
        self.active = [SESSION]
        self.broker = [SESSION]

    def tearDown(self):
        self.registry.clear()

    def source(self):
        return TrustedLocalEventSource(
            SESSION, self.registry, lambda: self.active[0], lambda: self.broker[0],
        )

    def owner(self, script):
        def spawn(argv, **kwargs):
            self.assertEqual(argv, COMMAND)
            self.assertIs(kwargs["stdin"], subprocess.PIPE)
            self.assertIs(kwargs["stderr"], subprocess.DEVNULL)
            self.assertNotIn("API_TOKEN", kwargs["env"])
            self.assertNotIn("GITHUB_TOKEN", kwargs["env"])
            self.assertTrue(kwargs["start_new_session"])
            return subprocess.Popen([sys.executable, "-u", "-c", script], **kwargs)
        return OwnedWineEventProcess(
            SESSION, self.registry, lambda: self.active[0],
            lambda: self.broker[0], prefix="/tmp/synthetic-prefix", spawn=spawn,
        )

    def test_terminal_overflow_fails_closed_and_scrubs(self):
        source = self.source()
        self.assertTrue(source.feed_internal(frame("ready", 0)))
        for i in range(1, 129):
            self.assertTrue(source.feed_internal(frame("location", i)))
        self.assertFalse(source.feed_internal(frame("overflow", 129)))
        self.assertTrue(source.stopped)
        self.assertEqual(source.failure_class, "source_overflow")
        self.assertEqual(self.registry.observe(SESSION)["state"], "unavailable")

    def test_missing_sequence_is_not_silent_loss(self):
        source = self.source()
        self.assertTrue(source.feed_internal(frame("ready", 0)))
        self.assertFalse(source.feed_internal(frame("location", 2)))
        self.assertEqual(source.failure_class, "source_gap")
        self.assertEqual(self.registry.observe(SESSION)["state"], "unavailable")

    def test_byte_limit_erases_without_disclosing_frames(self):
        source = self.source()
        self.assertTrue(source.feed_internal(frame("ready", 0)))
        for i in range(1, 130):
            if not source.feed_internal(frame("location", i, padding=180)):
                break
        else:
            self.fail("byte cap was not reached")
        self.assertLessEqual(source._bytes, source.MAX_BYTES)
        self.assertTrue(source.stopped)
        self.assertEqual(self.registry.observe(SESSION)["state"], "unavailable")

    def test_readers_independent_and_bounded(self):
        source = self.source()
        self.assertTrue(source.feed_internal(frame("ready", 0)))
        for i in range(1, 9):
            self.assertTrue(source.feed_internal(frame("show", i)))
        outputs = []
        threads = [threading.Thread(
            target=lambda: outputs.append(self.registry.observe(SESSION, after=0, limit=3))
        ) for _ in range(2)]
        for t in threads:
            t.start()
        for t in threads:
            t.join(timeout=2)
            self.assertFalse(t.is_alive())
        self.assertEqual(len(outputs), 2)
        for result in outputs:
            self.assertEqual(result["state"], "ready")
            self.assertEqual([x["sequence"] for x in result["events"]], [1, 2, 3])
            self.assertEqual(result["next_cursor"], 3)
        self.assertEqual(self.registry.observe(SESSION, after=3, limit=3)["next_cursor"], 6)
        source.stop()

    def test_stop_during_callback_with_private_quit_byte(self):
        script = (
            "import sys,time\n"
            "print(" + repr(frame("ready", 0).strip()) + ",flush=True)\n"
            "print(" + repr(frame("show", 1).strip()) + ",flush=True)\n"
            "assert sys.stdin.buffer.read(1)==b'Q'\n"
        )
        owner = self.owner(script)
        outcomes = []
        t = threading.Thread(target=lambda: outcomes.append(owner.run(deadline_seconds=4)))
        t.start()
        for _ in range(200):
            if self.registry.observe(SESSION)["state"] == "ready":
                break
            time.sleep(0.01)
        self.assertEqual(self.registry.observe(SESSION)["state"], "ready")
        owner.request_stop()
        t.join(timeout=4)
        self.assertFalse(t.is_alive())
        self.assertEqual(outcomes, ["cancelled"])
        self.assertTrue(owner.source.stopped)
        self.assertEqual(self.registry.observe(SESSION)["state"], "unavailable")

    def test_delayed_ready_and_cancel_before_first_callback(self):
        script = "import time;time.sleep(2)\n"
        owner = self.owner(script)
        results = []
        t = threading.Thread(target=lambda: results.append(owner.run(deadline_seconds=5)))
        t.start()
        time.sleep(0.05)
        owner.request_stop()
        t.join(timeout=4)
        self.assertFalse(t.is_alive())
        self.assertEqual(results, ["cancelled"])
        self.assertEqual(self.registry.observe(SESSION)["state"], "unavailable")

    def test_nonzero_exit_is_never_clean_eof(self):
        script = "print(" + repr(frame("ready", 0).strip()) + ",flush=True)\nraise SystemExit(7)\n"
        owner = self.owner(script)
        self.assertEqual(owner.run(deadline_seconds=3), "nonzero_exit")
        self.assertEqual(self.registry.observe(SESSION)["state"], "unavailable")

    def test_changed_owner_is_not_allowed_to_replay(self):
        source = self.source()
        self.assertTrue(source.feed_internal(frame("ready", 0)))
        self.assertTrue(source.feed_internal(frame("show", 1)))
        self.active[0] = "next-session"
        self.assertFalse(source.feed_internal(frame("show", 2)))
        self.assertEqual(self.registry.observe(SESSION)["state"], "unavailable")

    def test_stale_owner_cleanup_cannot_erase_successor(self):
        older = self.source()
        self.assertTrue(older.feed_internal(frame("ready", 0)))
        older_bridge = older._bridge
        self.active[0] = "next"
        self.broker[0] = "next"
        successor = TrustedLocalEventSource(
            "next", self.registry, lambda: self.active[0], lambda: self.broker[0],
        )
        self.assertTrue(successor.feed_internal(frame("ready", 0)))
        self.assertTrue(successor.feed_internal(frame("show", 1)))
        self.assertFalse(self.registry.clear_if_owner(SESSION, older_bridge))
        older.stop()
        self.assertEqual(self.registry.observe("next")["state"], "ready")
        successor.stop()

    def test_service_renews_once_only_then_refuses_unbounded_restarts(self):
        class FakeOwner:
            def __init__(self, *args, **kwargs):
                self.exit = threading.Event()
                self.source = type("FakeSource", (), {"stop": lambda _s: None})()
            def run(self, deadline_seconds):
                self.exit.wait(2)
                return "cancelled"
            def request_stop(self):
                self.exit.set()

        svc = ObserverService(
            lambda: SESSION, lambda: SESSION, owner_factory=FakeOwner,
        )
        env = {
            "WINEBOT_WINE_EVENTS_RDTE_ENABLED": "1",
            "WINEBOT_WINE_EVENTS_PROCESS_RDTE_ENABLED": "1",
            "API_TOKEN": "synthetic-fixture-token",
            "WINEPREFIX": "/tmp",
            "DISPLAY": ":99",
        }
        with patch.dict(os.environ, env), patch(
            "api.core.wine_events_service_rdte.os.path.isfile", return_value=True
        ):
            try:
                self.assertTrue(svc.start_if_admitted())
                self.assertFalse(svc.start_if_admitted())
                svc._owner.request_stop()
                svc._thread.join(timeout=2)
                self.assertFalse(svc.start_if_admitted())  # cooldown
                time.sleep(1.05)
                self.assertTrue(svc.start_if_admitted())
                svc._owner.request_stop()
                svc._thread.join(timeout=2)
                time.sleep(1.05)
                self.assertFalse(svc.start_if_admitted())  # exhausted budget
            finally:
                self.assertTrue(svc.shutdown())


if __name__ == "__main__":
    unittest.main()
