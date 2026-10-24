"""Synthetic fail-closed tests of the WineBot internal WinEvent adapter."""
import json
import threading
import unittest

from event_bridge import EventBridge


def event(kind, sequence, **extras):
    return json.dumps({
        "schema": "winebot.wine.event.v1",
        "kind": kind, "sequence": sequence, **extras,
    }, separators=(",", ":"))


class EventBridgeTests(unittest.TestCase):
    def test_happy_path_paged_readonly_cursor(self):
        b = EventBridge()
        self.assertTrue(b.ingest(event("ready", 0)))
        for n, kind in enumerate(("show", "location", "focus"), 1):
            self.assertTrue(b.ingest(event(kind, n)))
        r = b.observe(limit=2)
        self.assertEqual(r, {"state": "ready",
                            "events": [{"sequence": 1, "kind": "show"},
                                       {"sequence": 2, "kind": "location"}],
                            "next_cursor": 2})
        self.assertEqual(b.observe(after=2)["events"],
                         [{"sequence": 3, "kind": "focus"}])
        self.assertEqual(b.observe(after=3)["state"], "ready")

    def test_ready_required(self):
        b = EventBridge()
        self.assertFalse(b.ingest(event("show", 1)))
        self.assertEqual(b.observe()["state"], "unqualified")
        self.assertEqual(b.observe()["reason"], "missing_ready")

    def test_schema_rejects_identifiers(self):
        for extras in ({"hwnd": "secret"}, {"title": "secret"},
                       {"coordinates": [1, 2]}, {"pid": 7}):
            with self.subTest(extras=tuple(extras)):
                b = EventBridge()
                self.assertFalse(b.ingest(event("ready", 0, **extras)))
                self.assertEqual(b.observe()["events"], [])
                self.assertEqual(b.observe()["reason"], "invalid_schema")

    def test_invalid_source_events_and_gaps(self):
        for corrupt in (event("overflow", 1), event("show", 2),
                        event("ready", 1), event("show", True),
                        event("show", 1, text="secret"), "{", "x" * 257):
            with self.subTest(corrupt_type=type(corrupt).__name__):
                b = EventBridge()
                b.ingest(event("ready", 0))
                self.assertFalse(b.ingest(corrupt))
                self.assertEqual(b.observe()["state"], "unqualified")
                self.assertFalse(b.ingest(event("show", 1)))

    def test_wraparound_reports_gap(self):
        b = EventBridge(capacity=2)
        b.ingest(event("ready", 0))
        for n in range(1, 4):
            self.assertTrue(b.ingest(event("location", n)))
        self.assertEqual(b.observe(after=0)["state"], "history_gap")
        self.assertEqual([x["sequence"] for x in b.observe(after=1)["events"]],
                         [2, 3])

    def test_close_zeros_state(self):
        b = EventBridge()
        b.ingest(event("ready", 0))
        b.ingest(event("show", 1))
        b.close()
        self.assertEqual(b.observe()["events"], [])
        self.assertEqual(b.observe()["reason"], "closed")

    def test_no_cross_session_reuse(self):
        a, b = EventBridge(), EventBridge()
        a.ingest(event("ready", 0))
        b.ingest(event("ready", 0))
        a.ingest(event("show", 1))
        self.assertEqual(b.observe()["events"], [])
        self.assertEqual(len(a.observe()["events"]), 1)

    def test_invalid_cursor_and_capacity(self):
        b = EventBridge()
        for args in ({"after": -1}, {"after": True}, {"limit": 0},
                     {"limit": 1000}, {"limit": "1"}):
            self.assertEqual(b.observe(**args)["state"], "invalid_cursor")
        b.ingest(event("ready", 0))
        self.assertEqual(b.observe(after=30)["state"], "invalid_cursor")
        for capacity in (0, -1, 1025, True):
            with self.assertRaises(ValueError):
                EventBridge(capacity)

    def test_multireader_snapshot_stability(self):
        b = EventBridge()
        b.ingest(event("ready", 0))
        for n in range(1, 13):
            b.ingest(event("location", n))
        results = []
        threads = [threading.Thread(target=lambda: results.append(b.observe(limit=12)))
                   for _ in range(8)]
        for th in threads:
            th.start()
        for th in threads:
            th.join()
        self.assertEqual(len(results), 8)
        self.assertTrue(all(result == results[0] for result in results))


if __name__ == "__main__":
    unittest.main()
