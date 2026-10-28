# Source-only observer admission race oracle
from pathlib import Path
import unittest

class ObserverAdmissionSourceTests(unittest.TestCase):
    def test_observed_split_callbacks_are_not_atomic(self):
        source=Path("api/core/wine_events_service_rdte.py").read_text()
        self.assertIn("session_id = self._active_session()",source)
        self.assertIn("session_id == self._broker_session()",source)
        self.assertIn("self._last_started_session = session",source)

    def test_broker_has_detached_snapshot_but_no_epoch_admission(self):
        source=Path("api/core/broker.py").read_text()
        self.assertIn("return self.state.model_copy(deep=True)",source)
        self.assertNotIn("def admit_observer_epoch(",source)

if __name__=="__main__":
    unittest.main()
