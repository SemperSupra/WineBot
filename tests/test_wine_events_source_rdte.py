"""Synthetic-only trusted source lifecycle and cross-session qualification."""
import json
import unittest

from api.core.wine_events_rdte import SessionObserverRegistry
from api.core.wine_events_source_rdte import TrustedLocalEventSource


def record(kind, sequence, padding=0):
    text = json.dumps({
        "schema": "winebot.wine.event.v1",
        "kind": kind, "sequence": sequence,
    }, separators=(",", ":"))
    return text + (" " * padding) + "\n"


class LocalSourceTests(unittest.TestCase):
    def setUp(self):
        self.registry = SessionObserverRegistry()
        self.active = ["session-one"]
        self.broker = ["session-one"]
        self.src = self.source("session-one")

    def tearDown(self):
        self.src.stop()
        self.registry.clear()

    def source(self, session_id):
        return TrustedLocalEventSource(
            session_id, self.registry,
            lambda: self.active[0],
            lambda: self.broker[0],
        )

    def ready(self):
        self.assertTrue(self.src.feed_internal(record("ready", 0)))

    def test_source_is_unavailable_until_ready(self):
        self.assertEqual(self.registry.observe("session-one")["state"], "unavailable")
        self.ready()
        self.assertEqual(self.registry.observe("session-one")["state"], "ready")

    def test_feed_read_and_clear(self):
        self.ready()
        self.assertTrue(self.src.feed_internal(record("show", 1)))
        self.assertTrue(self.src.feed_internal(record("location", 2)))
        self.assertEqual(self.registry.observe("session-one", limit=1)["events"],
                         [{"kind": "show", "sequence": 1}])
        self.assertEqual(self.registry.observe("session-one", after=1)["events"],
                         [{"kind": "location", "sequence": 2}])
        self.src.stop()
        self.assertEqual(self.registry.observe("session-one")["state"], "unavailable")

    def test_missing_ready_is_fatal(self):
        self.assertFalse(self.src.feed_internal(record("show", 1)))
        self.assertTrue(self.src.stopped)
        self.assertEqual(self.registry.observe("session-one")["state"], "unavailable")

    def test_source_gap_and_extra_identifiers_fail_closed(self):
        self.ready()
        self.assertFalse(self.src.feed_internal(record("show", 2)))
        self.assertEqual(self.registry.observe("session-one")["events"], [])
        another = self.source("session-one")
        self.assertTrue(another.feed_internal(record("ready", 0)))
        contaminated = '{"schema":"winebot.wine.event.v1","kind":"show","sequence":1,"hwnd":"secret"}\n'
        self.assertFalse(another.feed_internal(contaminated))
        self.assertEqual(self.registry.observe("session-one")["state"], "unavailable")

    def test_handover_stops_and_erases(self):
        self.ready()
        self.assertTrue(self.src.feed_internal(record("show", 1)))
        self.active[0] = "session-two"
        self.assertFalse(self.src.feed_internal(record("location", 2)))
        self.assertTrue(self.src.stopped)
        self.assertEqual(self.registry.observe("session-one")["state"], "unavailable")

    def test_stale_source_cannot_clear_replacement_session(self):
        self.ready()
        self.active[0] = "session-two"
        self.broker[0] = "session-two"
        replacement = self.source("session-two")
        self.assertTrue(replacement.feed_internal(record("ready", 0)))
        self.assertTrue(replacement.feed_internal(record("show", 1)))
        self.src.stop()
        self.assertEqual(self.registry.observe("session-two")["events"],
                         [{"kind": "show", "sequence": 1}])
        replacement.stop()

    def test_broker_mismatch_and_error_fail_closed(self):
        self.broker[0] = "session-other"
        self.assertFalse(self.src.feed_internal(record("ready", 0)))
        self.assertTrue(self.src.stopped)
        invalid = TrustedLocalEventSource(
            "session-one", self.registry,
            lambda: (_ for _ in ()).throw(RuntimeError("fake")),
            lambda: "session-one",
        )
        self.assertFalse(invalid.feed_internal(record("ready", 0)))
        self.assertTrue(invalid.stopped)

    def test_reject_unterminated_oversized_and_bad_unicode(self):
        for invalid in (record("ready", 0).rstrip("\n"), "x" * 257,
                        "\ud800", 3):
            with self.subTest(invalid_type=type(invalid).__name__):
                probe = self.source("session-one")
                self.assertFalse(probe.feed_internal(invalid))
                self.assertTrue(probe.stopped)

    def test_event_count_limit_and_cleanup(self):
        self.ready()
        for n in range(1, 129):
            self.assertTrue(self.src.feed_internal(record("location", n)))
        self.assertFalse(self.src.feed_internal(record("location", 129)))
        self.assertEqual(self.registry.observe("session-one")["state"], "unavailable")

    def test_byte_budget_rejection(self):
        self.ready()
        for n in range(1, 129):
            if not self.src.feed_internal(record("location", n, padding=170)):
                self.assertTrue(self.src.stopped)
                self.assertEqual(self.registry.observe("session-one")["events"], [])
                break
        else:
            self.fail("byte budget never enforced")


if __name__ == "__main__":
    unittest.main()
