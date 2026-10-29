"""Actual broker incarnation reset/rollback negative evidence; no process spawn.

This intentionally verifies a known weakness of the in-memory counter. A
green witness MUST NOT be misrepresented as durable session fencing.
"""
import asyncio
import unittest
from unittest.mock import patch
from api.core.broker import InputBroker
from api.core.models import ControlPolicyMode


def new_broker():
    with patch("api.core.broker.get_instance_control_mode", return_value="hybrid"):
        return InputBroker()


def set_session(broker, name):
    with patch("api.core.broker.get_instance_control_mode", return_value="hybrid"):
        asyncio.run(broker.update_session(name, True, ControlPolicyMode.HYBRID))


class ActualBrokerResetNegative(unittest.TestCase):
    def test_separate_broker_instances_reuse_same_incarnation(self):
        first, second = new_broker(), new_broker()
        set_session(first, "synthetic-s")
        set_session(second, "synthetic-s")
        old = first.get_observer_session_snapshot()
        new = second.get_observer_session_snapshot()
        self.assertEqual(old, new,
                         "witness identical pair after independent process-local state")
        self.assertEqual(new, ("synthetic-s", 1))

    def test_reset_does_not_preserve_prior_high_water_mark(self):
        old = new_broker()
        for _ in range(4):
            set_session(old, "synthetic-s")
        self.assertEqual(old.get_observer_session_snapshot(), ("synthetic-s", 4))
        new = new_broker()
        set_session(new, "synthetic-s")
        self.assertEqual(new.get_observer_session_snapshot(), ("synthetic-s", 1))
        self.assertLess(new.get_observer_session_snapshot()[1],
                        old.get_observer_session_snapshot()[1])

    def test_same_name_epoch_snapshot_is_not_a_capability(self):
        broker = new_broker()
        set_session(broker, "synthetic-s")
        snapshot = broker.get_observer_session_snapshot()
        self.assertIs(type(snapshot), tuple)
        self.assertEqual(len(snapshot), 2)
        self.assertFalse(hasattr(broker, "admit_observer_epoch"))
        self.assertFalse(hasattr(broker, "claim_observer_resource"))

    def test_session_reincarnation_changes_only_local_counter(self):
        broker = new_broker()
        set_session(broker, "synthetic-s")
        old = broker.get_observer_session_snapshot()
        set_session(broker, "synthetic-t")
        set_session(broker, "synthetic-s")
        new = broker.get_observer_session_snapshot()
        self.assertEqual(old[0], new[0])
        self.assertNotEqual(old[1], new[1])
        self.assertEqual(new[1], 3)


if __name__ == "__main__":
    unittest.main()
