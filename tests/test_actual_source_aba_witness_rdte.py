import unittest
from api.core.wine_events_rdte import SessionObserverRegistry
from api.core.wine_events_source_rdte import TrustedLocalEventSource

class SourceABA(unittest.TestCase):
    def test_same_name_aba_witness(self):
        r=SessionObserverRegistry()
        state={"session":"s"}
        current=lambda:state["session"]
        source=TrustedLocalEventSource("s",r,current,current)
        state["session"]="other"
        self.assertFalse(source._session_valid())
        state["session"]="s"
        self.assertTrue(source._session_valid())
    def test_mismatch_rejected(self):
        source=TrustedLocalEventSource("s",SessionObserverRegistry(),lambda:"other",lambda:"s")
        self.assertFalse(source._session_valid())
