"""Actual InputBroker candidate incarnation snapshot; no admission/launch.

Unlike earlier synthetic epoch stores, this exercises the real class and
synchronized update_session mutation. No private ledger code is reproduced.
"""
import asyncio
import threading
import unittest
from unittest.mock import patch

from api.core.broker import InputBroker
from api.core.models import ControlPolicyMode


def new_broker():
    with patch("api.core.broker.get_instance_control_mode", return_value="hybrid"):
        return InputBroker()


def set_session(broker, session):
    with patch("api.core.broker.get_instance_control_mode", return_value="hybrid"):
        asyncio.run(broker.update_session(session, True, ControlPolicyMode.HYBRID))


class ActualBrokerSnapshotTests(unittest.TestCase):
    def test_initial_snapshot_is_nonadmitting(self):
        broker = new_broker()
        self.assertEqual(broker.get_observer_session_snapshot(), ("unknown", 0))
        self.assertFalse(hasattr(broker, "admit_observer_epoch"))

    def test_same_session_name_bumps_incarnation(self):
        broker = new_broker()
        set_session(broker, "synthetic-a")
        self.assertEqual(broker.get_observer_session_snapshot(), ("synthetic-a", 1))
        set_session(broker, "synthetic-a")
        self.assertEqual(broker.get_observer_session_snapshot(), ("synthetic-a", 2))
        set_session(broker, "synthetic-b")
        self.assertEqual(broker.get_observer_session_snapshot(), ("synthetic-b", 3))

    def test_detached_old_snapshot_does_not_change(self):
        broker = new_broker()
        set_session(broker, "synthetic-a")
        original = broker.get_observer_session_snapshot()
        set_session(broker, "synthetic-b")
        self.assertEqual(original, ("synthetic-a", 1))
        self.assertEqual(broker.get_observer_session_snapshot(), ("synthetic-b", 2))
        self.assertIsInstance(original, tuple)

    def test_concurrent_readers_never_observe_mixed_pair(self):
        broker = new_broker()
        observed = []
        failures = []
        done = threading.Event()
        def writer():
            try:
                for n in range(1, 61):
                    set_session(broker, "synthetic-a" if n % 2 else "synthetic-b")
            except Exception:
                failures.append("writer_failed")
            finally:
                done.set()
        def reader():
            while not done.is_set():
                observed.append(broker.get_observer_session_snapshot())
            observed.append(broker.get_observer_session_snapshot())
        t1 = threading.Thread(target=writer)
        readers = [threading.Thread(target=reader) for _ in range(3)]
        for t in readers:
            t.start()
        t1.start()
        t1.join(timeout=8)
        self.assertFalse(t1.is_alive())
        done.set()
        for t in readers:
            t.join(timeout=2)
            self.assertFalse(t.is_alive())
        self.assertFalse(failures)
        self.assertGreater(len(observed), 0)
        self.assertEqual(broker.get_observer_session_snapshot(), ("synthetic-b", 60))
        for session, incarnation in observed:
            if incarnation == 0:
                self.assertEqual(session, "unknown")
            else:
                self.assertEqual(
                    session, "synthetic-a" if incarnation % 2 else "synthetic-b"
                )

    def test_regular_snapshot_remains_detached(self):
        broker = new_broker()
        set_session(broker, "synthetic-a")
        copy = broker.get_state()
        copy.session_id = "mutated"
        self.assertEqual(broker.get_state().session_id, "synthetic-a")
        self.assertEqual(broker.get_observer_session_snapshot(), ("synthetic-a", 1))


if __name__ == "__main__":
    unittest.main()
