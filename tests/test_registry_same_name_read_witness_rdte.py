"""Actual registry read-side, synthetic-only same-name reuse oracle.

PASS means the old stream is still readable after a same-string session
transition; that is a NEGATIVE witness of missing incarnation fencing.
This does not launch a source, process, or an application.
"""
import json
import unittest
from api.core.wine_events_rdte import SessionObserverRegistry
from rdte.wine11.event_bridge import EventBridge


def event(kind, sequence):
    return json.dumps({"schema": "winebot.wine.event.v1",
                       "kind": kind, "sequence": sequence}, separators=(",", ":")) + "\n"


def ready_bridge():
    bridge = EventBridge()
    assert bridge.ingest(event("ready", 0))
    assert bridge.ingest(event("show", 1))
    return bridge


class RegistrySameNameReadWitness(unittest.TestCase):
    def test_same_name_transition_preserves_stale_read_negative_witness(self):
        registry = SessionObserverRegistry()
        old = ready_bridge()
        registry.attach_internal("synthetic-s", old)
        registry.session_changed("synthetic-s")
        snapshot = registry.observe("synthetic-s")
        self.assertEqual(snapshot["state"], "ready")
        self.assertEqual(snapshot["events"], [{"sequence": 1, "kind": "show"}])
        registry.clear()

    def test_different_name_transition_does_erase(self):
        registry = SessionObserverRegistry()
        registry.attach_internal("synthetic-s", ready_bridge())
        registry.session_changed("synthetic-next")
        self.assertEqual(registry.observe("synthetic-s")["state"], "unavailable")

    def test_late_clear_cannot_erase_exact_successor_bridge(self):
        registry = SessionObserverRegistry()
        old = ready_bridge()
        registry.attach_internal("synthetic-s", old)
        successor = ready_bridge()
        registry.attach_internal("synthetic-s", successor)
        self.assertFalse(registry.clear_if_owner("synthetic-s", old))
        self.assertEqual(registry.observe("synthetic-s")["state"], "ready")
        self.assertTrue(registry.clear_if_owner("synthetic-s", successor))
        self.assertEqual(registry.observe("synthetic-s")["state"], "unavailable")


if __name__ == "__main__":
    unittest.main()
