import unittest
from rdte.wine11.wininspect_correlation_rdte import correlate, CorrelationError

class CorrelationTests(unittest.TestCase):
    def test_valid(self):
        self.assertEqual(correlate("r1", {"id":"r1","result":{"ok":True}}), {"ok":True})

    def test_missing_id_fails_closed(self):
        with self.assertRaisesRegex(CorrelationError, "missing_response_id"):
            correlate("r1", {"result":{"ok":True}})

    def test_wrong_id_fails_closed(self):
        with self.assertRaisesRegex(CorrelationError, "response_id_mismatch"):
            correlate("r1", {"id":"r2","result":{"ok":True}})

    def test_invalid_envelope(self):
        with self.assertRaisesRegex(CorrelationError, "invalid_response"):
            correlate("r1", None)

    def test_invalid_request(self):
        with self.assertRaisesRegex(CorrelationError, "invalid_request_id"):
            correlate("", {"id":"","result":None})

    def test_no_identifier_leak(self):
        secret = "sensitive-rpc-identifier"
        try:
            correlate(secret, {"id":"wrong"})
        except CorrelationError as exc:
            self.assertNotIn(secret, str(exc))
            self.assertNotIn("wrong", str(exc))

if __name__ == "__main__":
    unittest.main()
