"""Actual registry/bridge ownership tests; no Wine process or secrets."""
import unittest
from api.core.wine_events_rdte import SessionObserverRegistry
from rdte.wine11.event_bridge import EventBridge

class RegistryOwnership(unittest.TestCase):
    def test_old_bridge_cannot_clear_replacement_same_session(self):
        r=SessionObserverRegistry()
        old,new=EventBridge(),EventBridge()
        r.attach_internal("same",old)
        r.attach_internal("same",new)
        self.assertFalse(r.clear_if_owner("same",old))
        self.assertTrue(r.clear_if_owner("same",new))
    def test_session_change_clears_previous(self):
        r=SessionObserverRegistry()
        r.attach_internal("old",EventBridge())
        r.session_changed("new")
        self.assertEqual(r.observe("old")["state"],"unavailable")
if __name__=="__main__":
    unittest.main()
