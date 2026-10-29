"""Actual service + registry + EventBridge handover regression, no Wine spawn.

Only the external owner is synthetic. The production classes and their
registry are imported unchanged, so a global clear or stale cleanup fails.
"""
import os
import threading
import unittest
from unittest.mock import patch

from api.core.wine_events_service_rdte import ObserverService
from api.core.wine_events_rdte import registry
from rdte.wine11.event_bridge import EventBridge

READY = '{"schema":"winebot.wine.event.v1","kind":"ready","sequence":0}\n'


def bridge_ready():
    b = EventBridge()
    assert b.ingest(READY)
    return b


class LocalSource:
    def __init__(self, session, bridge):
        self.session, self.bridge = session, bridge
        self.stopped = False

    def stop(self):
        if not self.stopped:
            self.stopped = True
            registry.clear_if_owner(self.session, self.bridge)


class OwnedFixture:
    """Never launches a process; faithfully exercises registry owner identity."""
    created = []

    def __init__(self, session, _registry, active, broker, *, prefix, display):
        assert _registry is registry
        self.session = session
        self.bridge = bridge_ready()
        self.source = LocalSource(session, self.bridge)
        self.ready = threading.Event()
        self.cancel = threading.Event()
        self.created.append(self)

    def run(self, deadline_seconds):
        assert deadline_seconds == 110.0
        registry.attach_internal(self.session, self.bridge)
        self.ready.set()
        if not self.cancel.wait(2.5):
            self.source.stop()
            return "timeout"
        self.source.stop()
        return "cancelled"

    def request_stop(self):
        self.cancel.set()


class ActualServiceHandover(unittest.TestCase):
    def setUp(self):
        registry.clear()
        OwnedFixture.created.clear()
        self.session = ["synthetic-s"]
        self.flags = patch.dict(os.environ, {
            "WINEBOT_WINE_EVENTS_RDTE_ENABLED": "1",
            "WINEBOT_WINE_EVENTS_PROCESS_RDTE_ENABLED": "1",
            "API_TOKEN": "synthetic-only",
            "WINEPREFIX": "/tmp",
        })
        self.flags.start()
        self.binary = patch(
            "api.core.wine_events_service_rdte.os.path.isfile",
            return_value=True,
        )
        self.binary.start()
        self.service = ObserverService(
            lambda: self.session[0], lambda: self.session[0],
            owner_factory=OwnedFixture,
        )

    def tearDown(self):
        self.service.shutdown()
        self.binary.stop()
        self.flags.stop()
        registry.clear()

    def launch(self):
        self.assertTrue(self.service.start_if_admitted())
        owner = OwnedFixture.created[-1]
        self.assertTrue(owner.ready.wait(2), "fixture owner missing ready")
        return owner

    def test_no_owner_shutdown_preserves_foreign_bridge(self):
        foreign = bridge_ready()
        registry.attach_internal("foreign", foreign)
        self.assertTrue(self.service.shutdown())
        self.assertEqual(registry.observe("foreign")["state"], "ready")
        self.assertFalse(self.service.start_if_admitted())

    def test_actual_service_stale_shutdown_cannot_erase_same_name_successor(self):
        old = self.launch()
        replacement = bridge_ready()
        registry.attach_internal("synthetic-s", replacement)
        self.assertTrue(self.service.shutdown())
        self.assertEqual(self.service.last_verdict, "cancelled")
        self.assertTrue(old.source.stopped)
        self.assertIsNot(old.bridge, replacement)
        self.assertEqual(registry.observe("synthetic-s")["state"], "ready")
        self.assertFalse(registry.clear_if_owner("synthetic-s", old.bridge))
        self.assertEqual(registry.observe("synthetic-s")["state"], "ready")

    def test_actual_service_handover_cannot_erase_other_session(self):
        old = self.launch()
        new = bridge_ready()
        self.session[0] = "successor"
        registry.attach_internal("successor", new)
        self.assertTrue(self.service.shutdown())
        self.assertTrue(old.source.stopped)
        self.assertEqual(registry.observe("successor")["state"], "ready")
        self.assertEqual(registry.observe("synthetic-s")["state"], "unavailable")

    def test_worker_cancellation_scoped_to_owner_and_idempotent(self):
        old = self.launch()
        self.assertTrue(self.service.shutdown())
        self.assertTrue(self.service.shutdown())
        self.assertEqual(self.service.last_verdict, "cancelled")
        self.assertTrue(old.source.stopped)
        self.assertEqual(registry.observe("synthetic-s")["state"], "unavailable")
        self.assertFalse(self.service.start_if_admitted())

    def test_owner_late_cleanup_fence_under_concurrent_replacement(self):
        old = self.launch()
        entered = threading.Event()
        release = threading.Event()

        def successor():
            entered.set()
            if not release.wait(2):
                return
            registry.attach_internal("synthetic-s", bridge_ready())

        t = threading.Thread(target=successor)
        t.start()
        self.assertTrue(entered.wait(1))
        release.set()
        t.join(timeout=2)
        self.assertFalse(t.is_alive())
        self.assertTrue(self.service.shutdown())
        self.assertTrue(old.source.stopped)
        self.assertEqual(registry.observe("synthetic-s")["state"], "ready")


if __name__ == "__main__":
    unittest.main()
