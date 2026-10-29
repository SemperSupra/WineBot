import unittest
from api.core.wine_events_rdte import SessionObserverRegistry
from api.core.wine_events_source_rdte import TrustedLocalEventSource
class SourceFence(unittest.TestCase):
    def test_unfenced_source_denied(self):
        s=TrustedLocalEventSource("s",SessionObserverRegistry(),lambda:"s",lambda:"s")
        self.assertFalse(s._session_valid())
    def test_receipt_rotation_denied(self):
        token={"value":"a"}
        s=TrustedLocalEventSource("s",SessionObserverRegistry(),lambda:"s",lambda:"s",
             incarnation="a",validate_incarnation=lambda name,t: token["value"]==t)
        self.assertTrue(s._session_valid())
        token["value"]="b"
        self.assertFalse(s._session_valid())
    def test_incomplete_receipt_denied(self):
        with self.assertRaises(ValueError):
            TrustedLocalEventSource("s",SessionObserverRegistry(),lambda:"s",lambda:"s",incarnation="a")
