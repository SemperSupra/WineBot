"""Read-only actual-broker seam tests; intentionally avoid production mutation."""
import asyncio
import unittest
from unittest.mock import patch

from api.core.broker import InputBroker
from api.core.models import ControlPolicyMode

class BrokerSeamTests(unittest.TestCase):
    def test_session_snapshot_is_detached(self):
        with patch("api.core.broker.get_instance_control_mode",return_value="hybrid"):
            b=InputBroker()
            asyncio.run(b.update_session("session-a",True,ControlPolicyMode.HYBRID))
            snapshot=b.get_state()
            snapshot.session_id="forged"
            self.assertEqual(b.get_state().session_id,"session-a")

    def test_current_broker_has_no_epoch_in_state(self):
        with patch("api.core.broker.get_instance_control_mode",return_value="hybrid"):
            b=InputBroker()
            asyncio.run(b.update_session("session-a",True,ControlPolicyMode.HYBRID))
            self.assertFalse(hasattr(b.get_state(),"generation"))
            self.assertFalse(hasattr(b.get_state(),"incarnation_id"))

if __name__=="__main__":
    unittest.main()
