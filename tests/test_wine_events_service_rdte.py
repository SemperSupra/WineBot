"""No-network opt-in service owner lifecycle/lease boundary tests."""
import os
import threading
import time
import unittest
from unittest.mock import patch

from api.core.wine_events_service_rdte import ObserverService

TOKEN = "synthetic-service-token"


class FakeOwner:
    created = []

    def __init__(self, session, registry, active, broker, *, prefix, display, incarnation, validate_incarnation):
        if not validate_incarnation(session, incarnation):
            raise ValueError("synthetic_fixture_invalid_receipt")
        self.incarnation = incarnation
        self.session = session
        self.prefix = prefix
        self.display = display
        self.stopped = threading.Event()
        self.started = threading.Event()
        self.source = type("LocalSource", (), {"stop": lambda _: None})()
        self.created.append(self)

    def run(self, deadline_seconds):
        self.started.set()
        self.stopped.wait(3)
        return "cancelled"

    def request_stop(self):
        self.stopped.set()


class ObserverServiceTests(unittest.TestCase):
    def setUp(self):
        FakeOwner.created.clear()
        self.active = ["rdte-session"]
        self.broker = ["rdte-session"]
        self.service = ObserverService(
            lambda: self.active[0],
            lambda: self.broker[0],
            owner_factory=FakeOwner,
            admit_observer=lambda session: (session, "synthetic-service-incarnation"),
            validate_incarnation=lambda session, receipt: (
                session in ("rdte-session", "rdte-next")
                and receipt == "synthetic-service-incarnation"
            ),
        )
        self.flags = patch.dict(os.environ, {
            "WINEBOT_WINE_EVENTS_RDTE_ENABLED": "1",
            "WINEBOT_WINE_EVENTS_PROCESS_RDTE_ENABLED": "1",
            "API_TOKEN": TOKEN,
            "WINEPREFIX": "/tmp",
            "DISPLAY": ":99",
        })
        self.flags.start()
        self.path = patch("api.core.wine_events_service_rdte.os.path.isfile", return_value=True)
        self.path.start()

    def tearDown(self):
        self.service.shutdown()
        self.path.stop()
        self.flags.stop()

    def test_admitted_starts_one_fixed_owner_and_stops(self):
        self.assertTrue(self.service.start_if_admitted())
        child = FakeOwner.created[0]
        self.assertTrue(child.started.wait(2))
        self.assertEqual(child.session, "rdte-session")
        self.assertEqual(child.prefix, "/tmp")
        self.assertEqual(child.incarnation, "synthetic-service-incarnation")
        self.assertFalse(self.service.start_if_admitted())
        self.assertTrue(self.service.shutdown())
        self.assertTrue(child.stopped.is_set())
        self.assertFalse(self.service.start_if_admitted())

    def test_two_feature_flags_and_api_token_required(self):
        for key in ("WINEBOT_WINE_EVENTS_RDTE_ENABLED",
                    "WINEBOT_WINE_EVENTS_PROCESS_RDTE_ENABLED", "API_TOKEN"):
            with self.subTest(key=key):
                with patch.dict(os.environ, {key: ""}):
                    self.assertFalse(self.service.start_if_admitted())
        self.assertEqual(len(FakeOwner.created), 0)

    def test_binary_not_present_is_unavailable(self):
        with patch("api.core.wine_events_service_rdte.os.path.isfile", return_value=False):
            self.assertFalse(self.service.start_if_admitted())
        self.assertEqual(len(FakeOwner.created), 0)

    def test_mismatched_active_broker_is_unavailable(self):
        self.broker[0] = "not-matching"
        self.assertFalse(self.service.start_if_admitted())
        self.assertEqual(len(FakeOwner.created), 0)

    def test_callback_exception_denies(self):
        bad = ObserverService(
            lambda: (_ for _ in ()).throw(ValueError("synthetic")),
            lambda: "rdte-session", owner_factory=FakeOwner)
        self.assertFalse(bad.start_if_admitted())
        self.assertTrue(bad.shutdown())

    def test_no_prefix_does_not_spawn(self):
        with patch.dict(os.environ, {"WINEPREFIX": "/synthetic/nonexistent-prefix"}):
            self.assertFalse(self.service.start_if_admitted())
        self.assertEqual(len(FakeOwner.created), 0)

    def test_new_session_allowed_only_after_old_owner_ends(self):
        self.assertTrue(self.service.start_if_admitted())
        first = FakeOwner.created[0]
        self.assertTrue(first.started.wait(2))
        self.active[0] = "rdte-next"
        self.broker[0] = "rdte-next"
        self.assertFalse(self.service.start_if_admitted())
        first.request_stop()
        self.service._thread.join(timeout=2)
        self.assertFalse(self.service._thread.is_alive())
        self.assertTrue(self.service.start_if_admitted())
        self.assertEqual(FakeOwner.created[1].session, "rdte-next")
        self.assertTrue(self.service.shutdown())

    def test_owner_factory_failure_cannot_mutate_registry(self):
        def broken(*args, **kwargs):
            raise ValueError("synthetic factory refusal")
        svc = ObserverService(lambda: "rdte-session", lambda: "rdte-session",
                              owner_factory=broken)
        self.assertFalse(svc.start_if_admitted())
        self.assertTrue(svc.shutdown())


if __name__ == "__main__":
    unittest.main()
