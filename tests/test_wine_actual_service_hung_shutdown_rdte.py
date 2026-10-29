"""Actual ObserverService shutdown timeout contracts with no Wine or threads.

Only worker and owner dependencies are deterministic stubs. No external
process, session mutation or simulated successful cleanup is asserted.
"""
import unittest

from api.core.wine_events_service_rdte import ObserverService
from api.core.wine_events_rdte import registry
from rdte.wine11.event_bridge import EventBridge


def bridge_ready():
    b = EventBridge()
    if not b.ingest('{"schema":"winebot.wine.event.v1","kind":"ready","sequence":0}\n'):
        raise AssertionError("fixed synthetic bridge did not ready")
    return b


class FixedOwner:
    def __init__(self):
        self.stop_requests = 0

    def request_stop(self):
        self.stop_requests += 1


class FixedThread:
    def __init__(self, alive):
        self.alive = alive
        self.joins = []

    def join(self, timeout=None):
        self.joins.append(timeout)

    def is_alive(self):
        return self.alive


class ActualServiceHungShutdown(unittest.TestCase):
    def setUp(self):
        registry.clear()
        self.service = ObserverService(lambda: "synthetic-s",
                                       lambda: "synthetic-s")

    def tearDown(self):
        registry.clear()

    def test_hung_worker_reports_incomplete_without_erasing_foreign(self):
        foreign = bridge_ready()
        registry.attach_internal("successor", foreign)
        owner = FixedOwner()
        thread = FixedThread(alive=True)
        self.service._owner = owner
        self.service._thread = thread
        self.assertFalse(self.service.shutdown())
        self.assertEqual(owner.stop_requests, 1)
        self.assertEqual(thread.joins, [4.0])
        self.assertEqual(registry.observe("successor")["state"], "ready")
        self.assertTrue(self.service._stopped)

    def test_late_worker_completion_does_not_clear_successor(self):
        foreign = bridge_ready()
        registry.attach_internal("synthetic-s", foreign)
        owner = FixedOwner()
        thread = FixedThread(alive=True)
        self.service._owner = owner
        self.service._thread = thread
        self.assertFalse(self.service.shutdown())
        thread.alive = False
        self.assertTrue(self.service.shutdown())
        self.assertEqual(owner.stop_requests, 2)
        self.assertEqual(thread.joins, [4.0, 4.0])
        self.assertEqual(registry.observe("synthetic-s")["state"], "ready")

    def test_no_owner_no_worker_keeps_successor_and_returns_complete(self):
        foreign = bridge_ready()
        registry.attach_internal("successor", foreign)
        self.assertTrue(self.service.shutdown())
        self.assertEqual(registry.observe("successor")["state"], "ready")

    def test_shutdown_remains_closed_when_hung_owner_recovers(self):
        owner = FixedOwner()
        thread = FixedThread(alive=True)
        self.service._owner = owner
        self.service._thread = thread
        self.assertFalse(self.service.shutdown())
        thread.alive = False
        self.assertFalse(self.service.start_if_admitted())
        self.assertTrue(self.service.shutdown())


if __name__ == "__main__":
    unittest.main()
