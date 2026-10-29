import asyncio
import unittest
from unittest.mock import patch
from api.core.broker import InputBroker

class BrokerSnapshot(unittest.TestCase):
    def test_detached_snapshot(self):
        with patch("api.core.broker.get_instance_control_mode",return_value="hybrid"):
            broker=InputBroker()
        original=broker.get_state().session_id
        state=broker.get_state()
        state.session_id="forged"
        self.assertEqual(broker.get_state().session_id,original)
    def test_session_name_reuse(self):
        with patch("api.core.broker.get_instance_control_mode",return_value="hybrid"):
            broker=InputBroker()
        asyncio.run(broker.update_session("s",False))
        asyncio.run(broker.update_session("other",False))
        asyncio.run(broker.update_session("s",False))
        self.assertEqual(broker.get_state().session_id,"s")
        self.assertFalse(hasattr(broker.get_state(),"observer_incarnation"))
